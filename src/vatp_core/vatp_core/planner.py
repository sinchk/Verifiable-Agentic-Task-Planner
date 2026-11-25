"""LLM → validated Behavior Tree planner with a generate–validate–repair loop and replanning.

    instruction + scene ──► RAG ──► LLM (constrained JSON BT) ──► compile ──► VALIDATOR
                                       ▲                                        │ issues
                                       └────────── repair prompt ◄──────────────┘
                                                                  │ valid
                                                                  ▼ BT.CPP XML  (only now may the robot move)

Nothing the LLM emits reaches the executor unless ``PlanResult.ok`` is True.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from . import bt as btmod
from .bt import BTNode
from .issues import Issue
from .llm import LLMBackend, LLMError, Prompt
from .rag import Retriever
from .skills import SkillLibrary, load_library
from .validator import ValidationReport, Validator
from .world import World

SYSTEM_TEMPLATE = """You are the task-planning module of a warehouse mobile manipulator. You do NOT control the robot.
You output a Behavior Tree (BT) that a deterministic validator will check and, only if it passes, a BehaviorTree.CPP executor will run.

OUTPUT: a JSON object matching the provided schema:
  - "nodes": flat list. Each node: id (unique, e.g. "n1"), type (a node from the library), params ([{{name,value}}]), children (ordered list of child ids).
  - "root": id of the root node. Every node must be reachable from root; each node has exactly one parent; no cycles.
  - "goals": postconditions your tree guarantees on every success path (object_at(obj,zone), robot_at(zone), gripper_empty(), zone_clear(zone)).
  - "rationale": 1-3 sentences.

HARD RULES
  * Use ONLY the nodes below, with exactly the declared ports. Port values are literal zone/object names from the scene. No {{blackboard}} references.
  * Navigate to a zone before picking from it or placing into it. The gripper holds one object at a time and must be empty at the end.
  * Never route through keep-out geofences: split long moves into legal NavigateTo waypoints.
  * Conditional instructions ("if blocked, ...") => Fallback[ condition, Sequence[ remedial steps ] ].
  * Wrap fragile skills in RetryUntilSuccessful (<=5 attempts) when appropriate; end unrecoverable branches with RequestHumanHelp.

{library}

SAFETY CONSTRAINTS (always apply):
{safety}

RELEVANT PROCEDURES (retrieved):
{retrieved}
"""


@dataclass
class Failure:
    """What the executor tells the planner when a running tree fails."""
    node: str  # name of failing leaf node
    skill: str
    code: str  # one of SkillLibrary.failure_codes
    message: str = ""
    detail: dict[str, Any] = field(default_factory=dict)

    def describe(self) -> str:
        return f"skill {self.skill} (node '{self.node}') failed with {self.code}: {self.message}"


@dataclass
class Attempt:
    latency_s: float
    llm_latency_s: float
    input_tokens: int
    output_tokens: int
    validation_ms: float
    issues: list[Issue]
    plan: dict[str, Any] | None
    error: str | None = None


@dataclass
class PlanResult:
    ok: bool
    mode: str  # plan | replan
    tree: BTNode | None
    xml: str | None
    plan: dict[str, Any] | None
    report: ValidationReport | None
    attempts: list[Attempt]
    total_latency_s: float
    backend: str
    retrieved: list[str] = field(default_factory=list)

    @property
    def n_repairs(self) -> int:
        return max(0, len(self.attempts) - 1)

    def metrics(self) -> dict[str, Any]:
        return {
            "ok": self.ok, "mode": self.mode, "attempts": len(self.attempts),
            "repairs": self.n_repairs, "latency_s": round(self.total_latency_s, 3),
            "llm_latency_s": round(sum(a.llm_latency_s for a in self.attempts), 3),
            "validation_ms": round(sum(a.validation_ms for a in self.attempts), 3),
            "input_tokens": sum(a.input_tokens for a in self.attempts),
            "output_tokens": sum(a.output_tokens for a in self.attempts),
            "nodes": self.tree.count() if self.tree else 0,
            "first_attempt_valid": bool(self.attempts and not any(
                i.severity == "error" for i in self.attempts[0].issues) and self.attempts[0].error is None),
        }


class Planner:
    def __init__(self, backend: LLMBackend, validator: Validator | None = None,
                 retriever: Retriever | None = None, library: SkillLibrary | None = None,
                 max_repairs: int = 2):
        self.backend = backend
        self.lib = library or load_library()
        self.validator = validator or Validator(self.lib)
        self.retriever = retriever or Retriever()
        self.max_repairs = max_repairs
        self.schema = btmod.plan_json_schema(list(self.lib.skills) + list(self.lib.controls))

    # ---------------------------------------------------------------- prompts
    def _system(self, query: str, mode: str) -> tuple[str, list[str]]:
        safety = self.retriever.always("SC-")
        got = self.retriever.search(query, k=3, prefix="RP-") if mode == "replan" else \
            self.retriever.search(query, k=2, prefix="RP-")
        sys = SYSTEM_TEMPLATE.format(
            library=self.lib.prompt_description(),
            safety="\n".join(c.render() for c in safety),
            retrieved="\n".join(c.render() for c in got) or "(none)",
        )
        return sys, [c.id for c in got]

    # ------------------------------------------------------------------ core
    def _run(self, mode: str, system: str, user: str, world: World,
             required: list[dict[str, Any]], retrieved: list[str],
             ctx: dict[str, Any]) -> PlanResult:
        t_start = time.perf_counter()
        attempts: list[Attempt] = []
        feedback = ""
        tree: BTNode | None = None
        report: ValidationReport | None = None
        plan: dict[str, Any] | None = None
        for k in range(self.max_repairs + 1):
            t0 = time.perf_counter()
            prompt = Prompt(system, user + feedback, {**ctx, "attempt": k, "mode": mode, "world": world})
            try:
                res = self.backend.generate(prompt, self.schema)
            except LLMError as e:
                attempts.append(Attempt(time.perf_counter() - t0, time.perf_counter() - t0, 0, 0, 0.0,
                                        [Issue("LLM_ERROR", str(e))], None, str(e)))
                break
            plan = res.data
            tree, report = self.validator.validate_plan(plan, world, required)
            attempts.append(Attempt(time.perf_counter() - t0, res.latency_s, res.input_tokens,
                                    res.output_tokens, report.elapsed_ms, list(report.issues), plan))
            if report.ok:
                break
            feedback = (
                "\n\nYOUR PREVIOUS PLAN WAS REJECTED BY THE VALIDATOR. Fix every error and output a complete new plan.\n"
                f"Previous plan:\n{json.dumps(plan)}\n"
                "Validator errors:\n" + "\n".join(f"- {i}" for i in report.errors)
            )
        ok = bool(report and report.ok and tree is not None)
        return PlanResult(ok, mode, tree if ok else None, btmod.to_xml(tree) if ok else None,
                          plan, report, attempts, time.perf_counter() - t_start,
                          self.backend.name, retrieved)

    def plan(self, instruction: str, world: World,
             required_goals: list[dict[str, Any]] | None = None) -> PlanResult:
        system, got = self._system(instruction, "plan")
        user = f"{world.describe()}\n\nINSTRUCTION: {instruction}\n"
        return self._run("plan", system, user, world, required_goals or [], got,
                         {"instruction": instruction, "required_goals": required_goals or []})

    def replan(self, instruction: str, world: World, failure: Failure,
               required_goals: list[dict[str, Any]] | None = None,
               declined: list[str] | None = None) -> PlanResult:
        """Patch the mission after a runtime failure.

        ``world`` is the *current* belief state (robot pose, held object, updated
        object locations, newly perceived obstacles). The returned tree covers the
        REMAINING mission only; ``required_goals`` are the still-unsatisfied goals.
        """
        query = f"{failure.code} {failure.skill} {failure.message} replan remaining"
        system, got = self._system(query, "replan")
        user = (f"{world.describe()}\n\nORIGINAL INSTRUCTION: {instruction}\n"
                f"EXECUTION FAILURE: {failure.describe()}\n"
                "Produce a new tree for the REMAINING mission from the CURRENT scene above "
                "(do not repeat completed steps; the gripper may be holding an object).\n")
        if declined:
            user += "Previously rejected recovery ideas: " + "; ".join(declined) + "\n"
        return self._run("replan", system, user, world, required_goals or [], got,
                         {"instruction": instruction, "failure": failure,
                          "required_goals": required_goals or []})
