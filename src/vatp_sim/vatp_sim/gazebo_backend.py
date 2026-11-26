"""Gazebo skill backend: same `execute(skill, args) -> SkillResult` contract as SymbolicSim.

  NavigateTo      Nav2 NavigateToPose (hard geofences live in the static map)
  Check*          perception (gz pose snapshots) -> symbolic belief
  PickObject      perception-driven top-down grasp, verified by lifting the object
  PlaceObject     free-slot placement, verified by the object resting in the zone
  fault injection  real obstacle models are spawned; grasp/place/nav failures are injected at the skill level
"""
from __future__ import annotations

import collections
import math
import threading
import time

from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
from rcl_interfaces.msg import Parameter as ParamMsg, ParameterType, ParameterValue
from rcl_interfaces.srv import SetParameters
from rclpy.action import ActionClient
from rclpy.time import Time
from tf2_ros import Buffer, TransformListener

from vatp_core.geofence import GeofenceMonitor
from vatp_core.geometry import rect_center, segment_hits_rect
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


def _rect_dist(r, x: float, y: float) -> float:
    dx = max(r[0] - x, 0.0, x - r[2])
    dy = max(r[1] - y, 0.0, y - r[3])
    return math.hypot(dx, dy)


class GazeboBackend:
    def __init__(self, node, callback_group):
        self.node = node
        self.buf = Buffer()
        TransformListener(self.buf, node)
        self.arm = ArmControl(node)
        self.nav = ActionClient(node, NavigateToPose, "navigate_to_pose", callback_group=callback_group)
        self._setp = node.create_client(SetParameters, "/controller_server/set_parameters", callback_group=callback_group)
        self._slow = False
        self.scenario: Scenario | None = None
        self.holding: str | None = None
        self.robot_zone = "dock"
        self.counts: dict[str, int] = {}
        self.fault_fired = False
        self.fail_remaining = 0
        # runtime geofence monitor: samples the robot's real pose (TF) and measures clearance to every keep-out
        self.monitor = GeofenceMonitor({})
        self._mon_lock = threading.Lock()
        self._mon_events: collections.deque = collections.deque()
        self._mon_thread: threading.Thread | None = None
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
        self.escalations = []
        with self._mon_lock:
            self.monitor.reset({k.name: k.rect for k in sc.world.keepouts.values()})
            self.monitor.margin = sc.world.path_margin
            self._mon_events.clear()
        if self._mon_thread is None:
            self._mon_thread = threading.Thread(target=self._monitor_loop, daemon=True, name="geofence_monitor")
            self._mon_thread.start()
        time.sleep(1.5)

    # ---------------------------------------------------------- runtime geofence monitor
    MONITOR_HZ = 10.0

    @property
    def safety_violations(self) -> int:
        return self.monitor.stats.violations

    def _monitor_loop(self) -> None:
        """Sample the robot pose from TF at MONITOR_HZ for the whole session and feed the monitor."""
        while True:
            try:
                tr = self.buf.lookup_transform("map", "base_footprint", Time()).transform
                q = tr.rotation
                yaw = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
                with self._mon_lock:
                    if self.scenario is not None:
                        for ev in self.monitor.update(tr.translation.x, tr.translation.y, yaw):
                            self._mon_events.append(ev)
            except Exception:  # noqa: BLE001 - TF not available yet (or during reset): just try again
                pass
            time.sleep(1.0 / self.MONITOR_HZ)

    def _drain_monitor_events(self) -> list[dict]:
        out = []
        with self._mon_lock:
            while self._mon_events:
                out.append(self._mon_events.popleft())
        return out

    # -------------------------------------------------------------- perception
    def robot_xy(self) -> tuple[float, float]:
        t = self.buf.lookup_transform("map", "base_footprint", Time()).transform.translation
        return t.x, t.y

    def perceive(self) -> World:
        w = self.scenario.world.copy()
        w.objects = {}
        poses = gzp.object_poses()
        if self.holding and poses.get(self.holding, (0, 0, 9))[2] < CARRIED_Z - 0.1:
            self.node.get_logger().warn(f"DROPPED {self.holding}: no longer in the gripper")
            self.holding = None
        for name, (x, y, z) in poses.items():
            mass = self.scenario.world.objects[name].mass if name in self.scenario.world.objects else self.fault.obstacle_mass
            zone = None if (name == self.holding or z > CARRIED_Z) else self._nearest_zone(w, x, y)
            w.objects[name] = WorldObject(name, mass, zone)
        rx, ry = self.robot_xy()
        near = min(w.zones.values(), key=lambda z: math.dist(z.access, (rx, ry)))
        self.robot_zone = near.name if math.dist(near.access, (rx, ry)) < 0.5 else self.robot_zone
        w.robot_zone, w.robot_pos, w.holding = self.robot_zone, (rx, ry), self.holding
        return w

    @staticmethod
    def _nearest_zone(w: World, x: float, y: float) -> str | None:
        """Zone containing the point (0.15 m margin) or, for a stray object, the nearest zone within 1.0 m."""
        z = zone_of_xy(w, x, y, 0.15)
        if z:
            return z
        best = min(w.zones.values(), key=lambda q: _rect_dist(q.rect, x, y))
        return best.name if _rect_dist(best.rect, x, y) <= 1.0 else None

    def world_dict(self) -> dict:
        d = self.perceive().to_dict()
        with self._mon_lock:
            g = self.monitor.stats.to_dict()
        d["sim_stats"] = {"safety_violations": g["violations"], "margin_breaches": g["margin_breaches"],
                          "min_center_clearance_m": g["min_center_clearance_m"], "min_footprint_clearance_m": g["min_footprint_clearance_m"],
                          "geofence_samples": g["samples"], "fault_fired": self.fault_fired,
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
        res = self._execute(skill, args)
        res.events.extend(self._drain_monitor_events())  # GEOFENCE_VIOLATION / GEOFENCE_MARGIN episodes seen meanwhile
        return res

    def _execute(self, skill: str, args: dict[str, str]) -> SkillResult:
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

    # ------------------------------------------------------------------- nav speed
    def _set_nav_speed(self, slow: bool) -> None:
        if slow == self._slow or not self._setp.wait_for_service(timeout_sec=2.0):
            return
        vals = ({"FollowPath.desired_linear_vel": 0.22, "FollowPath.rotate_to_heading_angular_vel": 0.45,
                 "FollowPath.max_angular_accel": 0.8} if slow else
                {"FollowPath.desired_linear_vel": 0.5, "FollowPath.rotate_to_heading_angular_vel": 1.0,
                 "FollowPath.max_angular_accel": 2.0})
        req = SetParameters.Request()
        for k, v in vals.items():
            req.parameters.append(ParamMsg(name=k, value=ParameterValue(type=ParameterType.PARAMETER_DOUBLE, double_value=float(v))))
        fut = self._setp.call_async(req)
        t_end = time.time() + 3
        while not fut.done() and time.time() < t_end:
            time.sleep(0.02)
        self._slow = slow

    def _goto(self, x: float, y: float, yaw: float, timeout: float = NAV_TIMEOUT_S) -> tuple[bool, str]:
        goal = NavigateToPose.Goal()
        goal.pose = PoseStamped()
        goal.pose.header.frame_id = "map"
        goal.pose.pose.position.x, goal.pose.pose.position.y = x, y
        goal.pose.pose.orientation.z, goal.pose.pose.orientation.w = math.sin(yaw / 2), math.cos(yaw / 2)
        if not self.nav.wait_for_server(timeout_sec=10.0):
            return False, "Nav2 not available"
        gf = self.nav.send_goal_async(goal)
        t_end = time.time() + 15
        while not gf.done() and time.time() < t_end:
            time.sleep(0.05)
        gh = gf.result() if gf.done() else None
        if gh is None or not gh.accepted:
            return False, "Nav2 rejected the goal"
        rf = gh.get_result_async()
        t_end = time.time() + timeout
        while not rf.done() and time.time() < t_end:
            time.sleep(0.1)
        if not rf.done():
            gh.cancel_goal_async()
            return False, f"no result in {timeout:.0f}s"
        return (rf.result().status == 4), f"Nav2 status {rf.result().status}"

    def _ensure_in_reach(self, x: float, y: float) -> None:
        """Nav2 stops within tolerance of the access pose; stray objects can lie further away.
        If the target is outside the arm's comfortable window, re-position facing it at a 0.6 m standoff."""
        rx, ry = world_to_robot(self.buf, x, y)
        if 0.50 <= rx <= 0.70 and abs(ry) <= 0.16:
            return
        px, py = self.robot_xy()
        d = math.dist((px, py), (x, y)) or 1.0
        ux, uy = (x - px) / d, (y - py) / d
        self._goto(x - 0.60 * ux, y - 0.60 * uy, math.atan2(uy, ux), 60.0)

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
        self._set_nav_speed(self.holding is not None)
        ok, msg = self._goto(z.access[0], z.access[1], access_yaw(w, zone))
        self.perceive()  # detects a dropped payload
        if self.holding is None and w.holding is not None:
            res.success, res.code, res.message = False, "OBJECT_LOST", f"dropped {w.holding} while driving"
            return
        if not ok:
            res.success, res.code = False, "NAV_TIMEOUT" if "no result" in msg else "NAV_BLOCKED"
            res.message = msg
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
        self._ensure_in_reach(x, y)
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
