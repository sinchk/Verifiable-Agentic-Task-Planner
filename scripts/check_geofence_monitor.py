#!/usr/bin/env python3
"""Live check of the runtime geofence monitor against the real Gazebo simulation.

Needs the full stack running:   ros2 launch vatp_sim mission.launch.py backend:=mock scenario:=3 gui:=false
  1. clean baseline        : robot parked far from the keep-out        -> 0 violations, 0 margin breaches
  2. margin approach       : robot placed 0.25 m from the aisle        -> 1 margin breach, 0 violations
  3. real contact          : robot DRIVEN (cmd_vel) into the barrier   -> >= 1 violation, footprint clearance ~ 0
  4. event path            : GEOFENCE_* events arrive on /vatp/events after the next skill call
Prints a table and exits non-zero if an expectation fails.
"""
import json
import math
import subprocess
import sys
import threading
import time

import rclpy
import yaml
from geometry_msgs.msg import Twist
from rclpy.action import ActionClient
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from vatp_core.scenarios import make_scenario
from vatp_interfaces.action import ExecuteSkill
from vatp_interfaces.msg import MissionEvent
from vatp_interfaces.srv import GetWorld, LoadScenario
from vatp_sim import gz_perception as gzp


class Check(Node):
    def __init__(self):
        super().__init__("geofence_monitor_check")
        self.load = self.create_client(LoadScenario, "/vatp/load_scenario")
        self.world = self.create_client(GetWorld, "/vatp/get_world")
        self.skill = ActionClient(self, ExecuteSkill, "/vatp/skills/check_zone_clear")
        self.cmd = self.create_publisher(Twist, "/cmd_vel", 10)
        self.events = []
        self.create_subscription(MissionEvent, "/vatp/events", lambda m: self.events.append((m.type, m.detail)), 100)

    def call(self, cli, req, timeout=60.0):
        f = cli.call_async(req)
        t = time.time() + timeout
        while not f.done() and time.time() < t:
            time.sleep(0.02)
        return f.result()

    def stats(self):
        w = yaml.safe_load(self.call(self.world, GetWorld.Request()).world_yaml)
        return w["sim_stats"]

    def place(self, x, y, yaw, hold_s=1.5):
        t = time.time() + hold_s
        while time.time() < t:       # re-assert the pose so the 10 Hz monitor sees it for sure
            gzp.set_pose("vatp_amr", x, y, 0.02, yaw)
            time.sleep(0.1)

    def drive(self, v, secs):
        t = time.time() + secs
        msg = Twist(); msg.linear.x = v
        while time.time() < t:
            self.cmd.publish(msg); time.sleep(0.05)
        self.cmd.publish(Twist())

    def run_skill(self):
        self.skill.wait_for_server(timeout_sec=30)
        g = ExecuteSkill.Goal(skill="CheckZoneClear", arg_names=["zone"], arg_values=["dock"])
        gf = self.skill.send_goal_async(g)
        while not gf.done(): time.sleep(0.02)
        rf = gf.result().get_result_async()
        while not rf.done(): time.sleep(0.02)


def main():
    rclpy.init()
    n = Check()
    ex = MultiThreadedExecutor(num_threads=4); ex.add_node(n)
    threading.Thread(target=ex.spin, daemon=True).start()
    for c in (n.load, n.world):
        assert c.wait_for_service(timeout_sec=90), "stack not running"
    sc = make_scenario(3, 0, jitter=False)
    assert n.call(n.load, LoadScenario.Request(scenario_yaml=sc.to_yaml())).ok
    time.sleep(3)
    rows, ok = [], True

    def record(name, expect, s):
        nonlocal ok
        good = expect(s)
        ok &= good
        rows.append((name, s["safety_violations"], s["margin_breaches"], s["min_center_clearance_m"], s["min_footprint_clearance_m"], "PASS" if good else "FAIL"))

    n.place(4.0, 6.0, 0.0, 1.5)
    record("1 baseline (robot far from the aisle)", lambda s: s["safety_violations"] == 0 and s["margin_breaches"] == 0, n.stats())
    n.place(6.75, 6.0, math.pi / 2, 2.0)
    record("2 margin approach (centre 0.25 m from the aisle)", lambda s: s["margin_breaches"] == 1 and s["safety_violations"] == 0, n.stats())
    n.place(5.2, 6.0, 0.0, 1.0)
    n.drive(0.3, 12.0)
    time.sleep(1.0)
    record("3 real contact (driven into the barrier)", lambda s: s["safety_violations"] >= 1 and s["min_footprint_clearance_m"] is not None and s["min_footprint_clearance_m"] <= 0.03, n.stats())
    n.run_skill(); time.sleep(0.5)
    kinds = sorted({t for t, _ in n.events if t.startswith("GEOFENCE")})
    ok &= kinds == ["GEOFENCE_MARGIN", "GEOFENCE_VIOLATION"]
    rows.append(("4 events on /vatp/events", "", "", "", "", ", ".join(kinds) or "none"))
    print(f"{'check':58s} {'viol':>5s} {'margin':>7s} {'min ctr m':>10s} {'min fp m':>9s}  result")
    for r in rows:
        print(f"{r[0]:58s} {str(r[1]):>5s} {str(r[2]):>7s} {str(r[3]):>10s} {str(r[4]):>9s}  {r[5]}")
    print("\nALL CHECKS PASSED" if ok else "\nSOME CHECKS FAILED")
    for t, d in n.events:
        if t.startswith("GEOFENCE"): print("  event:", t, d)
    rclpy.shutdown()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
