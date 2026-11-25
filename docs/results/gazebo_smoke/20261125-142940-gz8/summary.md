# Benchmark summary

| metric | value |
|---|---|
| scenarios | 1 |
| mission success rate | 1/1 = 100% |
| fault scenarios recovered | 1/1 |
| scenarios needing replanning | 1 |
| initial plan latency (median / max, s) | 0.01 / 0.007 |
| replanning latency (median / max, s) | 0.01 / 0.008 |
| BT node count (median) | 16.00 |
| first-attempt plans valid | 1/1 |
| geofence/safety violations | 0 |
| errors/timeouts | 0 |

| id | template | fault | success | replans | plan s | replan s | nodes | wall s |
|---|---|---|---|---|---|---|---|---|
| s08 | conditional_clear_deliver | obstacle_spawn | ✅ | 1 | 0.007 | 0.008 | 16→21 | 202.79 |
