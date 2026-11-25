# Roadmap
- [x] Phase 1 — core: skill library, world model, BT validator, RAG, LLM planner, scenario suite, tests
- [x] Phase 2 — ROS 2: interfaces, planner node, BT.CPP executor (lifecycle), lifecycle skill servers (symbolic backend + fault injection), 20-scenario benchmark
- [~] Phase 3 — Gazebo Harmonic: robot/world/controllers/Nav2 verified; physical top-down pick AND place verified (crate lifted, carried, placed within ~1 cm) using analytic IK + perception-driven targets. NEXT: wrap into `gazebo_skill_server` (Nav2 NavigateTo, gz perception for Check*, ArmControl for Pick/Place), fault injection in Gazebo, MoveIt 2 as an alternative pick backend, Foxglove dashboard
- [ ] Phase 4 — fault injection, replanning loop, metrics over 20 scenarios, Foxglove/Groot2 dashboard
- [ ] Phase 5 — docs, results, demo
