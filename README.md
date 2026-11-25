# Verifiable Agentic Task Planner

LLM-to-Behavior-Tree synthesis with deterministic pre-execution validation and closed-loop
recovery for a mobile manipulator (ROS 2 Jazzy · Gazebo Harmonic · Nav2 · MoveIt 2 · BehaviorTree.CPP 4).

```
instruction ─► RAG(safety+recovery) ─► LLM (schema-constrained BT) ─► VALIDATOR ─► BT.CPP XML ─► executor
                                              ▲                         │ errors          │ tick
                                              └──── repair prompt ◄─────┘                 ▼
                              replan(failure, re-perceived world) ◄── FAILURE ◄── lifecycle skill servers
```

**Status:** core, ROS 2 closed loop, and the symbolic backend with fault injection work and are
benchmarked; Gazebo/Nav2/MoveIt backend is in progress — see [docs/ROADMAP.md](docs/ROADMAP.md).

## Quick start
```bash
sudo bash scripts/install_system_deps.sh      # once
bash scripts/setup_venv.sh                    # python deps (anthropic, pytest, ...)
source /opt/ros/jazzy/setup.bash && colcon build --symlink-install
source scripts/env.sh

ros2 launch vatp_ros symbolic.launch.py backend:=mock        # or backend:=anthropic (ANTHROPIC_API_KEY)
ros2 run vatp_ros benchmark --n 20 --seed 0 --out runs        # in a second terminal
```
Tests: `colcon test && colcon test-result` (39 Python + 4 C++).
Groot2 connects to the executor on port 1667 while a mission runs.

## Layout
| package | what |
|---|---|
| `vatp_core` | skill library (`spec/skills.yaml`), world model, **validator**, RAG, LLM backends, planner, scenarios, symbolic sim — no ROS dependency |
| `vatp_interfaces` | `ExecuteSkill`, `RunMission` actions; `PlanMission`, `Replan`, `GetWorld`, `LoadScenario` services; `MissionEvent` |
| `vatp_bt` | C++ lifecycle executor: registers skills from the shared YAML, ticks BT.CPP, recovery supervisor, Groot2 |
| `vatp_ros` | planner service node, lifecycle skill server, benchmark harness, launch |
