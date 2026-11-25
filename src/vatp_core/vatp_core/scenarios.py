"""Randomised warehouse scenarios: world + instruction + required goals + fault injection.

The same Scenario is consumed by (a) the offline benchmark, (b) the Gazebo
scenario spawner, and (c) the metrics runner, so results are comparable
across sim and symbolic execution.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

import yaml

from .routing import route
from .world import Keepout, World, WorldObject, Zone

FAULT_TYPES = ("none", "obstacle_spawn", "grasp_fail", "nav_block", "place_fail")


@dataclass
class Fault:
    type: str = "none"
    # obstacle_spawn / nav_block : zone in which the obstacle appears
    zone: str | None = None
    # trigger: fire when this skill (by tag) is about to execute the n-th time
    trigger_skill: str | None = None
    trigger_count: int = 1
    # grasp_fail / place_fail: number of consecutive attempts that fail (999 = persistent)
    fail_attempts: int = 1
    obstacle_mass: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class Scenario:
    id: str
    seed: int
    template: str
    instruction: str
    world: World
    required_goals: list[dict[str, Any]]
    fault: Fault = field(default_factory=Fault)

    def to_yaml(self) -> str:
        return yaml.safe_dump({
            "id": self.id, "seed": self.seed, "template": self.template,
            "instruction": self.instruction,
            "required_goals": self.required_goals,
            "fault": self.fault.to_dict(),
            "world": self.world.to_dict(),
        }, sort_keys=False)

    @staticmethod
    def from_yaml(text: str) -> "Scenario":
        d = yaml.safe_load(text)
        return Scenario(d["id"], d["seed"], d["template"], d["instruction"],
                        World.from_dict(d["world"]), d["required_goals"], Fault(**d["fault"]))


# ---------------------------------------------------------------- world base
def base_world(rng: random.Random, name: str) -> World:
    """Warehouse with a keep-out aisle that forces the loading bay to be the only legal corridor."""
    j = lambda v, a=0.25: round(v + rng.uniform(-a, a), 2)  # noqa: E731
    ko_x = j(7.0)
    zones = {
        "dock": Zone("dock", (0, 0, 2, 2), (1.5, 1.0), placeable=False),
        "zone_a": Zone("zone_a", (1, 3.5, 3.5, 5.5), (3.8, 4.5)),
        "staging": Zone("staging", (1, 6.5, 3.5, 8.5), (3.8, 7.5), capacity=3),
        "loading_bay": Zone("loading_bay", (5.5, 0.5, 8.5, 3.5), (5.0, 2.0), capacity=2, transit=True),
        "zone_b": Zone("zone_b", (10.5, 3.0, 13.5, 6.0), (10.0, 4.0)),
    }
    keepouts = {"restricted_aisle": Keepout("restricted_aisle", (ko_x, 4.5, ko_x + 1.0, 9.0))}
    return World(name=name, zones=zones, keepouts=keepouts, objects={},
                 robot_zone="dock", robot_pos=zones["dock"].access, payload_kg=2.0)


# ----------------------------------------------------------------- templates
def _t_conditional_clear_deliver(rng, w):
    blocked = rng.random() < 0.6
    w.objects["crate_1"] = WorldObject("crate_1", round(rng.uniform(1.0, 1.8), 2), "zone_a")
    w.objects["small_box_1"] = WorldObject("small_box_1", round(rng.uniform(0.3, 0.8), 2),
                                           "loading_bay" if blocked else "staging")
    ins = ("Check if the loading bay is clear; if blocked, clear the small box first, "
           "then deliver the crate to Zone B.")
    goals = [{"predicate": "object_at", "args": ["crate_1", "zone_b"]},
             {"predicate": "zone_clear", "args": ["loading_bay"]},
             {"predicate": "gripper_empty", "args": []}]
    return ins, goals


def _t_simple_delivery(rng, w):
    w.objects["crate_1"] = WorldObject("crate_1", round(rng.uniform(1.0, 1.8), 2), "zone_a")
    return "Deliver the crate from zone A to zone B.", [
        {"predicate": "object_at", "args": ["crate_1", "zone_b"]},
        {"predicate": "gripper_empty", "args": []}]


def _t_two_item(rng, w):
    w.objects["crate_1"] = WorldObject("crate_1", round(rng.uniform(1.0, 1.8), 2), "zone_a")
    w.objects["small_box_1"] = WorldObject("small_box_1", round(rng.uniform(0.3, 0.8), 2), "loading_bay")
    return "Move the small box to staging, deliver the crate to Zone B, then report status.", [
        {"predicate": "object_at", "args": ["small_box_1", "staging"]},
        {"predicate": "object_at", "args": ["crate_1", "zone_b"]},
        {"predicate": "gripper_empty", "args": []}]


def _t_geofence(rng, w):
    w.objects["crate_1"] = WorldObject("crate_1", round(rng.uniform(1.0, 1.8), 2), "staging")
    return ("Bring the crate from staging to Zone B. The restricted aisle is off limits — "
            "never drive through or next to it."), [
        {"predicate": "object_at", "args": ["crate_1", "zone_b"]},
        {"predicate": "gripper_empty", "args": []}]


TEMPLATES = {
    "conditional_clear_deliver": _t_conditional_clear_deliver,
    "simple_delivery": _t_simple_delivery,
    "two_item": _t_two_item,
    "geofence": _t_geofence,
}


# -------------------------------------------------------------------- faults
def _fault_for(rng, template: str, w: World, kind: str) -> Fault:
    if kind == "none":
        return Fault()
    if kind == "obstacle_spawn":  # unexpected box appears in the bay as the robot heads there
        return Fault("obstacle_spawn", "loading_bay", "NavigateTo", 1, obstacle_mass=round(rng.uniform(0.3, 0.8), 2))
    if kind == "nav_block":
        return Fault("nav_block", "loading_bay", "NavigateTo", 2, fail_attempts=2)
    if kind == "grasp_fail":
        return Fault("grasp_fail", None, "PickObject", 1, fail_attempts=rng.choice([2, 3]))
    if kind == "place_fail":
        return Fault("place_fail", None, "PlaceObject", 1, fail_attempts=2)
    raise ValueError(kind)


# fault schedule: first 8 scenarios are nominal; rest cycle through fault kinds
_SCHEDULE = ["none"] * 8 + ["obstacle_spawn", "grasp_fail", "obstacle_spawn", "grasp_fail",
                            "nav_block", "place_fail", "grasp_fail", "obstacle_spawn",
                            "nav_block", "place_fail", "obstacle_spawn", "grasp_fail"]
_TEMPLATE_CYCLE = ["conditional_clear_deliver", "simple_delivery", "two_item", "geofence"]


def make_scenario(index: int, seed: int = 0) -> Scenario:
    rng = random.Random(f"{seed}:{index}")
    tmpl = _TEMPLATE_CYCLE[index % len(_TEMPLATE_CYCLE)]
    w = base_world(rng, f"scenario_{index:02d}")
    instruction, goals = TEMPLATES[tmpl](rng, w)
    kind = _SCHEDULE[index % len(_SCHEDULE)]
    fault = _fault_for(rng, tmpl, w, kind)
    # obstacle_spawn / nav_block need a navigation to the bay to ever trigger;
    # every template reaches the bay (it is the only legal corridor to zone_b).
    sc = Scenario(f"s{index:02d}", seed, tmpl, instruction, w, goals, fault)
    assert route(w, w.robot_pos, "zone_b") is not None, "scenario must be solvable"
    return sc


def generate_suite(n: int = 20, seed: int = 0) -> list[Scenario]:
    return [make_scenario(i, seed) for i in range(n)]
