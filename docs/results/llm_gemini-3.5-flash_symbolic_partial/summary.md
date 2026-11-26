> **Partial LLM run.** `gemini-3.5-flash`, same settings. The free-tier limit of 20 requests per day ended the run after scenario s12, so s12-s19 are marked NOT EVALUATED (planner API unavailable) and excluded from the rates below. Scenario s09 failed because the model's reply was cut off at the 8,000-token output limit (since raised to 32,768).

# Benchmark summary

| metric | value |
|---|---|
| planner backend | gemini:gemini-3.5-flash |
| scenarios evaluated | 12 of 20 |
| not evaluated (planner API unavailable: quota/outage) | s12, s13, s14, s15, s16, s17, s18, s19 |
| mission success rate | 11/12 = 92% |
| fault scenarios recovered | 3/4 |
| scenarios needing replanning | 3 |
| initial plan latency (median / max, s) | 64.39 / 127.975 |
| replanning latency (median / max, s) | 95.36 / 302.414 |
| BT node count (median) | 9.00 |
| first-attempt plans valid | 12/12 |
| geofence/safety violations | 0 |
| errors/timeouts | 0 |

| id | template | fault | success | replans | plan s | replan s | nodes | wall s |
|---|---|---|---|---|---|---|---|---|
| s00 | conditional_clear_deliver | none | ✅ | 0 | 54.462 | 0.0 | 14→14 | 55.59 |
| s01 | simple_delivery | none | ✅ | 0 | 48.426 | 0.0 | 7→7 | 49.04 |
| s02 | two_item | none | ✅ | 0 | 74.311 | 0.0 | 11→11 | 75.84 |
| s03 | geofence | none | ✅ | 0 | 36.905 | 0.0 | 6→6 | 39.97 |
| s04 | conditional_clear_deliver | none | ✅ | 0 | 117.455 | 0.0 | 13→13 | 122.44 |
| s05 | simple_delivery | none | ✅ | 0 | 93.268 | 0.0 | 7→7 | 111.03 |
| s06 | two_item | none | ✅ | 0 | 127.975 | 0.0 | 11→11 | 129.96 |
| s07 | geofence | none | ✅ | 0 | 43.022 | 0.0 | 6→6 | 47.23 |
| s08 | conditional_clear_deliver | obstacle_spawn | ✅ | 1 | 103.603 | 16.79 | 13→12 | 127.37 |
| s09 | simple_delivery | grasp_fail | ❌ | 0 | 89.805 | 0.0 | 6→6 | 305.14 |
| s10 | two_item | obstacle_spawn | ✅ | 1 | 40.867 | 95.365 | 11→13 | 141.53 |
| s11 | geofence | grasp_fail | ✅ | 1 | 35.088 | 302.414 | 6→9 | 339.37 |
| s12 | conditional_clear_deliver | nav_block | NOT EVALUATED (API unavailable) | | | | | |
| s13 | simple_delivery | place_fail | NOT EVALUATED (API unavailable) | | | | | |
| s14 | two_item | grasp_fail | NOT EVALUATED (API unavailable) | | | | | |
| s15 | geofence | obstacle_spawn | NOT EVALUATED (API unavailable) | | | | | |
| s16 | conditional_clear_deliver | nav_block | NOT EVALUATED (API unavailable) | | | | | |
| s17 | simple_delivery | place_fail | NOT EVALUATED (API unavailable) | | | | | |
| s18 | two_item | obstacle_spawn | NOT EVALUATED (API unavailable) | | | | | |
| s19 | geofence | grasp_fail | NOT EVALUATED (API unavailable) | | | | | |
