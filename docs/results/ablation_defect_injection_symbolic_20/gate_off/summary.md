> Offline reference planner with a defect injected into the first answer of every plan and replan (`defect_rate=1.0`), symbolic backend, seed 0. Validator IGNORED (plans execute as generated).

# Benchmark summary

| metric | value |
|---|---|
| planner backend | mock(defect_rate=1.0) |
| scenarios evaluated | 20 of 20 |
| not evaluated (planner API unavailable: quota/outage) | none |
| mission success rate | 1/20 = 5% |
| fault scenarios recovered | 1/12 |
| scenarios needing replanning | 8 |
| initial plan latency (median / max, s) | 0.01 / 0.015 |
| replanning latency (median / max, s) | 0.01 / 0.013 |
| BT node count (median) | 11.00 |
| first-attempt plans valid | 0/20 |
| geofence/safety violations | 0 |
| errors/timeouts | 0 |

| id | template | fault | success | replans | plan s | replan s | nodes | wall s |
|---|---|---|---|---|---|---|---|---|
| s00 | conditional_clear_deliver | none | ❌ | 3 | 0.014 | 0.013 | 22→5 | 9.51 |
| s01 | simple_delivery | none | ❌ | 0 | 0.014 | 0.0 | 11→11 | 5.21 |
| s02 | two_item | none | ❌ | 0 | 0.008 | 0.0 | 18→18 | 8.6 |
| s03 | geofence | none | ❌ | 0 | 0.007 | 0.0 | 9→9 | 0.69 |
| s04 | conditional_clear_deliver | none | ❌ | 3 | 0.007 | 0.008 | 16→5 | 2.36 |
| s05 | simple_delivery | none | ❌ | 0 | 0.011 | 0.0 | 11→11 | 1.55 |
| s06 | two_item | none | ❌ | 0 | 0.015 | 0.0 | 18→18 | 3.58 |
| s07 | geofence | none | ❌ | 0 | 0.013 | 0.0 | 9→9 | 2.38 |
| s08 | conditional_clear_deliver | obstacle_spawn | ❌ | 3 | 0.013 | 0.012 | 22→5 | 2.25 |
| s09 | simple_delivery | grasp_fail | ❌ | 0 | 0.011 | 0.0 | 11→11 | 0.89 |
| s10 | two_item | obstacle_spawn | ❌ | 0 | 0.0 | 0.0 | 0→0 | 17.45 |
| s11 | geofence | grasp_fail | ❌ | 0 | 0.007 | 0.0 | 9→9 | 18.43 |
| s12 | conditional_clear_deliver | nav_block | ❌ | 3 | 0.007 | 0.007 | 22→5 | 2.04 |
| s13 | simple_delivery | place_fail | ❌ | 0 | 0.006 | 0.0 | 11→11 | 0.74 |
| s14 | two_item | grasp_fail | ❌ | 0 | 0.01 | 0.0 | 18→18 | 1.28 |
| s15 | geofence | obstacle_spawn | ❌ | 1 | 0.013 | 0.013 | 9→29 | 0.84 |
| s16 | conditional_clear_deliver | nav_block | ❌ | 3 | 0.012 | 0.012 | 16→5 | 2.7 |
| s17 | simple_delivery | place_fail | ❌ | 0 | 0.011 | 0.0 | 11→11 | 11.38 |
| s18 | two_item | obstacle_spawn | ✅ | 1 | 0.008 | 0.008 | 18→29 | 20.99 |
| s19 | geofence | grasp_fail | ❌ | 1 | 0.007 | 0.006 | 9→9 | 5.83 |
