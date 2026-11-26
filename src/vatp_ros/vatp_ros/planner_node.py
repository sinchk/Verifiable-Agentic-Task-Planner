"""ROS 2 planner node: exposes the validated LLM→BT planner as services.

  /vatp/plan_mission  (PlanMission)   instruction + world  -> validated BT.CPP XML
  /vatp/replan        (Replan)        failure + CURRENT world -> validated XML for the REMAINING mission

Parameters: backend (auto|mock|anthropic), model, effort, defect_rate, seed, max_repairs.
"""
from __future__ import annotations

import json

import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from vatp_core.llm import make_backend
from vatp_core.planner import Failure, PlanResult, Planner
from vatp_core.validator import _holds
from vatp_core.world import World
from vatp_interfaces.srv import PlanMission, Replan


class PlannerNode(Node):
    def __init__(self) -> None:
        super().__init__("vatp_planner")
        self.declare_parameter("backend", "auto")
        self.declare_parameter("model", "")
        self.declare_parameter("effort", "")
        self.declare_parameter("defect_rate", 0.0)
        self.declare_parameter("seed", 0)
        self.declare_parameter("max_repairs", 2)
        self.declare_parameter("enforce_validator", True)  # False = ablation: run plans unvalidated
        kind = self.get_parameter("backend").value
        kw: dict = {}
        if kind == "mock" or (kind == "auto" and not _has_key()):
            kind = "mock"
            kw = {"defect_rate": float(self.get_parameter("defect_rate").value),
                  "seed": int(self.get_parameter("seed").value)}
        else:
            if self.get_parameter("model").value:
                kw["model"] = self.get_parameter("model").value
            if self.get_parameter("effort").value:
                kw["effort"] = self.get_parameter("effort").value
        self.backend = make_backend(kind, **kw)
        self.planner = Planner(self.backend, max_repairs=int(self.get_parameter("max_repairs").value),
                               enforce=bool(self.get_parameter("enforce_validator").value))
        if not self.planner.enforce:
            self.get_logger().warn("ABLATION: validator verdicts are IGNORED; plans execute unvalidated")
        self._declared: dict[str, list[dict]] = {}
        cg = ReentrantCallbackGroup()
        self.create_service(PlanMission, "/vatp/plan_mission", self._plan, callback_group=cg)
        self.create_service(Replan, "/vatp/replan", self._replan, callback_group=cg)
        self.get_logger().info(f"planner ready, backend={self.backend.name}")

    # ----------------------------------------------------------------- helpers
    @staticmethod
    def _fill(resp, res: PlanResult):
        resp.ok = res.ok
        resp.bt_xml = res.xml or ""
        resp.plan_json = json.dumps(res.plan or {})
        resp.metrics_json = json.dumps(res.metrics())
        last = res.attempts[-1].issues if res.attempts else []
        resp.issues_json = json.dumps([i.to_dict() for i in last])
        return resp

    def _plan(self, req: PlanMission.Request, resp: PlanMission.Response):
        world = World.from_yaml(req.world_yaml)
        goals = json.loads(req.required_goals_json) if req.required_goals_json else []
        self.get_logger().info(f"PLAN: {req.instruction!r}")
        res = self.planner.plan(req.instruction, world, goals)
        if res.plan:
            self._declared[req.instruction] = res.plan.get("goals", [])
        m = res.metrics()
        self.get_logger().info(f"PLAN -> ok={res.ok} nodes={m['nodes']} repairs={m['repairs']} "
                               f"latency={m['latency_s']}s validation={m['validation_ms']}ms")
        if not res.ok:
            for i in (res.attempts[-1].issues if res.attempts else []):
                self.get_logger().warn(str(i))
        return self._fill(resp, res)

    def _replan(self, req: Replan.Request, resp: Replan.Response):
        world = World.from_yaml(req.world_yaml)
        full = json.loads(req.required_goals_json) if req.required_goals_json else \
            self._declared.get(req.instruction, [])
        open_goals = [g for g in full if not _holds(g, world)]
        if not any(g["predicate"] == "gripper_empty" for g in open_goals):
            open_goals.append({"predicate": "gripper_empty", "args": []})
        fail = Failure(req.failed_node, req.failed_skill, req.failure_code, req.failure_message)
        self.get_logger().warn(f"REPLAN after {fail.describe()}; open goals: "
                               f"{[g['predicate'] + str(g['args']) for g in open_goals]}")
        res = self.planner.replan(req.instruction, world, fail, open_goals)
        m = res.metrics()
        self.get_logger().info(f"REPLAN -> ok={res.ok} nodes={m['nodes']} repairs={m['repairs']} "
                               f"latency={m['latency_s']}s")
        return self._fill(resp, res)


def _has_key() -> bool:
    import os
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def main(args=None) -> None:
    rclpy.init(args=args)
    node = PlannerNode()
    ex = MultiThreadedExecutor(num_threads=4)
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
