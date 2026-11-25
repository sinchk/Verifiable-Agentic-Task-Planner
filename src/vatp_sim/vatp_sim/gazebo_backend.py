"""Gazebo skill backend: same `execute(skill, args) -> SkillResult` contract as SymbolicSim.

  NavigateTo      Nav2 NavigateToPose (hard geofences live in the static map)
  Check*          perception (gz pose snapshots) -> symbolic belief
  PickObject      perception-driven top-down grasp, verified by lifting the object
  PlaceObject     free-slot placement, verified by the object resting in the zone
  fault injection  real obstacle models are spawned; grasp/place/nav failures are injected at the skill level
"""
from __future__ import annotations

import math
import time

from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
from rclpy.time import Time
from tf2_ros import Buffer, TransformListener

from vatp_core.geometry import segment_hits_rect
from vatp_core.scenarios import Fault, Scenario
from vatp_core.symbolic_sim import SkillResult
from vatp_core.world import World, WorldObject

from . import gz_perception as gzp
from .arm_control import ArmControl, world_to_robot
from .arm_kinematics import HOME
from .layout import access_yaw, free_slot, slot_xy, zone_of_xy
from .world_gen import OBJECT_STYLE, grasp_height, object_kind, object_model_sdf

NAV_TIMEOUT_S = 120.0
CARRIED_Z = 0.30  # an object whose centre is above this is considered lifted/carried


class GazeboBackend:
    def __init__(self, node, callback_group):
        self.node = node
        self.buf = Buffer()
        TransformListener(self.buf, node)
        self.arm = ArmControl(node)
        self.nav = ActionClient(node, NavigateToPose, "navigate_to_pose", callback_group=callback_group)
        self.scenario: Scenario | None = None
        self.holding: str | None = None
        self.robot_zone = "dock"
        self.counts: dict[str, int] = {}
        self.fault_fired = False
        self.fail_remaining = 0
        self.safety_violations = 0
        self.escalations: list[str] = []
        self.fault = Fault()

    # ------------------------------------------------------------------ reset
    def load(self, sc: Scenario) -> None:
        for name in list(gzp.object_poses()):
            gzp.remove_model(name)
        used: dict[str, int] = {}
        for o in sc.world.objects.values():
            if o.zone is None:
                continue
            k = used.get(o.zone, 0)
            used[o.zone] = k + 1
            gzp.spawn_model(object_model_sdf(o.name, o.mass, slot_xy(sc.world, o.zone, k)))
        dock = sc.world.zones["dock"].access
        gzp.set_pose("vatp_amr", dock[0], dock[1], 0.02, 0.0)
        self.arm.gripper(0.0, 0.5)
        self.arm.move(HOME, 2.0)
        self.scenario, self.fault = sc, sc.fault
        self.holding, self.robot_zone = None, "dock"
        self.counts, self.fault_fired, self.fail_remaining = {}, False, 0
        self.safety_violations, self.escalations = 0, []
        time.sleep(1.5)

    # -------------------------------------------------------------- perception
    def robot_xy(self) -> tuple[float, float]:
        t = self.buf.lookup_transform("map", "base_footprint", Time()).transform.translation
        return t.x, t.y

    def perceive(self) -> World:
        w = self.scenario.world.copy()
        w.objects = {}
        for name, (x, y, z) in gzp.object_poses().items():
            mass = self.scenario.world.objects[name].mass if name in self.scenario.world.objects else self.fault.obstacle_mass
            zone = None if (name == self.holding or z > CARRIED_Z) else zone_of_xy(w, x, y, 0.15)
            w.objects[name] = WorldObject(name, mass, zone)
        rx, ry = self.robot_xy()
        near = min(w.zones.values(), key=lambda z: math.dist(z.access, (rx, ry)))
        self.robot_zone = near.name if math.dist(near.access, (rx, ry)) < 0.5 else self.robot_zone
        w.robot_zone, w.robot_pos, w.holding = self.robot_zone, (rx, ry), self.holding
        return w

    def world_dict(self) -> dict:
        d = self.perceive().to_dict()
        d["sim_stats"] = {"safety_violations": self.safety_violations, "fault_fired": self.fault_fired,
                          "escalations": list(self.escalations), "fault": self.fault.type}
        return d

    # ------------------------------------------------------------------ faults
    def _fire(self, skill: str, res: SkillResult) -> None:
        f = self.fault
        self.counts[skill] = self.counts.get(skill, 0) + 1
        if f.type == "none" or self.fault_fired or f.trigger_skill != skill or self.counts[skill] != f.trigger_count:
            return
        self.fault_fired = True
        w = self.scenario.world
        if f.type == "obstacle_spawn":
            gzp.spawn_model(object_model_sdf("obstacle_1", f.obstacle_mass, slot_xy(w, f.zone, 0)))
            res.events.append({"type": "FAULT_INJECTED", "detail": f"obstacle_1 appeared in {f.zone}"})
        else:
            self.fail_remaining = max(1, f.fail_attempts)
            res.events.append({"type": "FAULT_INJECTED", "detail": f"{f.type}: next {self.fail_remaining} {skill} call(s) fail"})

    def _injected(self, skill: str) -> bool:
        want = {"NavigateTo": "nav_block", "PickObject": "grasp_fail", "PlaceObject": "place_fail"}[skill]
        if self.fault.type == want and self.fault_fired and self.fail_remaining > 0:
            self.fail_remaining -= 1
            return True
        return False

    # ----------------------------------------------------------------- execute
    def execute(self, skill: str, args: dict[str, str]) -> SkillResult:
        res = SkillResult(True)
        try:
            if skill in ("NavigateTo", "PickObject", "PlaceObject"):
                self._fire(skill, res)
            if skill == "NavigateTo":
                self._navigate(args["zone"], res)
            elif skill == "PickObject":
                self._pick(args["object"], res)
            elif skill == "PlaceObject":
                self._place(args["object"], args["zone"], res)
            elif skill == "CheckZoneClear":
                w = self.perceive()
                ok = w.zone_clear(args["zone"])
                res.success, res.code = ok, "" if ok else "ZONE_OCCUPIED"
                res.message = "" if ok else f"{args['zone']} contains {[o.name for o in w.objects_in(args['zone'])]}"
            elif skill == "CheckHolding":
                ok = self.holding == args["object"]
                res.success, res.code = ok, "" if ok else "OBJECT_NOT_FOUND"
            elif skill == "CheckObjectAt":
                w = self.perceive()
                ok = args["object"] in w.objects and w.objects[args["object"]].zone == args["zone"]
                res.success, res.code = ok, "" if ok else "OBJECT_NOT_FOUND"
            elif skill == "Wait":
                time.sleep(float(args.get("seconds", 1)))
            elif skill == "RequestHumanHelp":
                self.escalations.append(args.get("reason", ""))
            elif skill != "ReportStatus":
                res.success, res.code, res.message = False, "PLAN_INVALID", f"unknown skill {skill}"
        except KeyError as e:
            res.success, res.code, res.message = False, "PLAN_INVALID", f"bad argument {e}"
        return res

    # ------------------------------------------------------------------ skills
    def _navigate(self, zone: str, res: SkillResult) -> None:
        w = self.perceive()
        z = w.zones[zone]
        if self._injected("NavigateTo"):
            res.success, res.code, res.message = False, "NAV_BLOCKED", "injected nav_block"
            return
        for tz in w.zones.values():  # same transit-corridor semantics as the symbolic backend
            blockers = [o.name for o in w.objects_in(tz.name)]
            if tz.transit and blockers and tz.name != zone and segment_hits_rect(w.robot_pos, z.access, tz.rect):
                res.success, res.code = False, "UNEXPECTED_OBSTACLE"
                res.message = f"path to {zone} blocked in {tz.name} by {blockers}"
                return
        yaw = access_yaw(w, zone)
        goal = NavigateToPose.Goal()
        goal.pose = PoseStamped()
        goal.pose.header.frame_id = "map"
        goal.pose.pose.position.x, goal.pose.pose.position.y = z.access
        goal.pose.pose.orientation.z, goal.pose.pose.orientation.w = math.sin(yaw / 2), math.cos(yaw / 2)
        if not self.nav.wait_for_server(timeout_sec=10.0):
            res.success, res.code, res.message = False, "NAV_TIMEOUT", "Nav2 not available"
            return
        gf = self.nav.send_goal_async(goal)
        t_end = time.time() + 15
        while not gf.done() and time.time() < t_end:
            time.sleep(0.05)
        gh = gf.result() if gf.done() else None
        if gh is None or not gh.accepted:
            res.success, res.code, res.message = False, "NAV_BLOCKED", "Nav2 rejected the goal"
            return
        rf = gh.get_result_async()
        t_end = time.time() + NAV_TIMEOUT_S
        while not rf.done() and time.time() < t_end:
            time.sleep(0.1)
        if not rf.done():
            gh.cancel_goal_async()
            res.success, res.code, res.message = False, "NAV_TIMEOUT", f"no result in {NAV_TIMEOUT_S}s"
            return
        if rf.result().status != 4:  # SUCCEEDED
            res.success, res.code, res.message = False, "NAV_BLOCKED", f"Nav2 status {rf.result().status}"
            return
        self.robot_zone = zone

    def _pick(self, obj: str, res: SkillResult) -> None:
        w = self.perceive()
        o = w.objects.get(obj)
        if o is None or o.zone is None or o.zone != w.robot_zone:
            res.success, res.code, res.message = False, "OBJECT_NOT_FOUND", f"{obj} not within reach at {w.robot_zone}"
            return
        if self.holding is not None or o.mass > w.payload_kg:
            res.success, res.code, res.message = False, "GRASP_FAILED", "gripper busy or object too heavy"
            return
        x, y, z = gzp.object_poses()[obj]
        rx, ry = world_to_robot(self.buf, x, y)
        zg = grasp_height(obj, z)
        if self._injected("PickObject"):  # a realistic miss: go through the motions, never close
            self.arm.open()
            self.arm.move(HOME, 1.0)
            res.success, res.code, res.message = False, "GRASP_FAILED", "injected grasp_fail"
            return
        self.arm.pick(rx, ry, zg)
        z_after = gzp.object_poses().get(obj, (0, 0, 0))[2]
        if z_after < CARRIED_Z:
            self.arm.open()
            res.success, res.code, res.message = False, "GRASP_FAILED", f"{obj} not lifted (z={z_after:.2f})"
            return
        self.holding = obj

    def _place(self, obj: str, zone: str, res: SkillResult) -> None:
        w = self.perceive()
        if self.holding != obj or w.robot_zone != zone:
            res.success, res.code, res.message = False, "PLACE_FAILED", f"not holding {obj} at {zone}"
            return
        if len(w.objects_in(zone)) >= w.zones[zone].capacity or not w.zones[zone].placeable:
            res.success, res.code, res.message = False, "ZONE_OCCUPIED", f"{zone} full or not placeable"
            return
        if self._injected("PlaceObject"):
            res.success, res.code, res.message = False, "PLACE_FAILED", "injected place_fail"
            return
        occupied = [(p[0], p[1]) for n, p in gzp.object_poses().items() if n != obj]
        tx, ty = slot_xy(w, zone, free_slot(w, zone, occupied))
        rx, ry = world_to_robot(self.buf, tx, ty)
        h = OBJECT_STYLE[object_kind(obj)][0][2]
        self.arm.place(rx, ry, grasp_height(obj, h / 2))
        px, py, pz = gzp.object_poses()[obj]
        if pz > CARRIED_Z or zone_of_xy(w, px, py, 0.15) != zone:
            res.success, res.code, res.message = False, "PLACE_FAILED", f"{obj} ended at ({px:.2f},{py:.2f},{pz:.2f})"
            return
        self.holding = None
