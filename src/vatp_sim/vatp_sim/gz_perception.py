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


# ---------------------------------------------------------------- world control (gz services)
def _gz_service(service: str, reqtype: str, reptype: str, req: str, timeout_ms: int = 5000) -> bool:
    r = subprocess.run(["gz", "service", "-s", service, "--reqtype", reqtype, "--reptype", reptype,
                        "--timeout", str(timeout_ms), "--req", req], capture_output=True, text=True, timeout=timeout_ms / 1000 + 5)
    return "true" in r.stdout


def spawn_model(sdf: str) -> bool:
    one_line = " ".join(sdf.split()).replace("\\", "\\\\").replace('"', '\\"')
    return _gz_service(f"/world/{WORLD_NAME}/create", "gz.msgs.EntityFactory", "gz.msgs.Boolean", f'sdf: "{one_line}"')


def remove_model(name: str) -> bool:
    return _gz_service(f"/world/{WORLD_NAME}/remove", "gz.msgs.Entity", "gz.msgs.Boolean", f'name: "{name}" type: MODEL')


def set_pose(name: str, x: float, y: float, z: float, yaw: float = 0.0) -> bool:
    import math
    req = (f'name: "{name}" position {{x: {x} y: {y} z: {z}}} '
           f'orientation {{z: {math.sin(yaw / 2)} w: {math.cos(yaw / 2)}}}')
    return _gz_service(f"/world/{WORLD_NAME}/set_pose", "gz.msgs.Pose", "gz.msgs.Boolean", req)
