# Verifiable Agentic Task Planner

**LLM → Behavior Tree synthesis with deterministic pre-execution validation and closed-loop recovery**
for a mobile manipulator — ROS 2 Jazzy · Gazebo Harmonic · Nav2 · BehaviorTree.CPP 4 · Groot2/Foxglove.

Raw LLM agents are too unpredictable to drive a robot directly. This project treats the model as a *proposer*:
it emits a plan in a constrained skill vocabulary, a **model-free validator proves safety properties before the
robot moves**, and only then is the plan executed as a BehaviorTree.CPP tree. When execution fails (unexpected
obstacle, failed grasp, blocked path) the supervisor re-perceives the scene and the planner returns a *validated
patch* for the remaining mission.

```
instruction ─► RAG(safety + recovery) ─► LLM (schema-constrained BT) ─► VALIDATOR ─► BT.CPP XML ─► lifecycle executor
                                               ▲                          │ errors                   │ tick
                                               └──── repair prompt ◄──────┘                           ▼
                    validated patch ◄── Replan(failure, re-perceived world) ◄── FAILURE ◄── skill servers (Nav2 · arm · perception)
```

## What is in the box
| capability | where |
|---|---|
| Skill library as single source of truth (prompt, schema, validator **and** C++ executor read the same YAML) | `vatp_core/spec/skills.yaml` |
| **Pre-execution validator**: structure · ports · symbolic execution of every success/failure path (preconditions, keep-out geofence, transit corridors, payload, capacity) · goal verification | `vatp_core/validator.py` |
| Generate → validate → repair loop; replanning for the *remaining* mission | `vatp_core/planner.py` |
| RAG memory (BM25) over safety constraints and recovery procedures | `vatp_core/rag.py`, `knowledge/*.md` |
| Claude backend (schema-constrained output, refusal fallbacks) + deterministic offline test double with defect injection | `vatp_core/llm.py`, `mock_planner.py` |
| ROS 2 **lifecycle** BT.CPP executor, recovery supervisor, Groot2 publisher, event stream | `vatp_bt` |
| Lifecycle skill servers (`ExecuteSkill` actions) with pluggable backends: `symbolic` and `gazebo` | `vatp_ros` |
| Gazebo warehouse + mobile manipulator, ros2_control, Nav2, perception, physical grasping, **live fault injection** | `vatp_sim` |
| 20 randomised scenarios × 5 fault types, metrics (success, replans, latency, node count, safety violations) | `vatp_core/scenarios.py`, `vatp_ros/benchmark.py` |

Architecture details and the honest list of simulation shortcuts: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
Running the demo with Groot2 / Foxglove: [docs/DEMO.md](docs/DEMO.md).

## Quick start (Ubuntu 24.04 + ROS 2 Jazzy)
```bash
sudo bash scripts/install_system_deps.sh      # once: colcon, ros2_control, Foxglove, MoveIt, ...
bash scripts/setup_venv.sh                    # python deps (anthropic, pytest, ...)
source /opt/ros/jazzy/setup.bash && colcon build --symlink-install
source scripts/env.sh

# fast, no Gazebo (CI-friendly)
ros2 launch vatp_ros symbolic.launch.py backend:=mock
ros2 run vatp_ros benchmark --n 20

# full simulation
ros2 launch vatp_sim mission.launch.py backend:=auto scenario:=0 gui:=false dashboard:=true
ros2 run vatp_ros benchmark --n 20 --physical --timeout 900
python scripts/plot_results.py runs/<stamp>/metrics.json
```
`backend:=anthropic` uses Claude (`ANTHROPIC_API_KEY`, default model `claude-opus-5-5`, override with `VATP_MODEL`/`VATP_EFFORT`).
`auto` falls back to the offline planner when no key is present.

Tests: `colcon test && colcon test-result` · `pytest src/vatp_core/tests` · `pytest src/vatp_sim/test`.

## Fault injection
Each scenario carries one fault, fired when a chosen skill is called for the n-th time:

| fault | effect | expected recovery |
|---|---|---|
| `obstacle_spawn` | a real box model appears in the loading bay (Gazebo) | NAV `UNEXPECTED_OBSTACLE` → replan: clear it, then continue |
| `grasp_fail` | the next *k* grasps miss | `RetryUntilSuccessful` absorbs k<3, replan otherwise |
| `nav_block` | the next 2 navigations fail | retry exhausted → replan |
| `place_fail` | placement fails while holding the object | replan: handle held object, then re-place |

## Results
See [docs/results/](docs/results/). Offline-planner numbers validate the pipeline and are **not** LLM latencies.

## Limitations (stated up front)
* Localisation and perception use simulator ground truth (stand-ins for AMCL and a VLM); the VLM hook is the scene graph given to the planner.
* Grasping uses closed-form IK with a high approach and vertical descent; MoveIt 2 is the planned replacement behind `ArmControl`.
* Validation is sound relative to the symbolic world model — it cannot catch discrepancies between that model and physics (that is what runtime recovery is for).

## License
Apache-2.0
