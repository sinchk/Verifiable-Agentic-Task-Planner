"""Lifecycle skill server: one ``ExecuteSkill`` action server per skill in the skill library.

Backend ``symbolic`` executes against the ground-truth symbolic world with fault injection
(fast; used for the benchmark and CI). The Gazebo backend (Nav2 + MoveIt 2) implements the
same ``execute`` contract and is selected with ``backend:=gazebo``.

Lifecycle: unconfigured -> (configure) world + servers created -> (activate) goals accepted
-> (deactivate) goals rejected, running skills cancelled. With ``autostart:=true`` the node
configures and activates itself shortly after launch.
"""
from __future__ import annotations

import json
import re
import threading
import time

import rclpy
import yaml
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.lifecycle import Node, State, TransitionCallbackReturn

from vatp_core.scenarios import Scenario
from vatp_core.skills import load_library
from vatp_core.symbolic_sim import SymbolicSim
from vatp_interfaces.action import ExecuteSkill
from vatp_interfaces.msg import MissionEvent
from vatp_interfaces.srv import GetWorld, LoadScenario


def snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def skill_action_name(skill: str) -> str:
    return f"/vatp/skills/{snake(skill)}"


class SkillServer(Node):
    def __init__(self) -> None:
        super().__init__("vatp_skill_server")
        self.declare_parameter("backend", "symbolic")
        self.declare_parameter("time_scale", 0.02)  # wall seconds per simulated second
        self.declare_parameter("autostart", True)
        self.lib = load_library()
        self.sim: SymbolicSim | None = None
        self._lock = threading.Lock()
        self._active = False
        self._servers: list[ActionServer] = []
        self._cg = ReentrantCallbackGroup()
        if self.get_parameter("autostart").value:
            self._boot = self.create_timer(0.3, self._autostart)

    def _autostart(self) -> None:
        self._boot.cancel()
        if self.trigger_configure() == TransitionCallbackReturn.SUCCESS:
            self.trigger_activate()

    # --------------------------------------------------------------- lifecycle
    def on_configure(self, state: State) -> TransitionCallbackReturn:
        self.gz = None
        backend = self.get_parameter("backend").value
        if backend == "gazebo":
            try:
                from vatp_sim.gazebo_backend import GazeboBackend
            except ImportError as e:
                self.get_logger().error(f"gazebo backend unavailable (is vatp_sim built/sourced?): {e}")
                return TransitionCallbackReturn.FAILURE
            self.gz = GazeboBackend(self, self._cg)
        elif backend != "symbolic":
            self.get_logger().error(f"unknown backend '{backend}' (symbolic|gazebo)")
            return TransitionCallbackReturn.FAILURE
        self.events = self.create_publisher(MissionEvent, "/vatp/events", 50)
        self.create_service(GetWorld, "/vatp/get_world", self._get_world, callback_group=self._cg)
        self.create_service(LoadScenario, "/vatp/load_scenario", self._load, callback_group=self._cg)
        for name in self.lib.skills:
            self._servers.append(ActionServer(
                self, ExecuteSkill, skill_action_name(name),
                execute_callback=lambda gh, n=name: self._execute(n, gh),
                goal_callback=self._goal_cb, cancel_callback=lambda gh: CancelResponse.ACCEPT,
                callback_group=self._cg))
        self.get_logger().info(f"configured: {len(self._servers)} skill action servers")
        return TransitionCallbackReturn.SUCCESS

    def on_activate(self, state: State) -> TransitionCallbackReturn:
        self._active = True
        self.get_logger().info("ACTIVE: accepting skill goals")
        return super().on_activate(state)

    def on_deactivate(self, state: State) -> TransitionCallbackReturn:
        self._active = False
        return super().on_deactivate(state)

    def on_cleanup(self, state: State) -> TransitionCallbackReturn:
        for s in self._servers:
            s.destroy()
        self._servers.clear()
        return TransitionCallbackReturn.SUCCESS

    # ---------------------------------------------------------------- services
    def _load(self, req: LoadScenario.Request, resp: LoadScenario.Response):
        try:
            sc = Scenario.from_yaml(req.scenario_yaml)
        except Exception as e:  # noqa: BLE001 — report any parse problem to the caller
            resp.ok, resp.message = False, f"bad scenario: {e}"
            return resp
        if self.gz is not None:
            self.gz.load(sc)
            self.sim = self.gz  # truthiness marks "scenario loaded"
        else:
            with self._lock:
                self.sim = SymbolicSim(sc)
        self.get_logger().info(f"loaded scenario {sc.id} ({sc.template}, fault={sc.fault.type})")
        resp.ok, resp.message = True, sc.id
        return resp

    def _get_world(self, req, resp: GetWorld.Response):
        if self.sim is None:
            resp.world_yaml = ""
            return resp
        if self.gz is not None:
            resp.world_yaml = yaml.safe_dump(self.gz.world_dict(), sort_keys=False)
            return resp
        with self._lock:
            d = self.sim.world.to_dict()
            d["sim_stats"] = {
                "safety_violations": self.sim.safety_violations,
                "margin_breaches": self.sim.margin_breaches,
                "fault_fired": self.sim.fault_fired,
                "escalations": list(self.sim.escalations),
                "fault": self.sim.fault.type,
            }
            resp.world_yaml = yaml.safe_dump(d, sort_keys=False)
        return resp

    # ------------------------------------------------------------------ action
    def _goal_cb(self, goal) -> GoalResponse:
        if not self._active or self.sim is None:
            return GoalResponse.REJECT
        return GoalResponse.ACCEPT

    def _emit(self, typ: str, node: str, detail: str) -> None:
        m = MissionEvent()
        m.stamp = self.get_clock().now().to_msg()
        m.type, m.node, m.detail = typ, node, detail
        self.events.publish(m)

    def _execute(self, skill: str, gh):
        req = gh.request
        args = dict(zip(req.arg_names, req.arg_values))
        if self.gz is not None:
            res = self.gz.execute(skill, args)  # real time: Nav2 / arm motion happen inside
        else:
            with self._lock:
                res = self.sim.execute(skill, args)
        for ev in res.events:
            self._emit(ev["type"], skill, ev["detail"])
            self.get_logger().warn(f"{ev['type']}: {ev['detail']}")
        # Simulated duration with feedback; honour cancellation.
        scale = float(self.get_parameter("time_scale").value)
        t_end = time.monotonic() + res.sim_duration_s * scale
        fb = ExecuteSkill.Feedback()
        while time.monotonic() < t_end:
            if gh.is_cancel_requested:
                gh.canceled()
                return ExecuteSkill.Result(success=False, code="CANCELED", message="canceled")
            fb.status, fb.progress = f"{skill} running", 0.5
            gh.publish_feedback(fb)
            time.sleep(0.02)
        out = ExecuteSkill.Result(success=res.success, code=res.code, message=res.message)
        (gh.succeed if res.success else gh.abort)()
        if res.success:
            self.get_logger().info(f"{skill}({json.dumps(args)}) -> OK")
        else:
            self.get_logger().warn(f"{skill}({json.dumps(args)}) -> {res.code}: {res.message}")
        return out


def main(args=None) -> None:
    rclpy.init(args=args)
    node = SkillServer()
    ex = MultiThreadedExecutor(num_threads=8)
    ex.add_node(node)
    try:
        ex.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
