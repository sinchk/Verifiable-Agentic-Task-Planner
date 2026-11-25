> **Run 1 (before carry fixes).** Offline reference planner, Gazebo backend. Failures s00/s08/s18: the small box slipped out of the gripper while driving; the backend kept believing it was held. Fixed afterwards (finger friction, slow carry, drop detection, stray-object recovery) — see run 2.

# Benchmark summary

| metric | value |
|---|---|
| scenarios | 20 |
| mission success rate | 17/20 = 85% |
| fault scenarios recovered | 10/12 |
| scenarios needing replanning | 11 |
| initial plan latency (median / max, s) | 0.01 / 0.01 |
| replanning latency (median / max, s) | 0.01 / 0.011 |
| BT node count (median) | 13.50 |
| first-attempt plans valid | 20/20 |
| geofence/safety violations | 0 |
| errors/timeouts | 0 |

| id | template | fault | success | replans | plan s | replan s | nodes | wall s |
|---|---|---|---|---|---|---|---|---|
| s00 | conditional_clear_deliver | none | ❌ | 3 | 0.01 | 0.008 | 22→13 | 178.93 |
| s01 | simple_delivery | none | ✅ | 0 | 0.007 | 0.0 | 11→11 | 71.41 |
| s02 | two_item | none | ✅ | 0 | 0.007 | 0.0 | 20→20 | 131.05 |
| s03 | geofence | none | ✅ | 0 | 0.007 | 0.0 | 11→11 | 84.72 |
| s04 | conditional_clear_deliver | none | ✅ | 0 | 0.007 | 0.0 | 16→16 | 70.77 |
| s05 | simple_delivery | none | ✅ | 0 | 0.007 | 0.0 | 11→11 | 70.57 |
| s06 | two_item | none | ✅ | 0 | 0.007 | 0.0 | 20→20 | 130.07 |
| s07 | geofence | none | ✅ | 0 | 0.008 | 0.0 | 11→11 | 82.63 |
| s08 | conditional_clear_deliver | obstacle_spawn | ❌ | 3 | 0.007 | 0.009 | 16→3 | 283.81 |
| s09 | simple_delivery | grasp_fail | ✅ | 0 | 0.006 | 0.0 | 11→11 | 77.38 |
| s10 | two_item | obstacle_spawn | ✅ | 1 | 0.008 | 0.01 | 20→29 | 343.84 |
| s11 | geofence | grasp_fail | ✅ | 0 | 0.006 | 0.0 | 11→11 | 88.28 |
| s12 | conditional_clear_deliver | nav_block | ✅ | 1 | 0.007 | 0.009 | 16→7 | 72.54 |
| s13 | simple_delivery | place_fail | ✅ | 1 | 0.006 | 0.006 | 11→3 | 72.0 |
| s14 | two_item | grasp_fail | ✅ | 1 | 0.008 | 0.009 | 20→17 | 155.03 |
| s15 | geofence | obstacle_spawn | ✅ | 1 | 0.007 | 0.01 | 11→29 | 277.76 |
| s16 | conditional_clear_deliver | nav_block | ✅ | 1 | 0.007 | 0.007 | 16→7 | 71.11 |
| s17 | simple_delivery | place_fail | ✅ | 1 | 0.007 | 0.007 | 11→3 | 74.51 |
| s18 | two_item | obstacle_spawn | ❌ | 3 | 0.007 | 0.011 | 20→37 | 193.39 |
| s19 | geofence | grasp_fail | ✅ | 1 | 0.008 | 0.007 | 11→9 | 93.48 |
