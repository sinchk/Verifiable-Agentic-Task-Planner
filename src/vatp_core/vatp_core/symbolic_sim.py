"""Symbolic skill backend: executes skills against a *ground-truth* world with fault injection.

This is the fast simulator behind the ROS skill servers (the Gazebo backend implements the same
``execute`` contract). Ground truth differs from the planner's belief exactly when a fault
fires — e.g. an obstacle appears in the loading bay after planning — which is what makes
closed-loop recovery necessary rather than decorative.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from .geometry import segment_hits_rect
from .scenarios import Fault, Scenario
from .world import World, WorldObject

ROBOT_SPEED = 0.8  # m/s (for simulated durations only)


@dataclass
class SkillResult:
    success: bool
    code: str = ""
    message: str = ""
    sim_duration_s: float = 0.0
    events: list[dict[str, Any]] = field(default_factory=list)  # e.g. FAULT_INJECTED


class SymbolicSim:
    def __init__(self, scenario: Scenario):
        self.scenario = scenario
        self.world: World = scenario.world.copy()
        self.fault: Fault = scenario.fault
        self.counts: dict[str, int] = {}
        self.fault_fired = False
        self.fail_remaining = 0
        self.safety_violations = 0
        self.escalations: list[str] = []
        self.log: list[str] = []

    # ------------------------------------------------------------------ faults
    def _maybe_fire(self, skill: str, res: SkillResult) -> None:
        f = self.fault
        self.counts[skill] = self.counts.get(skill, 0) + 1
        if f.type == "none" or self.fault_fired or f.trigger_skill != skill \
                or self.counts[skill] != f.trigger_count:
            return
        self.fault_fired = True
        if f.type == "obstacle_spawn":
            self.world.objects["obstacle_1"] = WorldObject("obstacle_1", f.obstacle_mass, f.zone)
            res.events.append({"type": "FAULT_INJECTED", "detail": f"obstacle_1 appeared in {f.zone}"})
        elif f.type in ("nav_block", "grasp_fail", "place_fail"):
            self.fail_remaining = max(1, f.fail_attempts)
            res.events.append({"type": "FAULT_INJECTED",
                               "detail": f"{f.type}: next {self.fail_remaining} {skill} call(s) will fail"})

    def _injected_failure(self, skill: str, code: str, res: SkillResult) -> bool:
        want = {"NavigateTo": "nav_block", "PickObject": "grasp_fail", "PlaceObject": "place_fail"}[skill]
        if self.fault.type == want and self.fault_fired and self.fail_remaining > 0:
            self.fail_remaining -= 1
            res.success, res.code = False, code
            res.message = f"injected {self.fault.type}"
            return True
        return False

    # ----------------------------------------------------------------- execute
    def execute(self, skill: str, args: dict[str, str]) -> SkillResult:
        res = SkillResult(True)
        w = self.world
        try:
            if skill in ("NavigateTo", "PickObject", "PlaceObject"):
                self._maybe_fire(skill, res)
            if skill == "NavigateTo":
                self._navigate(args["zone"], res)
            elif skill == "PickObject":
                self._pick(args["object"], res)
            elif skill == "PlaceObject":
                self._place(args["object"], args["zone"], res)
            elif skill == "CheckZoneClear":
                ok = w.zone_clear(args["zone"])
                res.success, res.code = ok, "" if ok else "ZONE_OCCUPIED"
                res.message = "" if ok else f"{args['zone']} contains {[o.name for o in w.objects_in(args['zone'])]}"
            elif skill == "CheckHolding":
                ok = w.holding == args["object"]
                res.success, res.code = ok, "" if ok else "OBJECT_NOT_FOUND"
            elif skill == "CheckObjectAt":
                ok = args["object"] in w.objects and w.objects[args["object"]].zone == args["zone"]
                res.success, res.code = ok, "" if ok else "OBJECT_NOT_FOUND"
            elif skill == "Wait":
                res.sim_duration_s = float(args.get("seconds", 1))
            elif skill == "ReportStatus":
                self.log.append(args.get("message", ""))
            elif skill == "RequestHumanHelp":
                self.escalations.append(args.get("reason", ""))
            else:
                res.success, res.code, res.message = False, "PLAN_INVALID", f"unknown skill {skill}"
        except KeyError as e:
            res.success, res.code, res.message = False, "PLAN_INVALID", f"bad argument {e}"
        return res

    # ------------------------------------------------------------------ skills
    def _navigate(self, zone: str, res: SkillResult) -> None:
        w = self.world
        if self._injected_failure("NavigateTo", "NAV_BLOCKED", res):
            res.sim_duration_s = 2.0
            return
        z = w.zones[zone]
        a, b = w.robot_pos, z.access
        for k in w.keepouts.values():
            if segment_hits_rect(a, b, k.rect, 0.0):
                self.safety_violations += 1  # physically crossed a geofence: must never happen with validated plans
                self.log.append(f"SAFETY VIOLATION: {w.robot_zone}->{zone} crosses {k.name}")
        for tz in w.zones.values():
            blockers = [o.name for o in w.objects_in(tz.name)]
            if tz.transit and blockers and tz.name != zone and segment_hits_rect(a, b, tz.rect):
                res.success, res.code = False, "UNEXPECTED_OBSTACLE"
                res.message = f"path to {zone} blocked in {tz.name} by {blockers}"
                res.sim_duration_s = 3.0
                return
        res.sim_duration_s = math.dist(a, b) / ROBOT_SPEED
        w.robot_zone, w.robot_pos = zone, b

    def _pick(self, obj: str, res: SkillResult) -> None:
        w = self.world
        o = w.objects.get(obj)
        if o is None or o.zone is None or o.zone != w.robot_zone:
            res.success, res.code, res.message = False, "OBJECT_NOT_FOUND", f"{obj} not within reach at {w.robot_zone}"
            return
        if w.holding is not None or o.mass > w.payload_kg or not o.graspable:
            res.success, res.code, res.message = False, "GRASP_FAILED", "gripper busy or object not graspable/too heavy"
            return
        res.sim_duration_s = 4.0
        if self._injected_failure("PickObject", "GRASP_FAILED", res):
            return
        o.zone, w.holding = None, obj

    def _place(self, obj: str, zone: str, res: SkillResult) -> None:
        w = self.world
        if w.holding != obj or w.robot_zone != zone:
            res.success, res.code, res.message = False, "PLACE_FAILED", f"not holding {obj} at {zone}"
            return
        res.sim_duration_s = 3.0
        if self._injected_failure("PlaceObject", "PLACE_FAILED", res):
            return
        if len(w.objects_in(zone)) >= w.zones[zone].capacity or not w.zones[zone].placeable:
            res.success, res.code, res.message = False, "ZONE_OCCUPIED", f"{zone} full or not placeable"
            return
        w.objects[obj].zone, w.holding = zone, None

    # --------------------------------------------------------------- evaluation
    def goals_satisfied(self, goals: list[dict[str, Any]]) -> bool:
        from .validator import _holds
        return all(_holds(g, self.world) for g in goals)
