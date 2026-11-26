# Roadmap
- [x] Phase 1 — core: skill library, world model, BT validator, RAG, LLM planner, scenario suite, tests
- [x] Phase 2 — ROS 2: interfaces, planner node, BT.CPP executor (lifecycle), lifecycle skill servers (symbolic backend + fault injection), 20-scenario benchmark
- [x] Phase 3 — Gazebo Harmonic end to end: robot, world, ros2_control, Nav2, perception, physical pick/place, `gazebo` skill backend with real fault injection (obstacle spawned mid-mission → replan → recovered). Smoke results in docs/results/gazebo_smoke
- [x] Phase 4 (Gazebo results with the offline reference planner; LLM results on the symbolic backend) — fault injection, replanning loop, metrics over 20 scenarios, Foxglove/Groot2 dashboard
- [ ] Phase 5 — docs, results, demo
