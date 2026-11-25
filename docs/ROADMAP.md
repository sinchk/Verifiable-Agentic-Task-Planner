# Roadmap
- [x] Phase 1 — core: skill library, world model, BT validator, RAG, LLM planner, scenario suite, tests
- [x] Phase 2 — ROS 2: interfaces, planner node, BT.CPP executor (lifecycle), lifecycle skill servers (symbolic backend + fault injection), 20-scenario benchmark
- [~] Phase 3 — Gazebo Harmonic: robot + world + ros2_control + bridges + Nav2 launch DONE; IN PROGRESS: map->odom localiser pose mismatch (planner sees robot at (0.85,0) vs TF (1.5,1.0)), then Nav2 skill backend, MoveIt 2 pick/place, object perception via `gz topic` snapshots
- [ ] Phase 4 — fault injection, replanning loop, metrics over 20 scenarios, Foxglove/Groot2 dashboard
- [ ] Phase 5 — docs, results, demo
