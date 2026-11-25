"""Deterministic pre-execution validator for LLM-generated behavior trees.

The validator never calls a model. Given a BT (XML or compiled tree), the
skill library and the symbolic world it is about to run in, it proves or
refutes — *before the robot moves* — that the tree:

  L1  STRUCTURE   uses only whitelisted nodes, legal arity, unique names, bounded size/depth/retries
  L2  PORTS       every attribute is declared, typed, in range and refers to a real zone/object;
                  no blackboard indirection (``{var}``) that could smuggle in ungrounded values
  L3  SEMANTICS   symbolic execution over *all* success/failure outcomes: preconditions hold at every
                  action (no illegal transitions), geofences are respected, payload/capacity limits hold
  L4  GOALS       every success path of the root establishes the declared (and externally required)
                  goals and leaves the gripper empty

Symbolic execution model: skills are transactional (a failing skill leaves the
world unchanged); condition nodes are evaluated against the belief state; a
node yields a set of (SUCCESS|FAILURE, world) outcomes, so Fallback branches
are analysed from the state in which the earlier alternatives failed.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from . import bt as btmod
from .bt import BTNode, BTParseError
from .geometry import segment_hits_rect, point_in_rect
from .issues import Issue, has_errors
from .skills import SkillLibrary, load_library
from .world import World

_BLACKBOARD = re.compile(r"[{}]")
_Outcome = tuple[bool, World]


@dataclass
class Limits:
    max_nodes: int = 60
    max_depth: int = 12
    max_retry_product: int = 10  # product of nested RetryUntilSuccessful attempts
    max_outcomes: int = 32  # cap on distinct symbolic worlds per node


@dataclass
class ValidationReport:
    issues: list[Issue] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)
    elapsed_ms: float = 0.0

    @property
    def ok(self) -> bool:
        return not has_errors(self.issues)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    def summary(self) -> str:
        if self.ok:
            return f"VALID ({self.stats.get('nodes', '?')} nodes, {self.elapsed_ms:.1f} ms)"
        return "INVALID:\n" + "\n".join(f"  {i}" for i in self.errors)

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "issues": [i.to_dict() for i in self.issues],
                "stats": self.stats, "elapsed_ms": round(self.elapsed_ms, 3)}


class Validator:
    def __init__(self, library: SkillLibrary | None = None, limits: Limits | None = None):
        self.lib = library or load_library()
        self.limits = limits or Limits()

    # ------------------------------------------------------------------ entry
    def validate_xml(self, xml: str, world: World,
                     goals: list[dict[str, Any]] | None = None,
                     required_goals: list[dict[str, Any]] | None = None) -> ValidationReport:
        t0 = time.perf_counter()
        try:
            root = btmod.parse_xml(xml)
        except BTParseError as e:
            r = ValidationReport([Issue("XML_MALFORMED", str(e))])
            r.elapsed_ms = (time.perf_counter() - t0) * 1000
            return r
        rep = self.validate_tree(root, world, goals, required_goals)
        rep.elapsed_ms = (time.perf_counter() - t0) * 1000
        return rep

    def validate_plan(self, plan: dict[str, Any], world: World,
                      required_goals: list[dict[str, Any]] | None = None) -> tuple[BTNode | None, ValidationReport]:
        t0 = time.perf_counter()
        tree, compile_issues = btmod.compile_plan(plan)
        if tree is None:
            r = ValidationReport(compile_issues)
            r.elapsed_ms = (time.perf_counter() - t0) * 1000
            return None, r
        # Round-trip through XML so what we validate is exactly what would execute.
        rep = self.validate_xml(btmod.to_xml(tree), world, plan.get("goals"), required_goals)
        rep.issues = compile_issues + rep.issues
        rep.elapsed_ms = (time.perf_counter() - t0) * 1000
        return tree, rep

    def validate_tree(self, root: BTNode, world: World,
                      goals: list[dict[str, Any]] | None = None,
                      required_goals: list[dict[str, Any]] | None = None) -> ValidationReport:
        t0 = time.perf_counter()
        issues: list[Issue] = []
        self._structure(root, issues)
        self._ports(root, world, issues)
        paths = 0
        if not has_errors(issues):  # semantics presuppose a well-formed tree
            ex = _Executor(self, world, issues)
            outcomes = ex.run(root, [(True, world.copy())])
            paths = len(outcomes)
            self._goals(outcomes, world, goals or [], required_goals or [], root, issues)
            if not any(s for s, _ in outcomes):
                issues.append(Issue("NO_SUCCESS_PATH",
                                    "the tree can never succeed under the belief state", root.name, "warning"))
        issues = _dedupe(issues)
        rep = ValidationReport(issues, {
            "nodes": root.count(), "depth": root.depth(), "symbolic_paths": paths,
        })
        rep.elapsed_ms = (time.perf_counter() - t0) * 1000
        return rep

    # --------------------------------------------------------------- L1: shape
    def _structure(self, root: BTNode, out: list[Issue]) -> None:
        lim = self.limits
        seen: set[str] = set()
        if root.count() > lim.max_nodes:
            out.append(Issue("TOO_MANY_NODES", f"{root.count()} nodes exceeds limit {lim.max_nodes}", root.name))
        if root.depth() > lim.max_depth:
            out.append(Issue("TOO_DEEP", f"depth {root.depth()} exceeds limit {lim.max_depth}", root.name))

        def visit(n: BTNode, retry_prod: int) -> None:
            if n.name in seen:
                out.append(Issue("DUPLICATE_NAME", f"node name '{n.name}' is not unique", n.name))
            seen.add(n.name)
            if n.tag in self.lib.controls:
                c = self.lib.controls[n.tag]
                k = len(n.children)
                if k < c.min_children or (c.max_children is not None and k > c.max_children):
                    rng = f"{c.min_children}..{c.max_children if c.max_children is not None else 'N'}"
                    out.append(Issue("BAD_ARITY", f"{n.tag} requires {rng} children, has {k}", n.name))
                if n.tag == "RetryUntilSuccessful":
                    try:
                        retry_prod *= max(1, int(n.attrs.get("num_attempts", "1")))
                    except ValueError:
                        pass  # reported by the port check
                    if retry_prod > lim.max_retry_product:
                        out.append(Issue("RETRY_EXPLOSION",
                                         f"nested retries multiply to {retry_prod} (> {lim.max_retry_product})", n.name))
            elif n.tag in self.lib.skills:
                if n.children:
                    out.append(Issue("LEAF_WITH_CHILDREN", f"skill {n.tag} must be a leaf", n.name))
            else:
                out.append(Issue("UNKNOWN_NODE", f"'{n.tag}' is not in the skill library", n.name))
            for ch in n.children:
                visit(ch, retry_prod)

        visit(root, 1)

    # -------------------------------------------------------------- L2: ports
    def _ports(self, root: BTNode, world: World, out: list[Issue]) -> None:
        for n in root.walk():
            spec = (self.lib.skills.get(n.tag) and self.lib.skills[n.tag].ports) or \
                   (self.lib.controls.get(n.tag) and self.lib.controls[n.tag].ports)
            if spec is None:
                continue  # unknown node already reported
            for pname in n.attrs:
                if pname not in spec:
                    out.append(Issue("UNKNOWN_PORT", f"{n.tag} has no port '{pname}'", n.name))
            for pname, p in spec.items():
                if pname not in n.attrs:
                    if p.required:
                        out.append(Issue("MISSING_PORT", f"{n.tag} requires port '{pname}'", n.name))
                    continue
                v = n.attrs[pname]
                if _BLACKBOARD.search(v):
                    out.append(Issue("BLACKBOARD_REF",
                                     f"port '{pname}' = '{v}': blackboard/ungrounded values are not allowed", n.name))
                    continue
                if p.type == "zone" and v not in world.zones:
                    out.append(Issue("UNKNOWN_ZONE", f"'{v}' is not a zone (known: {sorted(world.zones)})", n.name))
                elif p.type == "object" and v not in world.objects:
                    out.append(Issue("UNKNOWN_OBJECT", f"'{v}' is not an object (known: {sorted(world.objects)})", n.name))
                elif p.type in ("int", "float"):
                    try:
                        x = int(v) if p.type == "int" else float(v)
                    except ValueError:
                        out.append(Issue("BAD_NUMBER", f"port '{pname}'='{v}' is not a {p.type}", n.name))
                        continue
                    if (p.min is not None and x < p.min) or (p.max is not None and x > p.max):
                        out.append(Issue("OUT_OF_RANGE", f"port '{pname}'={x} outside [{p.min}, {p.max}]", n.name))
                elif p.type == "string" and not v.strip():
                    out.append(Issue("EMPTY_STRING", f"port '{pname}' is empty", n.name))

    # --------------------------------------------------------------- L4: goals
    def _goals(self, outcomes: list[_Outcome], initial: World, goals: list[dict[str, Any]],
               required: list[dict[str, Any]], root: BTNode, out: list[Issue]) -> None:
        for g in goals + required:
            msg = _check_goal_wellformed(g, initial)
            if msg:
                out.append(Issue("BAD_GOAL", msg, root.name))
        succ = [w for ok, w in outcomes if ok]
        for src, glist in (("declared", goals), ("required", required)):
            for g in glist:
                if _check_goal_wellformed(g, initial):
                    continue
                if any(not _holds(g, w) for w in succ):
                    out.append(Issue("GOAL_NOT_ESTABLISHED",
                                     f"{src} goal {g['predicate']}({', '.join(g['args'])}) "
                                     f"is not guaranteed on every success path", root.name))
        if any(w.holding is not None for w in succ):
            out.append(Issue("END_HOLDING", "a success path ends with the gripper still holding an object "
                                            "(must place it or never pick it)", root.name))


def _check_goal_wellformed(g: dict[str, Any], w: World) -> str | None:
    pred, args = g.get("predicate"), g.get("args", [])
    arity = {"object_at": 2, "robot_at": 1, "gripper_empty": 0, "zone_clear": 1}
    if pred not in arity:
        return f"unknown goal predicate '{pred}'"
    if len(args) != arity[pred]:
        return f"goal {pred} expects {arity[pred]} args, got {len(args)}"
    if pred == "object_at" and (args[0] not in w.objects or args[1] not in w.zones):
        return f"goal object_at({', '.join(args)}) references unknown object/zone"
    if pred in ("robot_at", "zone_clear") and args[0] not in w.zones:
        return f"goal {pred}({args[0]}) references unknown zone"
    return None


def _holds(g: dict[str, Any], w: World) -> bool:
    p, a = g["predicate"], g.get("args", [])
    if p == "object_at":
        return w.objects[a[0]].zone == a[1]
    if p == "robot_at":
        return w.robot_zone == a[0]
    if p == "gripper_empty":
        return w.holding is None
    if p == "zone_clear":
        return w.zone_clear(a[0])
    return False


def _dedupe(issues: list[Issue]) -> list[Issue]:
    seen, out = set(), []
    for i in issues:
        k = (i.code, i.node, i.message)
        if k not in seen:
            seen.add(k)
            out.append(i)
    return out


# --------------------------------------------------------------------------
# L3: symbolic executor
# --------------------------------------------------------------------------
class _Executor:
    def __init__(self, v: Validator, world: World, issues: list[Issue]):
        self.v, self.issues = v, issues
        self.cap = v.limits.max_outcomes

    def _cap(self, outs: list[_Outcome]) -> list[_Outcome]:
        seen, res = set(), []
        for ok, w in outs:
            k = (ok, w.state_key())
            if k not in seen:
                seen.add(k)
                res.append((ok, w))
        if len(res) > self.cap:
            self.issues.append(Issue("STATE_EXPLOSION",
                                     f"more than {self.cap} distinct symbolic worlds; simplify the tree", None))
            res = res[: self.cap]
        return res

    def run(self, n: BTNode, ins: list[_Outcome]) -> list[_Outcome]:
        """Execute node n from every *entering* (ok=True) world in ins; returns outcomes."""
        outs: list[_Outcome] = []
        for _, w in ins:
            outs.extend(self._node(n, w))
        return self._cap(outs)

    def _node(self, n: BTNode, w: World) -> list[_Outcome]:
        t = n.tag
        if t in ("Sequence", "ReactiveSequence"):
            cur, fails = [(True, w)], []
            for c in n.children:
                nxt = self.run(c, cur)
                fails += [o for o in nxt if not o[0]]
                cur = [o for o in nxt if o[0]]
                if not cur:
                    break
            return [*cur, *fails]
        if t == "Fallback":
            cur, succ = [(True, w)], []
            for c in n.children:
                nxt = self.run(c, cur)
                succ += [o for o in nxt if o[0]]
                cur = [(True, ww) for ok, ww in nxt if not ok]
                if not cur:
                    break
            return [*succ, *[(False, ww) for _, ww in cur]]
        if t in ("RetryUntilSuccessful", "Timeout"):
            return self.run(n.children[0], [(True, w)])
        if t == "Inverter":
            return [(not ok, ww) for ok, ww in self.run(n.children[0], [(True, w)])]
        if t == "ForceSuccess":
            return [(True, ww) for _, ww in self.run(n.children[0], [(True, w)])]
        return self._skill(n, w)

    # ------------------------------------------------------------- skill rules
    def _err(self, code: str, msg: str, n: BTNode) -> None:
        self.issues.append(Issue(code, msg, n.name))

    def _skill(self, n: BTNode, w: World) -> list[_Outcome]:
        a, t = n.attrs, n.tag
        if t == "CheckZoneClear":
            return [(w.zone_clear(a["zone"]), w)]
        if t == "CheckHolding":
            return [(w.holding == a["object"], w)]
        if t == "CheckObjectAt":
            return [(w.objects[a["object"]].zone == a["zone"], w)]
        if t in ("ReportStatus", "RequestHumanHelp", "Wait"):
            return [(True, w), (False, w)] if t == "Wait" else [(True, w)]

        w2 = w.copy()
        if t == "NavigateTo":
            self._nav_pre(n, w, a["zone"])
            z = w.zones[a["zone"]]
            w2.robot_zone, w2.robot_pos = z.name, z.access
        elif t == "PickObject":
            o = w.objects[a["object"]]
            if w.holding is not None:
                self._err("GRIPPER_BUSY", f"cannot pick '{o.name}': already holding '{w.holding}'", n)
            if o.zone is None:
                self._err("OBJECT_NOT_AVAILABLE", f"'{o.name}' is not located anywhere (held?)", n)
            elif w.robot_zone != o.zone:
                self._err("NOT_AT_OBJECT",
                          f"cannot pick '{o.name}' (in '{o.zone}'): robot is at '{w.robot_zone}' — navigate first", n)
            if not o.graspable:
                self._err("NOT_GRASPABLE", f"'{o.name}' is marked NOT-GRASPABLE", n)
            if o.mass > w.payload_kg:
                self._err("PAYLOAD_EXCEEDED", f"'{o.name}' mass {o.mass}kg > payload {w.payload_kg}kg", n)
            w2.holding, w2.objects[o.name].zone = o.name, None
        elif t == "PlaceObject":
            o, z = a["object"], w.zones[a["zone"]]
            if w.holding != o:
                self._err("NOT_HOLDING", f"cannot place '{o}': gripper holds '{w.holding}'", n)
            if w.robot_zone != z.name:
                self._err("NOT_AT_ZONE",
                          f"cannot place at '{z.name}': robot is at '{w.robot_zone}' — navigate first", n)
            if not z.placeable:
                self._err("ZONE_NOT_PLACEABLE", f"zone '{z.name}' is marked NO-PLACING", n)
            if len(w.objects_in(z.name)) >= z.capacity:
                self._err("ZONE_CAPACITY", f"zone '{z.name}' already holds {len(w.objects_in(z.name))} "
                                           f"object(s) (capacity {z.capacity})", n)
            w2.objects[o].zone, w2.holding = z.name, None
        return [(True, w2), (False, w)]

    def _nav_pre(self, n: BTNode, w: World, zone: str) -> None:
        z = w.zones[zone]
        if not z.navigable:
            self._err("ZONE_NOT_NAVIGABLE", f"zone '{zone}' is not navigable", n)
        for tz in w.zones.values():
            blockers = [o.name for o in w.objects_in(tz.name)]
            if tz.transit and blockers and tz.name != zone and segment_hits_rect(w.robot_pos, z.access, tz.rect):
                self._err("TRANSIT_BLOCKED",
                          f"path {w.robot_zone}->{zone} crosses transit zone '{tz.name}' which is "
                          f"obstructed by {blockers}; clear it first", n)
        for k in w.keepouts.values():
            if point_in_rect(z.access, _inflate(k.rect, w.path_margin)):
                self._err("GEOFENCE_TARGET", f"target '{zone}' access pose lies inside keep-out '{k.name}'", n)
            elif segment_hits_rect(w.robot_pos, z.access, k.rect, w.path_margin):
                via = self._via_hint(w, zone)
                self._err("GEOFENCE_PATH",
                          f"straight path {w.robot_zone}->{zone} crosses keep-out '{k.name}'"
                          f"{'; route via ' + via if via else ''}", n)

    @staticmethod
    def _via_hint(w: World, target: str) -> str:
        t = w.zones[target].access
        opts = []
        for z in w.zones.values():
            if z.name in (target, w.robot_zone) or not z.navigable:
                continue
            clear = not any(
                segment_hits_rect(w.robot_pos, z.access, k.rect, w.path_margin)
                or segment_hits_rect(z.access, t, k.rect, w.path_margin)
                or point_in_rect(z.access, _inflate(k.rect, w.path_margin))
                for k in w.keepouts.values()
            )
            if clear:
                opts.append(z.name)
        return ", ".join(opts)


def _inflate(r, m):
    return (r[0] - m, r[1] - m, r[2] + m, r[3] + m)
