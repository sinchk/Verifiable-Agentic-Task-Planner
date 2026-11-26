"""Scenario benchmark: runs N randomised scenarios through the *real* ROS stack and logs metrics.

For each scenario: load world+fault into the skill server -> RunMission (plan, validate, execute,
recover) -> read the ground-truth world back and check the required goals independently of
anything the planner claimed. Writes runs/<stamp>/{metrics.json,metrics.csv,events.jsonl,summary.md}.

    ros2 run vatp_ros benchmark --n 20 --seed 0 --out runs
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics as stats
import threading
import time
from pathlib import Path

import rclpy
import yaml
from rclpy.action import ActionClient
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from vatp_core.scenarios import generate_suite
from vatp_core.validator import _holds
from vatp_core.world import World
from vatp_interfaces.action import RunMission
from vatp_interfaces.msg import MissionEvent
from vatp_interfaces.srv import GetWorld, LoadScenario


class Bench(Node):
    def __init__(self) -> None:
        super().__init__("vatp_benchmark")
        self.load = self.create_client(LoadScenario, "/vatp/load_scenario")
        self.world = self.create_client(GetWorld, "/vatp/get_world")
        self.mission = ActionClient(self, RunMission, "/vatp/run_mission")
        self.events: list[dict] = []
        self.create_subscription(MissionEvent, "/vatp/events", self._ev, 500)
        self.t0 = time.time()

    def _ev(self, m: MissionEvent) -> None:
        self.events.append({"t": m.stamp.sec + m.stamp.nanosec * 1e-9, "type": m.type,
                            "node": m.node, "detail": m.detail})

    def wait_ready(self, timeout: float = 90.0) -> bool:
        return all(c.wait_for_service(timeout) for c in (self.load, self.world)) and \
            self.mission.wait_for_server(timeout)

    def call(self, cli, req, timeout=180.0):
        fut = cli.call_async(req)
        t_end = time.time() + timeout
        while not fut.done() and time.time() < t_end:
            time.sleep(0.01)
        return fut.result() if fut.done() else None

    def run_one(self, sc, max_replans: int, timeout: float) -> dict:
        r = self.call(self.load, LoadScenario.Request(scenario_yaml=sc.to_yaml()))
        assert r and r.ok, f"load failed: {r}"
        self.events.clear()
        goal = RunMission.Goal(instruction=sc.instruction, max_replans=max_replans,
                               required_goals_json=json.dumps(sc.required_goals))
        t0 = time.time()
        gf = self.mission.send_goal_async(goal)
        while not gf.done():
            time.sleep(0.01)
        gh = gf.result()
        if not gh.accepted:
            return {"id": sc.id, "error": "mission rejected"}
        rf = gh.get_result_async()
        t_end = time.time() + timeout
        while not rf.done() and time.time() < t_end:
            time.sleep(0.02)
        wall = time.time() - t0
        if not rf.done():
            gh.cancel_goal_async()
            return {"id": sc.id, "error": f"timeout after {timeout}s", "wall_s": wall}
        res = rf.result().result
        time.sleep(0.2)  # let trailing events land
        w = yaml.safe_load(self.call(self.world, GetWorld.Request()).world_yaml)
        stats_ = w.get("sim_stats", {})
        final = World.from_dict(w)
        goals_ok = all(_holds(g, final) for g in sc.required_goals)
        ev = list(self.events)
        plan_ready = next((e for e in ev if e["type"] == "PLAN_READY"), None)
        pm = json.loads(plan_ready["detail"]).get("metrics", {}) if plan_ready else {}
        replan_m = [json.loads(e["detail"]).get("metrics", {}) for e in ev if e["type"] == "REPLAN_READY"]
        faults = [e for e in ev if e["type"] == "FAULT_INJECTED"]
        return {
            "id": sc.id, "template": sc.template, "fault": sc.fault.type, "backend": pm.get("backend", ""),
            "success": bool(res.success and goals_ok),
            "tree_completed": bool(res.success), "goals_satisfied": goals_ok,
            "fault_fired": bool(stats_.get("fault_fired")), "n_fault_events": len(faults),
            "recovered_from_fault": bool(res.success and goals_ok and stats_.get("fault_fired")),
            "replans": int(res.replans),
            "plan_latency_s": round(res.first_plan_latency_s, 3),
            "replan_latency_s": round(res.total_replan_latency_s / res.replans, 3) if res.replans else 0.0,
            "initial_nodes": int(res.initial_nodes),
            "final_nodes": final_nodes(res.final_bt_xml),
            "plan_repairs": int(pm.get("repairs", 0)),
            "first_attempt_valid": bool(pm.get("first_attempt_valid", True)),
            "validation_ms": float(pm.get("validation_ms", 0.0)),
            "safety_violations": int(stats_.get("safety_violations", 0)),
            "escalations": len(stats_.get("escalations", [])),
            "wall_s": round(wall, 2), "message": res.message,
            "_events": ev, "_final_xml": res.final_bt_xml,
        }


def final_nodes(xml: str) -> int:
    import xml.etree.ElementTree as ET
    try:
        bt = ET.fromstring(xml).find("BehaviorTree")
        return sum(1 for _ in bt.iter()) - 1
    except Exception:  # noqa: BLE001
        return 0


def summarize(rows: list[dict]) -> str:
    ok = [r for r in rows if "error" not in r]
    n = len(rows)
    succ = sum(r["success"] for r in ok)
    faulty = [r for r in ok if r["fault"] != "none"]
    rec = sum(r["recovered_from_fault"] for r in faulty)
    pl = [r["plan_latency_s"] for r in ok]
    rl = [r["replan_latency_s"] for r in ok if r["replans"]]

    def med(x): return f"{statistics_med(x):.2f}" if x else "n/a"
    lines = [
        "# Benchmark summary", "",
        f"| metric | value |", "|---|---|",
        f"| planner backend | {', '.join(sorted({r['backend'] for r in ok if r.get('backend')})) or 'n/a'} |",
        f"| scenarios | {n} |",
        f"| mission success rate | {succ}/{n} = {100*succ/max(n,1):.0f}% |",
        f"| fault scenarios recovered | {rec}/{len(faulty)} |",
        f"| scenarios needing replanning | {sum(1 for r in ok if r['replans'])} |",
        f"| initial plan latency (median / max, s) | {med(pl)} / {max(pl) if pl else 'n/a'} |",
        f"| replanning latency (median / max, s) | {med(rl)} / {max(rl) if rl else 'n/a'} |",
        f"| BT node count (median) | {med([r['initial_nodes'] for r in ok])} |",
        f"| first-attempt plans valid | {sum(r['first_attempt_valid'] for r in ok)}/{len(ok)} |",
        f"| geofence/safety violations | {sum(r['safety_violations'] for r in ok)} |",
        f"| errors/timeouts | {n-len(ok)} |", "",
        "| id | template | fault | success | replans | plan s | replan s | nodes | wall s |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        if "error" in r:
            lines.append(f"| {r['id']} | – | – | ERROR: {r['error']} | | | | | |")
        else:
            lines.append(f"| {r['id']} | {r['template']} | {r['fault']} | {'✅' if r['success'] else '❌'} | "
                         f"{r['replans']} | {r['plan_latency_s']} | {r['replan_latency_s']} | "
                         f"{r['initial_nodes']}→{r['final_nodes']} | {r['wall_s']} |")
    return "\n".join(lines) + "\n"


def statistics_med(x):
    return stats.median(x)


def main(args=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="runs")
    ap.add_argument("--max-replans", type=int, default=3)
    ap.add_argument("--timeout", type=float, default=240.0)
    ap.add_argument("--tag", default="")
    ap.add_argument("--physical", action="store_true", help="Gazebo backend: fixed (un-jittered) geometry matching the world")
    ap.add_argument("--only", type=int, nargs="*", help="run only these scenario indices")
    a, ros_args = ap.parse_known_args(args)
    rclpy.init(args=ros_args)
    node = Bench()
    ex = MultiThreadedExecutor(num_threads=4)
    ex.add_node(node)
    threading.Thread(target=ex.spin, daemon=True).start()
    if not node.wait_ready():
        node.get_logger().error("system not ready (planner/skill server/executor not up)")
        raise SystemExit(2)
    out = Path(a.out) / (time.strftime("%Y%m%d-%H%M%S") + (f"-{a.tag}" if a.tag else ""))
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    suite = generate_suite(a.n, a.seed, jitter=not a.physical)
    for sc in ([suite[i] for i in a.only] if a.only else suite):
        node.get_logger().info(f"=== {sc.id} [{sc.template}] fault={sc.fault.type}: {sc.instruction}")
        row = node.run_one(sc, a.max_replans, a.timeout)
        rows.append(row)
        node.get_logger().info(f"    -> {'OK' if row.get('success') else 'FAIL'} "
                               f"replans={row.get('replans')} {row.get('message', row.get('error'))}")
    flat = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]
    (out / "metrics.json").write_text(json.dumps(flat, indent=1))
    keys = sorted({k for r in flat for k in r})
    with open(out / "metrics.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(flat)
    with open(out / "events.jsonl", "w") as f:
        for r in rows:
            for e in r.get("_events", []):
                f.write(json.dumps({"scenario": r["id"], **e}) + "\n")
    for r in rows:
        if r.get("_final_xml"):
            (out / f"{r['id']}_final.bt.xml").write_text(r["_final_xml"])
    (out / "summary.md").write_text(summarize(rows))
    print(summarize(rows))
    print(f"results in {out}")
    rclpy.shutdown()


if __name__ == "__main__":
    main()
