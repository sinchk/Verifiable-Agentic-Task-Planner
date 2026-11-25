"""Deterministic offline stand-in for the LLM (test double / CI / baseline).

A tiny goal-regression planner: derive goals from the instruction (plan) or take the
still-open goals (replan), then emit a BT with geofence-legal routes, bounded retries and
human-escalation fallbacks. Optional ``defect_rate`` injects *reproducible* LLM-style
mistakes into the FIRST attempt of a request so the validator and repair loop are
exercised without network or cost. Mock results are always labelled ``backend=mock``.
"""
from __future__ import annotations

import random
import re
import time
from typing import Any

from . import bt as btmod
from .bt import BTNode
from .llm import LLMResult, Prompt
from .geometry import segment_hits_rect
from .routing import route
from .world import World

DEFECTS = ("drop_nav", "direct_nav", "bad_zone", "bad_skill", "blackboard", "drop_place", "unbounded")


class _Builder:
    def __init__(self) -> None:
        self.n = 0

    def node(self, tag: str, children: list[BTNode] | None = None, **attrs: str) -> BTNode:
        self.n += 1
        return BTNode(tag, f"n{self.n}", {k: str(v) for k, v in attrs.items()}, children or [])


def _derive_goals(instruction: str, w: World) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    s = instruction.lower().replace("_", " ")
    goals: list[dict[str, Any]] = []
    flags = {"conditional_bay": False, "report": "report" in s}
    if "crate" in s:
        for zname in ("zone b", "zone a", "staging", "loading bay"):
            if f"to {zname}" in s or f"to {zname.replace(' ', '')}" in s:
                goals.append({"predicate": "object_at", "args": ["crate_1", zname.replace(" ", "_")]})
                break
    if "small box" in s and "staging" in s and "move the small box to staging" in s:
        goals.insert(0, {"predicate": "object_at", "args": ["small_box_1", "staging"]})
    if "loading bay" in s and ("clear" in s or "blocked" in s):
        flags["conditional_bay"] = True
        goals.append({"predicate": "zone_clear", "args": ["loading_bay"]})
    goals.append({"predicate": "gripper_empty", "args": []})
    return goals, flags


class MockBackend:
    def __init__(self, defect_rate: float = 0.0, seed: int = 0):
        self.defect_rate, self.seed = defect_rate, seed
        self.name = f"mock(defect_rate={defect_rate})"
        self._calls = 0

    # ---------------------------------------------------------------- planning
    def _nav(self, b: _Builder, sim: World, zone: str, out: list[BTNode], depth: int = 0) -> None:
        for _ in range(12):  # re-route after every hop: clearing a corridor moves the robot
            if sim.robot_zone == zone:
                return
            hops = route(sim, sim.robot_pos, zone)
            if hops is None:
                out.append(b.node("RequestHumanHelp", reason=f"no legal route to {zone}"))
                return
            h = hops[0]
            if depth < 3:  # clear obstructed transit corridors this leg crosses
                blocked = [o.name for tz in sim.zones.values()
                           if tz.transit and tz.name != h and
                           segment_hits_rect(sim.robot_pos, sim.zones[h].access, tz.rect)
                           for o in sim.objects_in(tz.name)]
                if blocked:
                    for o in blocked:
                        self._move(b, sim, o, "staging", out, depth + 1)
                    continue
            out.append(b.node("RetryUntilSuccessful", [b.node("NavigateTo", zone=h)], num_attempts=2))
            sim.robot_zone, sim.robot_pos = h, sim.zones[h].access

    def _ensure_holding(self, b: _Builder, sim: World, obj: str, out: list[BTNode], depth: int) -> bool:
        o = sim.objects[obj]
        if sim.holding == obj:
            return True
        if sim.holding is not None:  # park whatever we hold first
            self._place_at(b, sim, sim.holding, "staging", out, depth)
        if o.mass > sim.payload_kg or not o.graspable or o.zone is None:
            out.append(b.node("RequestHumanHelp", reason=f"cannot handle {obj}"))
            return False
        self._nav(b, sim, o.zone, out, depth)
        out.append(b.node("RetryUntilSuccessful", [b.node("PickObject", object=obj)], num_attempts=3))
        o.zone, sim.holding = None, obj
        return True

    def _move(self, b: _Builder, sim: World, obj: str, dest: str, out: list[BTNode], depth: int = 0) -> None:
        if self._ensure_holding(b, sim, obj, out, depth):
            self._place_at(b, sim, obj, dest, out, depth)

    def _place_at(self, b: _Builder, sim: World, obj: str, dest: str, out: list[BTNode], depth: int = 0) -> None:
        self._nav(b, sim, dest, out, depth)  # may displace the held object while clearing a corridor
        if not self._ensure_holding(b, sim, obj, out, depth):
            return
        self._nav(b, sim, dest, out, depth)
        out.append(b.node("RetryUntilSuccessful", [b.node("PlaceObject", object=obj, zone=dest)], num_attempts=2))
        sim.objects[obj].zone, sim.holding = dest, None

    def _build(self, prompt: Prompt) -> dict[str, Any]:
        ctx = prompt.ctx
        w: World = ctx["world"]
        sim = w.copy()
        b = _Builder()
        steps: list[BTNode] = []
        if ctx["mode"] == "replan":
            goals, flags = list(ctx.get("required_goals", [])), {"conditional_bay": False, "report": False}
        else:
            goals, flags = _derive_goals(ctx["instruction"], w)

        order = {"zone_clear": 0, "object_at": 1, "robot_at": 2, "gripper_empty": 3}
        goals = sorted(goals, key=lambda g: order.get(g["predicate"], 9))
        for g in goals:
            p, a = g["predicate"], g["args"]
            if p == "zone_clear" and flags["conditional_bay"] and ctx["mode"] == "plan":
                remedial: list[BTNode] = []
                blockers = [o.name for o in sim.objects_in(a[0])]
                for o in blockers:
                    self._move(b, sim, o, "staging", remedial)
                if not remedial:  # belief says clear, but runtime may disagree -> escalate safely
                    remedial = [b.node("ReportStatus", message=f"{a[0]} unexpectedly blocked"),
                                b.node("RequestHumanHelp", reason=f"{a[0]} blocked")]
                steps.append(b.node("Fallback", [b.node("CheckZoneClear", zone=a[0]),
                                                 b.node("Sequence", remedial)]))
            elif p == "zone_clear":
                for o in [o.name for o in sim.objects_in(a[0])]:
                    self._move(b, sim, o, "staging", steps)
            elif p == "object_at" and sim.objects[a[0]].zone != a[1]:
                self._move(b, sim, a[0], a[1], steps)
            elif p == "gripper_empty" and sim.holding:
                self._place_at(b, sim, sim.holding, "staging", steps)
        if flags["report"]:
            steps.append(b.node("ReportStatus", message="mission complete"))
        if not steps:
            steps.append(b.node("ReportStatus", message="nothing to do"))
        root = b.node("Sequence", steps)
        return btmod.tree_to_plan(root, goals, "offline reference plan (goal-regression)")

    # ---------------------------------------------------------------- defects
    def _inject(self, plan: dict[str, Any], rng: random.Random) -> dict[str, Any]:
        root, _ = btmod.compile_plan(plan)
        assert root is not None
        nodes = list(root.walk())
        parent = {id(c): n for n in nodes for c in n.children}

        def drop(n: BTNode) -> None:
            p = parent[id(n)]
            p.children.remove(n)

        def leaves(tag: str) -> list[BTNode]:
            return [n for n in nodes if n.tag == tag]

        kinds = list(DEFECTS)
        rng.shuffle(kinds)
        for kind in kinds:
            if kind == "drop_nav" and leaves("NavigateTo"):
                n = leaves("NavigateTo")[0]
                drop(parent[id(n)] if parent[id(n)].tag == "RetryUntilSuccessful" else n)
            elif kind == "direct_nav":
                navs = leaves("NavigateTo")
                cand = [n for n in navs if n.attrs["zone"] == "loading_bay"]
                if cand and any(n.attrs["zone"] == "zone_b" for n in navs):
                    drop(parent[id(cand[-1])] if parent[id(cand[-1])].tag == "RetryUntilSuccessful" else cand[-1])
                else:
                    continue
            elif kind == "bad_zone" and leaves("NavigateTo"):
                leaves("NavigateTo")[-1].attrs["zone"] = "zone_c"
            elif kind == "bad_skill" and leaves("PickObject"):
                leaves("PickObject")[0].tag = "GraspObject"
            elif kind == "blackboard" and leaves("NavigateTo"):
                leaves("NavigateTo")[0].attrs["zone"] = "{target_zone}"
            elif kind == "drop_place" and leaves("PlaceObject"):
                n = leaves("PlaceObject")[-1]
                drop(parent[id(n)] if parent[id(n)].tag == "RetryUntilSuccessful" else n)
            elif kind == "unbounded" and leaves("RetryUntilSuccessful"):
                leaves("RetryUntilSuccessful")[0].attrs["num_attempts"] = "100"
            else:
                continue
            break
        out = btmod.tree_to_plan(root, plan["goals"], plan["rationale"])
        out["_injected_defect"] = kind
        return out

    def generate(self, prompt: Prompt, schema: dict[str, Any]) -> LLMResult:
        t0 = time.perf_counter()
        plan = self._build(prompt)
        self._calls += 1
        rng = random.Random(f"{self.seed}:{prompt.ctx.get('instruction')}:{prompt.ctx.get('mode')}")
        if prompt.ctx.get("attempt", 0) == 0 and rng.random() < self.defect_rate:
            plan = self._inject(plan, rng)
        # Simulate nothing about latency: the mock is instant; metrics label it as such.
        return LLMResult(plan, time.perf_counter() - t0, 0, 0, self.name, "end_turn")
