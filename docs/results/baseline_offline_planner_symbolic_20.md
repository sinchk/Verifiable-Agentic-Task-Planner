> **Offline reference planner** (no LLM) on the symbolic skill backend — validates the ROS 2 closed loop and metrics pipeline; latencies are NOT LLM latencies.

# Benchmark summary

| metric | value |
|---|---|
| scenarios | 20 |
| mission success rate | 20/20 = 100% |
| fault scenarios recovered | 12/12 |
| scenarios needing replanning | 9 |
| initial plan latency (median / max, s) | 0.01 / 0.017 |
| replanning latency (median / max, s) | 0.01 / 0.017 |
| BT node count (median) | 13.50 |
| first-attempt plans valid | 20/20 |
| geofence/safety violations | 0 |
| errors/timeouts | 0 |

| id | template | fault | success | replans | plan s | replan s | nodes | wall s |
|---|---|---|---|---|---|---|---|---|
| s00 | conditional_clear_deliver | none | ✅ | 0 | 0.017 | 0.0 | 22→22 | 2.73 |
| s01 | simple_delivery | none | ✅ | 0 | 0.013 | 0.0 | 11→11 | 2.79 |
| s02 | two_item | none | ✅ | 0 | 0.014 | 0.0 | 20→20 | 2.52 |
| s03 | geofence | none | ✅ | 0 | 0.013 | 0.0 | 11→11 | 1.32 |
| s04 | conditional_clear_deliver | none | ✅ | 0 | 0.013 | 0.0 | 16→16 | 0.98 |
| s05 | simple_delivery | none | ✅ | 0 | 0.014 | 0.0 | 11→11 | 0.75 |
| s06 | two_item | none | ✅ | 0 | 0.015 | 0.0 | 20→20 | 2.33 |
| s07 | geofence | none | ✅ | 0 | 0.013 | 0.0 | 11→11 | 1.09 |
| s08 | conditional_clear_deliver | obstacle_spawn | ✅ | 1 | 0.014 | 0.015 | 22→21 | 2.46 |
| s09 | simple_delivery | grasp_fail | ✅ | 0 | 0.014 | 0.0 | 11→11 | 1.84 |
| s10 | two_item | obstacle_spawn | ✅ | 1 | 0.014 | 0.017 | 20→29 | 3.61 |
| s11 | geofence | grasp_fail | ✅ | 0 | 0.013 | 0.0 | 11→11 | 4.05 |
| s12 | conditional_clear_deliver | nav_block | ✅ | 1 | 0.015 | 0.013 | 22→15 | 5.01 |
| s13 | simple_delivery | place_fail | ✅ | 1 | 0.006 | 0.005 | 11→3 | 5.53 |
| s14 | two_item | grasp_fail | ✅ | 0 | 0.007 | 0.0 | 20→20 | 2.76 |
| s15 | geofence | obstacle_spawn | ✅ | 1 | 0.007 | 0.011 | 11→29 | 8.29 |
| s16 | conditional_clear_deliver | nav_block | ✅ | 1 | 0.006 | 0.01 | 16→7 | 6.75 |
| s17 | simple_delivery | place_fail | ✅ | 1 | 0.008 | 0.009 | 11→3 | 2.64 |
| s18 | two_item | obstacle_spawn | ✅ | 1 | 0.007 | 0.011 | 20→29 | 5.64 |
| s19 | geofence | grasp_fail | ✅ | 1 | 0.007 | 0.006 | 11→9 | 2.0 |
