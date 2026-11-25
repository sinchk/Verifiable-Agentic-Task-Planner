"""Symbolic world model: zones, keep-out geofences, objects, robot.

This is the *belief state* the planner reasons over and the validator
symbolically executes behavior trees against. It is deliberately small,
immutable-by-convention (``copy()`` before mutation) and YAML-serialisable so
the Gazebo scenario generator, the LLM prompt and the validator share one
representation.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

import yaml

from .geometry import Point, Rect, rect_center


@dataclass
class Zone:
    name: str
    rect: Rect
    access: Point  # where the robot parks to work on this zone
    navigable: bool = True
    placeable: bool = True
    capacity: int = 2
    transit: bool = False  # robot routes pass THROUGH this zone; objects inside obstruct the path

    def to_dict(self) -> dict[str, Any]:
        return {
            "rect": list(self.rect),
            "access": list(self.access),
            "navigable": self.navigable,
            "placeable": self.placeable,
            "capacity": self.capacity,
            "transit": self.transit,
        }


@dataclass
class Keepout:
    """Hard geofence: robot must neither enter nor cross it."""

    name: str
    rect: Rect

    def to_dict(self) -> dict[str, Any]:
        return {"rect": list(self.rect)}


@dataclass
class WorldObject:
    name: str
    mass: float
    zone: str | None  # None while held
    graspable: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"mass": self.mass, "zone": self.zone, "graspable": self.graspable}


@dataclass
class World:
    name: str
    zones: dict[str, Zone]
    keepouts: dict[str, Keepout]
    objects: dict[str, WorldObject]
    robot_zone: str
    robot_pos: Point
    holding: str | None = None
    payload_kg: float = 2.0
    path_margin: float = 0.3  # clearance kept from keep-outs along straight paths

    # ------------------------------------------------------------------ utils
    def copy(self) -> "World":
        return copy.deepcopy(self)

    def objects_in(self, zone: str) -> list[WorldObject]:
        return [o for o in self.objects.values() if o.zone == zone]

    def zone_clear(self, zone: str) -> bool:
        return not self.objects_in(zone)

    def state_key(self) -> tuple:
        """Hashable fingerprint for de-duplicating symbolic states."""
        return (
            self.robot_zone,
            self.holding,
            tuple(sorted((o.name, o.zone) for o in self.objects.values())),
        )

    # -------------------------------------------------------------- (de)serial
    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "robot": {
                "zone": self.robot_zone,
                "pos": list(self.robot_pos),
                "holding": self.holding,
                "payload_kg": self.payload_kg,
            },
            "zones": {n: z.to_dict() for n, z in self.zones.items()},
            "keepouts": {n: k.to_dict() for n, k in self.keepouts.items()},
            "objects": {n: o.to_dict() for n, o in self.objects.items()},
        }

    def to_yaml(self) -> str:
        return yaml.safe_dump(self.to_dict(), sort_keys=False)

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "World":
        zones = {
            n: Zone(
                n,
                tuple(z["rect"]),
                tuple(z["access"]) if "access" in z else rect_center(tuple(z["rect"])),
                z.get("navigable", True),
                z.get("placeable", True),
                z.get("capacity", 2),
                z.get("transit", False),
            )
            for n, z in d["zones"].items()
        }
        keepouts = {n: Keepout(n, tuple(k["rect"])) for n, k in d.get("keepouts", {}).items()}
        objects = {
            n: WorldObject(n, o["mass"], o.get("zone"), o.get("graspable", True))
            for n, o in d.get("objects", {}).items()
        }
        r = d["robot"]
        pos = tuple(r["pos"]) if "pos" in r else zones[r["zone"]].access
        return World(
            name=d.get("name", "world"),
            zones=zones,
            keepouts=keepouts,
            objects=objects,
            robot_zone=r["zone"],
            robot_pos=pos,
            holding=r.get("holding"),
            payload_kg=r.get("payload_kg", 2.0),
        )

    @staticmethod
    def from_yaml(text: str) -> "World":
        return World.from_dict(yaml.safe_load(text))

    # ------------------------------------------------------------- LLM prompt
    def describe(self) -> str:
        """Deterministic textual scene graph handed to the planner."""
        lines = [f"SCENE '{self.name}'"]
        lines.append(
            f"robot: at zone '{self.robot_zone}' pos=({self.robot_pos[0]:.1f},{self.robot_pos[1]:.1f}), "
            f"holding={self.holding or 'nothing'}, payload_limit={self.payload_kg}kg"
        )
        lines.append("zones:")
        for z in self.zones.values():
            flags = []
            if not z.navigable:
                flags.append("NOT-NAVIGABLE")
            if not z.placeable:
                flags.append("NO-PLACING")
            if z.transit:
                flags.append("TRANSIT-CORRIDOR(routes cross it; must be empty to pass)")
            lines.append(
                f"  - {z.name}: rect={tuple(round(v, 2) for v in z.rect)} "
                f"access=({z.access[0]:.1f},{z.access[1]:.1f}) {' '.join(flags)}".rstrip()
            )
        lines.append("keep-out geofences (never enter or cross, clearance "
                     f"{self.path_margin} m):")
        for k in self.keepouts.values():
            lines.append(f"  - {k.name}: rect={tuple(round(v, 2) for v in k.rect)}")
        lines.append("objects:")
        for o in self.objects.values():
            where = f"in '{o.zone}'" if o.zone else "held"
            g = "" if o.graspable else " NOT-GRASPABLE"
            lines.append(f"  - {o.name}: mass={o.mass}kg {where}{g}")
        return "\n".join(lines)
