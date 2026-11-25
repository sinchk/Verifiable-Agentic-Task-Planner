"""World perception through `gz topic` snapshots (no Gazebo Python bindings are available).

The scene broadcaster publishes every dynamic entity's pose with its NAME (the ROS bridge drops names),
so a one-shot `gz topic -e -n 1` read is used at skill boundaries — a perception *event*, not a stream.
"""
from __future__ import annotations

import re
import subprocess

from .world_gen import WORLD_NAME

_ENTITY = re.compile(r'pose \{\s*name: "([^"]+)"(.*?)(?=\n\s*pose \{|\Z)', re.S)
_VAL = re.compile(r"\b([xyz]):\s*([-+0-9.eE]+)")


def object_poses(prefixes=("crate", "small_box", "obstacle"), timeout: float = 8.0) -> dict[str, tuple[float, float, float]]:
    """World-frame (x, y, z) of every object model currently in the simulation."""
    out = subprocess.run(
        ["gz", "topic", "-e", "-t", f"/world/{WORLD_NAME}/dynamic_pose/info", "-n", "1"],
        capture_output=True, text=True, timeout=timeout).stdout
    poses: dict[str, tuple[float, float, float]] = {}
    for m in _ENTITY.finditer(out):
        name, body = m.group(1), m.group(2)
        if not name.startswith(prefixes):
            continue
        pos = body.split("orientation")[0]
        v = dict(_VAL.findall(pos))
        poses[name] = (float(v.get("x", 0)), float(v.get("y", 0)), float(v.get("z", 0)))
    return poses
