"""Closed-form IK for the VATP arm (planar after the base pan joint), top-down grasps.

Geometry (metres, robot/footprint frame; angles positive = pitching DOWN about +y):
  pan axis at x=ARM_X, height PIVOT_Z; shoulder pitch pivot R0 = 0.08 ahead of the pan axis;
  upper arm L1, forearm+wrist-1 L2 (forearm 0.36 + 0.07 to the wrist-pitch joint), tool length TOOL
  (j5->j6 .07 + j6->mount .05 + mount->grasp_frame .14) along the final pitch direction.
Joint order: arm_joint_1..6 = pan, shoulder, elbow, wrist-roll-1, wrist-pitch, wrist-roll-2.
"""
from __future__ import annotations

import math

ARM_X = 0.16
R0 = 0.08  # shoulder pitch pivot ahead of the PAN axis (which itself is ARM_X ahead of the footprint origin)
PIVOT_Z = 0.23
L1, L2, TOOL = 0.38, 0.43, 0.26
LIMITS = [(-3.0, 3.0), (-2.1, 1.7), (-2.6, 2.6), (-3.0, 3.0), (-2.2, 2.2), (-3.0, 3.0)]
# Stowed: upper arm raised, forearm folded back over the base; max reach 0.57 m ahead at >=0.25 m height
HOME = [0.0, -1.6, 2.6, 0.0, -2.2, 0.0]
# finger joints: 0 = fully open (inner gap 0.174 m); positive = closing; contact with a 0.15 m crate at ~0.012
GRIPPER_OPEN, GRIPPER_CLOSED = 0.0, 0.05


class Unreachable(ValueError):
    pass


def topdown_ik(x: float, y: float, z: float, roll: float = 0.0) -> list[float]:
    """Joint angles putting grasp_frame at (x, y, z) (robot frame) with the gripper pointing straight down."""
    xa = x - ARM_X  # the pan axis is ARM_X ahead of the footprint origin
    pan = math.atan2(y, xa)
    R = math.hypot(xa, y)
    px = R - R0
    # 2-link target in (forward, downward) coordinates: the wrist-pitch joint sits TOOL above the grasp frame
    tz = PIVOT_Z - (z + TOOL)  # >0 means the wrist joint is below the shoulder pivot
    d2 = px * px + tz * tz
    c3 = (d2 - L1 * L1 - L2 * L2) / (2 * L1 * L2)
    if abs(c3) > 1.0:
        raise Unreachable(f"target out of reach (R={R:.2f}, z={z:.2f})")
    a3 = math.acos(c3)  # elbow-up solution (positive bend)
    a2 = math.atan2(tz, px) - math.atan2(L2 * math.sin(a3), L1 + L2 * math.cos(a3))
    a5 = math.pi / 2 - a2 - a3
    q = [pan, a2, a3, 0.0, a5, roll + pan]  # +pan keeps the closing axis aligned with the robot axes (verified in sim TF)
    for v, (lo, hi), i in zip(q, LIMITS, range(6)):
        if not lo <= v <= hi:
            raise Unreachable(f"joint {i + 1} = {v:.2f} outside [{lo}, {hi}]")
    return q


def forward(q: list[float]) -> tuple[float, float, float]:
    """Grasp-frame position (robot frame) for joints with roll joints at 0 (verification helper)."""
    pan, a2, a3, _, a5, _ = q
    a23, phi = a2 + a3, a2 + a3 + a5
    r = R0 + L1 * math.cos(a2) + L2 * math.cos(a23) + TOOL * math.cos(phi)
    z = PIVOT_Z - (L1 * math.sin(a2) + L2 * math.sin(a23) + TOOL * math.sin(phi))
    return ARM_X + r * math.cos(pan), r * math.sin(pan), z
