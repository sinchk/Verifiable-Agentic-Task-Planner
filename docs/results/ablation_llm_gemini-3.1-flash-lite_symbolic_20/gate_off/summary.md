> `gemini-3.1-flash-lite`, temperature 0, symbolic backend, seed 0. Validator verdict IGNORED: every first answer (and every replan) executes as generated, one model request each, no repair loop. The gate-ON run for comparison is [llm_gemini-3.1-flash-lite_symbolic_20](../../llm_gemini-3.1-flash-lite_symbolic_20/summary.md).

# Benchmark summary

| metric | value |
|---|---|
| planner backend | gemini:gemini-3.1-flash-lite |
| scenarios evaluated | 20 of 20 |
| not evaluated (planner API unavailable: quota/outage) | none |
| mission success rate | 17/20 = 85% |
| fault scenarios recovered | 9/12 |
| scenarios needing replanning | 7 |
| initial plan latency (median / max, s) | 2.59 / 51.016 |
| replanning latency (median / max, s) | 2.78 / 105.645 |
| BT node count (median) | 10.50 |
| first-attempt plans valid | 10/20 |
| geofence/safety violations | 2 |
| errors/timeouts | 0 |

| id | template | fault | success | replans | plan s | replan s | nodes | wall s |
|---|---|---|---|---|---|---|---|---|
| s00 | conditional_clear_deliver | none | ✅ | 0 | 2.497 | 0.0 | 14→14 | 3.6 |
| s01 | simple_delivery | none | ✅ | 0 | 2.849 | 0.0 | 9→9 | 3.48 |
| s02 | two_item | none | ✅ | 0 | 2.604 | 0.0 | 14→14 | 4.06 |
| s03 | geofence | none | ✅ | 0 | 2.39 | 0.0 | 7→7 | 5.74 |
| s04 | conditional_clear_deliver | none | ✅ | 0 | 10.34 | 0.0 | 14→14 | 14.17 |
| s05 | simple_delivery | none | ✅ | 0 | 51.016 | 0.0 | 7→7 | 52.57 |
| s06 | two_item | none | ✅ | 0 | 3.122 | 0.0 | 14→14 | 9.11 |
| s07 | geofence | none | ✅ | 0 | 9.732 | 0.0 | 8→8 | 10.49 |
| s08 | conditional_clear_deliver | obstacle_spawn | ❌ | 0 | 3.108 | 0.0 | 14→14 | 6.09 |
| s09 | simple_delivery | grasp_fail | ✅ | 0 | 2.112 | 0.0 | 8→8 | 8.14 |
| s10 | two_item | obstacle_spawn | ✅ | 0 | 2.572 | 0.0 | 12→12 | 11.68 |
| s11 | geofence | grasp_fail | ✅ | 0 | 2.516 | 0.0 | 7→7 | 3.53 |
| s12 | conditional_clear_deliver | nav_block | ✅ | 2 | 5.328 | 3.68 | 15→16 | 16.35 |
| s13 | simple_delivery | place_fail | ❌ | 1 | 2.249 | 2.093 | 7→8 | 10.93 |
| s14 | two_item | grasp_fail | ✅ | 1 | 2.761 | 105.645 | 14→13 | 111.03 |
| s15 | geofence | obstacle_spawn | ✅ | 2 | 2.093 | 2.578 | 7→4 | 13.52 |
| s16 | conditional_clear_deliver | nav_block | ✅ | 3 | 2.642 | 2.784 | 14→11 | 19.02 |
| s17 | simple_delivery | place_fail | ❌ | 1 | 1.848 | 2.918 | 7→8 | 15.42 |
| s18 | two_item | obstacle_spawn | ✅ | 0 | 2.386 | 0.0 | 13→13 | 5.13 |
| s19 | geofence | grasp_fail | ✅ | 1 | 2.141 | 2.774 | 7→9 | 13.28 |
