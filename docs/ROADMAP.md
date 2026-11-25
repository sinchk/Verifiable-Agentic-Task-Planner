# Roadmap
- [x] Phase 1 — core: skill library, world model, BT validator, RAG, LLM planner, scenario suite, tests
- [x] Phase 2 — ROS 2: interfaces, planner node, BT.CPP executor (lifecycle), lifecycle skill servers (symbolic backend + fault injection), 20-scenario benchmark
- [~] Phase 3 — Gazebo Harmonic: robot, world, ros2_control, bridges, ground-truth localiser and Nav2 verified (dock→zone_a→loading_bay→zone_b, ~7 cm accuracy, geofence respected). NEXT: Gazebo skill backend (Nav2 NavigateTo, `gz topic` perception, MoveIt 2 pick/place, object attach), fault injection in Gazebo
- [ ] Phase 4 — fault injection, replanning loop, metrics over 20 scenarios, Foxglove/Groot2 dashboard
- [ ] Phase 5 — docs, results, demo
