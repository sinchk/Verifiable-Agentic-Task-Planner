> Offline reference planner with a defect injected into the first answer of every plan and replan (`defect_rate=1.0`), symbolic backend, seed 0. Validator ENFORCED (reject + repair).

# Benchmark summary

| metric | value |
|---|---|
| planner backend | mock(defect_rate=1.0) |
| scenarios evaluated | 20 of 20 |
| not evaluated (planner API unavailable: quota/outage) | none |
| mission success rate | 20/20 = 100% |
| fault scenarios recovered | 12/12 |
| scenarios needing replanning | 9 |
| initial plan latency (median / max, s) | 0.01 / 0.023 |
| replanning latency (median / max, s) | 0.01 / 0.029 |
| BT node count (median) | 13.50 |
| first-attempt plans valid | 0/20 |
| geofence/safety violations | 0 |
| errors/timeouts | 0 |

| id | template | fault | success | replans | plan s | replan s | nodes | wall s |
|---|---|---|---|---|---|---|---|---|
| s00 | conditional_clear_deliver | none | ✅ | 0 | 0.017 | 0.0 | 22→22 | 2.13 |
| s01 | simple_delivery | none | ✅ | 0 | 0.014 | 0.0 | 11→11 | 0.63 |
| s02 | two_item | none | ✅ | 0 | 0.023 | 0.0 | 20→20 | 1.77 |
| s03 | geofence | none | ✅ | 0 | 0.015 | 0.0 | 11→11 | 1.12 |
| s04 | conditional_clear_deliver | none | ✅ | 0 | 0.017 | 0.0 | 16→16 | 2.2 |
| s05 | simple_delivery | none | ✅ | 0 | 0.01 | 0.0 | 11→11 | 4.33 |
| s06 | two_item | none | ✅ | 0 | 0.009 | 0.0 | 20→20 | 1.2 |
| s07 | geofence | none | ✅ | 0 | 0.012 | 0.0 | 11→11 | 0.83 |
| s08 | conditional_clear_deliver | obstacle_spawn | ✅ | 1 | 0.019 | 0.019 | 22→21 | 3.62 |
| s09 | simple_delivery | grasp_fail | ✅ | 0 | 0.014 | 0.0 | 11→11 | 1.39 |
| s10 | two_item | obstacle_spawn | ✅ | 1 | 0.017 | 0.029 | 20→29 | 3.57 |
| s11 | geofence | grasp_fail | ✅ | 0 | 0.008 | 0.0 | 11→11 | 5.5 |
| s12 | conditional_clear_deliver | nav_block | ✅ | 1 | 0.008 | 0.008 | 22→15 | 4.25 |
| s13 | simple_delivery | place_fail | ✅ | 1 | 0.007 | 0.007 | 11→3 | 1.88 |
| s14 | two_item | grasp_fail | ✅ | 0 | 0.009 | 0.0 | 20→20 | 1.89 |
| s15 | geofence | obstacle_spawn | ✅ | 1 | 0.012 | 0.02 | 11→29 | 3.86 |
| s16 | conditional_clear_deliver | nav_block | ✅ | 1 | 0.008 | 0.008 | 16→7 | 0.95 |
| s17 | simple_delivery | place_fail | ✅ | 1 | 0.006 | 0.006 | 11→3 | 5.5 |
| s18 | two_item | obstacle_spawn | ✅ | 1 | 0.009 | 0.011 | 20→29 | 6.31 |
| s19 | geofence | grasp_fail | ✅ | 1 | 0.008 | 0.008 | 11→9 | 2.98 |
