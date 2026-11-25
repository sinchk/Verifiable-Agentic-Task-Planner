"""Scenario -> Gazebo Harmonic SDF (world, object models) and Nav2 occupancy map."""
from __future__ import annotations

import math
from pathlib import Path

from vatp_core.scenarios import Scenario
from vatp_core.world import World, WorldObject

from .layout import slot_xy

WORLD_NAME = "vatp_warehouse"
ARENA = (-0.5, -0.5, 14.5, 9.5)  # xmin ymin xmax ymax (outer wall centre-lines)

# (size x y z, rgba) per object kind
OBJECT_STYLE = {
    "crate": ((0.15, 0.15, 0.20), "0.55 0.35 0.15 1"),
    "small_box": ((0.10, 0.10, 0.10), "0.85 0.75 0.2 1"),
    "obstacle": ((0.12, 0.12, 0.12), "0.85 0.15 0.15 1"),
}


def object_kind(name: str) -> str:
    return "crate" if name.startswith("crate") else "obstacle" if name.startswith("obstacle") else "small_box"


def object_model_sdf(name: str, mass: float, xy: tuple[float, float], yaw: float = 0.0) -> str:
    (sx, sy, sz), rgba = OBJECT_STYLE[object_kind(name)]
    ixx, iyy, izz = (mass / 12 * (sy**2 + sz**2), mass / 12 * (sx**2 + sz**2), mass / 12 * (sx**2 + sy**2))
    return f"""<sdf version="1.9"><model name="{name}">
  <pose>{xy[0]:.3f} {xy[1]:.3f} {sz / 2 + 0.002:.3f} 0 0 {yaw:.3f}</pose>
  <link name="link">
    <inertial><mass>{mass}</mass><inertia><ixx>{ixx:.6f}</ixx><iyy>{iyy:.6f}</iyy><izz>{izz:.6f}</izz></inertia></inertial>
    <collision name="c"><geometry><box><size>{sx} {sy} {sz}</size></box></geometry>
      <surface><friction><ode><mu>1.5</mu><mu2>1.5</mu2></ode></friction></surface></collision>
    <visual name="v"><geometry><box><size>{sx} {sy} {sz}</size></box></geometry>
      <material><ambient>{rgba}</ambient><diffuse>{rgba}</diffuse></material></visual>
  </link></model></sdf>"""


def _box(name, x, y, z, sx, sy, sz, rgba, collide=True, static=True):
    col = f'<collision name="c"><geometry><box><size>{sx} {sy} {sz}</size></box></geometry></collision>' if collide else ""
    return (f'<model name="{name}"><static>{str(static).lower()}</static><pose>{x} {y} {z} 0 0 0</pose><link name="l">{col}'
            f'<visual name="v"><geometry><box><size>{sx} {sy} {sz}</size></box></geometry>'
            f'<material><ambient>{rgba}</ambient><diffuse>{rgba}</diffuse></material></visual></link></model>')


ZONE_COLOR = {"dock": "0.5 0.5 0.55 1", "zone_a": "0.3 0.5 0.9 1", "loading_bay": "0.95 0.8 0.2 1",
              "staging": "0.3 0.8 0.4 1", "zone_b": "0.7 0.4 0.85 1"}


def world_sdf(w: World, with_objects: bool = True) -> str:
    x0, y0, x1, y1 = ARENA
    parts = []
    t = 0.2
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    for nm, x, y, sx, sy in [("wall_s", cx, y0, x1 - x0 + t, t), ("wall_n", cx, y1, x1 - x0 + t, t),
                             ("wall_w", x0, cy, t, y1 - y0), ("wall_e", x1, cy, t, y1 - y0)]:
        parts.append(_box(nm, x, y, 0.3, sx, sy, 0.6, "0.6 0.6 0.6 1"))
    for z in w.zones.values():
        r = z.rect
        parts.append(_box(f"zone_{z.name}", (r[0] + r[2]) / 2, (r[1] + r[3]) / 2, 0.003, r[2] - r[0], r[3] - r[1], 0.006,
                          ZONE_COLOR.get(z.name, "0.7 0.7 0.7 1"), collide=False))
    for k in w.keepouts.values():
        r = k.rect
        parts.append(_box(f"keepout_{k.name}", (r[0] + r[2]) / 2, (r[1] + r[3]) / 2, 0.004, r[2] - r[0], r[3] - r[1], 0.008,
                          "0.9 0.1 0.1 1", collide=False))
        # physical low barrier along the keep-out so the lidar/costmap also sees it
        parts.append(_box(f"barrier_{k.name}", (r[0] + r[2]) / 2, (r[1] + r[3]) / 2, 0.15, r[2] - r[0], r[3] - r[1], 0.3,
                          "0.9 0.1 0.1 0.5"))
    objs = ""
    if with_objects:
        used: dict[str, int] = {}
        for o in w.objects.values():
            if o.zone is None:
                continue
            k = used.get(o.zone, 0)
            used[o.zone] = k + 1
            objs += object_model_sdf(o.name, o.mass, slot_xy(w, o.zone, k)).replace('<sdf version="1.9">', "").replace("</sdf>", "")
    return f"""<?xml version="1.0"?>
<sdf version="1.9">
  <world name="{WORLD_NAME}">
    <physics name="p" type="ode"><max_step_size>0.004</max_step_size><real_time_factor>1.0</real_time_factor></physics>
    <plugin filename="gz-sim-physics-system" name="gz::sim::systems::Physics"/>
    <plugin filename="gz-sim-user-commands-system" name="gz::sim::systems::UserCommands"/>
    <plugin filename="gz-sim-scene-broadcaster-system" name="gz::sim::systems::SceneBroadcaster"/>
    <plugin filename="gz-sim-sensors-system" name="gz::sim::systems::Sensors"><render_engine>ogre2</render_engine></plugin>
    <plugin filename="gz-sim-contact-system" name="gz::sim::systems::Contact"/>
    <gravity>0 0 -9.81</gravity>
    <light type="directional" name="sun"><cast_shadows>false</cast_shadows><pose>5 5 10 0 0 0</pose>
      <diffuse>0.9 0.9 0.9 1</diffuse><specular>0.2 0.2 0.2 1</specular><direction>-0.4 0.3 -1</direction></light>
    <model name="ground"><static>true</static><link name="l">
      <collision name="c"><geometry><plane><normal>0 0 1</normal><size>30 30</size></plane></geometry>
        <surface><friction><ode><mu>1.0</mu><mu2>1.0</mu2></ode></friction></surface></collision>
      <visual name="v"><geometry><plane><normal>0 0 1</normal><size>30 30</size></plane></geometry>
        <material><ambient>0.35 0.35 0.38 1</ambient><diffuse>0.35 0.35 0.38 1</diffuse></material></visual></link></model>
    {''.join(parts)}
    <model name="overview_cam"><static>true</static><pose>7.0 -6.5 9.5 0 0.66 1.5708</pose><link name="l">
      <sensor name="cam" type="camera"><topic>/overview_cam/image</topic><update_rate>5</update_rate><always_on>true</always_on>
        <camera><horizontal_fov>1.25</horizontal_fov><image><width>1280</width><height>720</height><format>R8G8B8</format></image>
        <clip><near>0.1</near><far>60</far></clip></camera></sensor></link></model>
    {objs}
  </world>
</sdf>"""


def write_nav_map(w: World, out_dir: Path, name: str = "warehouse", res: float = 0.05) -> Path:
    """Static occupancy map: free arena, walls and keep-out geofences occupied (hard geofence at runtime)."""
    x0, y0, x1, y1 = ARENA
    W, H = int((x1 - x0) / res), int((y1 - y0) / res)
    img = bytearray([254] * (W * H))

    def fill(rx0, ry0, rx1, ry1, v=0):
        for j in range(max(0, int((ry0 - y0) / res)), min(H, int((ry1 - y0) / res) + 1)):
            row = (H - 1 - j) * W
            for i in range(max(0, int((rx0 - x0) / res)), min(W, int((rx1 - x0) / res) + 1)):
                img[row + i] = v

    t = 0.15
    fill(x0, y0, x1, y0 + t); fill(x0, y1 - t, x1, y1); fill(x0, y0, x0 + t, y1); fill(x1 - t, y0, x1, y1)
    for k in w.keepouts.values():
        fill(*k.rect)
    out_dir.mkdir(parents=True, exist_ok=True)
    pgm = out_dir / f"{name}.pgm"
    pgm.write_bytes(f"P5\n{W} {H}\n255\n".encode() + bytes(img))
    yml = out_dir / f"{name}.yaml"
    yml.write_text(f"image: {pgm.name}\nmode: trinary\nresolution: {res}\norigin: [{x0}, {y0}, 0.0]\n"
                   f"negate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.25\n")
    return yml


def grasp_height(name: str, z_center: float) -> float:
    """Grasp-frame height for a top-down grasp.

    The palm underside is 0.06 m above the grasp frame and the fingertips 0.07 m below it, so the
    palm clears the object top when grasp_z >= top - 0.05, and fingertips stay above the floor when
    grasp_z >= 0.09 (a 2 cm margin).
    """
    h = OBJECT_STYLE[object_kind(name)][0][2]
    return max(0.09, z_center + h / 2 - 0.04)
