# Demo guide

## 1. Start everything
```bash
source scripts/env.sh
ros2 launch vatp_sim mission.launch.py backend:=auto scenario:=0 gui:=true dashboard:=true
```
* `gui:=true` opens the Gazebo window (needs the desktop session; headless is the default and what the benchmark uses).
* `backend:=anthropic` uses Claude (needs credits on the key); `auto` falls back to the offline planner without a key.
* `dashboard:=true` starts `foxglove_bridge` on `ws://localhost:8765`.

## 2. Watch the behavior tree live (Groot2)
Download Groot2 from https://www.behaviortree.dev/groot/ , choose **Monitor**, connect to `localhost:1667`.
The tree shown is the *validated plan*; after a failure it is swapped for the validated patch.

## 3. Foxglove dashboard
Open Foxglove → *Open connection* → Foxglove WebSocket → `ws://localhost:8765`. Useful panels:

| panel | topic |
|---|---|
| 3D | `/tf`, `/robot_description`, `/scan`, `/global_costmap/costmap`, `/plan` |
| Log | `/rosout` (filter `vatp`) |
| Raw Messages / State Transitions | `/vatp/events` (`PLAN_READY`, `SKILL_FAILED`, `FALLBACK_TRIGGERED`, `REPLAN_READY`, `TREE_SWAPPED`, `FAULT_INJECTED`, `MISSION_END`) |
| Plot | `/vatp/events` is JSON in `detail`; latencies are in the benchmark CSV |

## 4. Run a mission / the benchmark
```bash
ros2 run vatp_ros benchmark --n 20 --physical --only 8 --timeout 600    # the obstacle-spawn recovery demo
ros2 run vatp_ros benchmark --n 20 --physical --timeout 900             # all 20 scenarios
python scripts/plot_results.py runs/<stamp>/metrics.json
```
Scenario 8 is the headline demo: *"Check if the loading bay is clear; if blocked, clear the small box first, then
deliver the crate to Zone B."* — an extra obstacle appears in the bay mid-mission, the tree fails, the supervisor
re-perceives, the planner returns a validated patch, the robot clears the new obstacle and finishes.

## 5. Without Gazebo (fast, CI-friendly)
```bash
ros2 launch vatp_ros symbolic.launch.py backend:=mock
ros2 run vatp_ros benchmark --n 20
```
