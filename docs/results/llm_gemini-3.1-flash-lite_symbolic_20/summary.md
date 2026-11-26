> **LLM planner run.** `gemini-3.1-flash-lite`, temperature 0, symbolic skill backend, scenario seed 0, max 2 repairs and 3 replans per mission. Plan and replan latencies are real model latencies (they include retries on server errors). All 20 scenarios were evaluated.

# Benchmark summary

| metric | value |
|---|---|
| planner backend | gemini:gemini-3.1-flash-lite |
| scenarios evaluated | 20 of 20 |
| not evaluated (planner API unavailable: quota/outage) | none |
| mission success rate | 14/20 = 70% |
| fault scenarios recovered | 7/12 |
| scenarios needing replanning | 5 |
| initial plan latency (median / max, s) | 6.68 / 140.222 |
| replanning latency (median / max, s) | 7.13 / 11.462 |
| BT node count (median) | 10.50 |
| first-attempt plans valid | 10/20 |
| geofence/safety violations | 0 |
| errors/timeouts | 0 |

| id | template | fault | success | replans | plan s | replan s | nodes | wall s |
|---|---|---|---|---|---|---|---|---|
| s00 | conditional_clear_deliver | none | ✅ | 0 | 7.629 | 0.0 | 15→15 | 22.14 |
| s01 | simple_delivery | none | ❌ | 0 | 9.83 | 0.0 | 0→0 | 10.15 |
| s02 | two_item | none | ✅ | 0 | 8.453 | 0.0 | 14→14 | 14.33 |
| s03 | geofence | none | ✅ | 0 | 2.678 | 0.0 | 7→7 | 4.13 |
| s04 | conditional_clear_deliver | none | ✅ | 0 | 140.222 | 0.0 | 14→14 | 143.27 |
| s05 | simple_delivery | none | ✅ | 0 | 2.851 | 0.0 | 7→7 | 4.51 |
| s06 | two_item | none | ✅ | 0 | 6.904 | 0.0 | 15→15 | 9.9 |
| s07 | geofence | none | ✅ | 0 | 4.752 | 0.0 | 8→8 | 5.55 |
| s08 | conditional_clear_deliver | obstacle_spawn | ✅ | 1 | 6.942 | 8.036 | 15→13 | 18.91 |
| s09 | simple_delivery | grasp_fail | ✅ | 0 | 4.588 | 0.0 | 8→8 | 7.49 |
| s10 | two_item | obstacle_spawn | ✅ | 1 | 6.269 | 6.879 | 13→12 | 15.6 |
| s11 | geofence | grasp_fail | ✅ | 0 | 4.352 | 0.0 | 7→7 | 52.07 |
| s12 | conditional_clear_deliver | nav_block | ✅ | 2 | 14.318 | 11.462 | 15→9 | 43.53 |
| s13 | simple_delivery | place_fail | ❌ | 0 | 2.488 | 0.0 | 7→7 | 19.66 |
| s14 | two_item | grasp_fail | ✅ | 1 | 6.134 | 7.135 | 15→14 | 15.76 |
| s15 | geofence | obstacle_spawn | ❌ | 0 | 13.062 | 0.0 | 7→7 | 27.56 |
| s16 | conditional_clear_deliver | nav_block | ✅ | 3 | 7.598 | 5.628 | 14→11 | 25.52 |
| s17 | simple_delivery | place_fail | ❌ | 0 | 4.364 | 0.0 | 7→7 | 15.97 |
| s18 | two_item | obstacle_spawn | ❌ | 0 | 7.203 | 0.0 | 13→13 | 51.1 |
| s19 | geofence | grasp_fail | ❌ | 0 | 6.448 | 0.0 | 7→7 | 25.45 |
