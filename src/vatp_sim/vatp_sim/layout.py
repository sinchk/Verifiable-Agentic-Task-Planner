"""Geometry shared by world generation, Nav2 goals, grasp planning and perception.

Every zone has an *access pose* (where the robot parks, facing the zone centre) and a few
object *slots* in front of the robot, so a symbolic ``PickObject(x)`` maps to a repeatable
physical grasp and ``PlaceObject(x, zone)`` to a free slot.
"""
from __future__ import annotations

import math

from vatp_core.geometry import rect_center
from vatp_core.world import World

REACH = 0.62  # metres from the access pose to the first slot (inside arm reach)
LATERAL = 0.30  # spacing between slots


def access_yaw(w: World, zone: str) -> float:
    z = w.zones[zone]
    c = rect_center(z.rect)
    return math.atan2(c[1] - z.access[1], c[0] - z.access[0])


def slot_xy(w: World, zone: str, k: int) -> tuple[float, float]:
    """k-th slot of a zone: k=0 straight ahead, then alternating left/right."""
    z = w.zones[zone]
    yaw = access_yaw(w, zone)
    lat = [0.0, LATERAL, -LATERAL, 2 * LATERAL][k % 4]
    fwd = REACH + (0.0 if k < 3 else 0.2)
    return (z.access[0] + fwd * math.cos(yaw) - lat * math.sin(yaw),
            z.access[1] + fwd * math.sin(yaw) + lat * math.cos(yaw))


def free_slot(w: World, zone: str, occupied_xy: list[tuple[float, float]]) -> int:
    for k in range(4):
        sx, sy = slot_xy(w, zone, k)
        if all(math.dist((sx, sy), o) > 0.18 for o in occupied_xy):
            return k
    return 0


def zone_of_xy(w: World, x: float, y: float, margin: float = 0.25) -> str | None:
    for z in w.zones.values():
        r = z.rect
        if r[0] - margin <= x <= r[2] + margin and r[1] - margin <= y <= r[3] + margin:
            return z.name
    return None
