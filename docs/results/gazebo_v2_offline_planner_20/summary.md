> **Run 2 (after carry fixes).** Gazebo Harmonic backend, Nav2, physical pick/place. Plans come from the **offline reference planner** (no LLM) so plan/replan latencies here are NOT LLM latencies; they validate the pipeline. Wall times are longer than run 1 because the robot now drives slowly while carrying.

# Benchmark summary

| metric | value |
|---|---|
| scenarios | 20 |
| mission success rate | 20/20 = 100% |
| fault scenarios recovered | 12/12 |
| scenarios needing replanning | 9 |
| initial plan latency (median / max, s) | 0.01 / 0.009 |
| replanning latency (median / max, s) | 0.01 / 0.01 |
| BT node count (median) | 13.50 |
| first-attempt plans valid | 20/20 |
| geofence/safety violations | 0 |
| errors/timeouts | 0 |

| id | template | fault | success | replans | plan s | replan s | nodes | wall s |
|---|---|---|---|---|---|---|---|---|
| s00 | conditional_clear_deliver | none | ✅ | 0 | 0.007 | 0.0 | 22→22 | 173.46 |
| s01 | simple_delivery | none | ✅ | 0 | 0.007 | 0.0 | 11→11 | 96.51 |
| s02 | two_item | none | ✅ | 0 | 0.007 | 0.0 | 20→20 | 174.27 |
| s03 | geofence | none | ✅ | 0 | 0.007 | 0.0 | 11→11 | 117.67 |
| s04 | conditional_clear_deliver | none | ✅ | 0 | 0.007 | 0.0 | 16→16 | 103.92 |
| s05 | simple_delivery | none | ✅ | 0 | 0.007 | 0.0 | 11→11 | 96.91 |
| s06 | two_item | none | ✅ | 0 | 0.007 | 0.0 | 20→20 | 172.84 |
| s07 | geofence | none | ✅ | 0 | 0.007 | 0.0 | 11→11 | 117.62 |
| s08 | conditional_clear_deliver | obstacle_spawn | ✅ | 2 | 0.006 | 0.008 | 16→13 | 387.65 |
| s09 | simple_delivery | grasp_fail | ✅ | 0 | 0.006 | 0.0 | 11→11 | 105.49 |
| s10 | two_item | obstacle_spawn | ✅ | 1 | 0.008 | 0.01 | 20→29 | 444.46 |
| s11 | geofence | grasp_fail | ✅ | 0 | 0.007 | 0.0 | 11→11 | 121.79 |
| s12 | conditional_clear_deliver | nav_block | ✅ | 1 | 0.008 | 0.007 | 16→7 | 99.06 |
| s13 | simple_delivery | place_fail | ✅ | 1 | 0.007 | 0.006 | 11→3 | 96.98 |
| s14 | two_item | grasp_fail | ✅ | 0 | 0.008 | 0.0 | 20→20 | 180.64 |
| s15 | geofence | obstacle_spawn | ✅ | 1 | 0.008 | 0.01 | 11→29 | 366.57 |
| s16 | conditional_clear_deliver | nav_block | ✅ | 1 | 0.007 | 0.008 | 16→7 | 97.26 |
| s17 | simple_delivery | place_fail | ✅ | 1 | 0.006 | 0.006 | 11→3 | 101.54 |
| s18 | two_item | obstacle_spawn | ✅ | 1 | 0.009 | 0.01 | 20→29 | 464.17 |
| s19 | geofence | grasp_fail | ✅ | 1 | 0.007 | 0.008 | 11→9 | 125.13 |
