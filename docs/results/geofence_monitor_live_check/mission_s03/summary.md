# Benchmark summary

| metric | value |
|---|---|
| planner backend | mock(defect_rate=0.0) |
| scenarios evaluated | 1 of 1 |
| not evaluated (planner API unavailable: quota/outage) | none |
| mission success rate | 1/1 = 100% |
| fault scenarios recovered | 0/0 |
| scenarios needing replanning | 0 |
| initial plan latency (median / max, s) | 0.02 / 0.017 |
| replanning latency (median / max, s) | n/a / n/a |
| BT node count (median) | 11.00 |
| first-attempt plans valid | 1/1 |
| keep-out contact episodes (safety violations) | 0 |
| clearance-margin breaches (centre < path margin from a keep-out) | 0 |
| closest approach to a keep-out, robot centre (m) | 1.475 |
| errors/timeouts | 0 |

| id | template | fault | success | replans | plan s | replan s | nodes | wall s |
|---|---|---|---|---|---|---|---|---|
| s03 | geofence | none | ✅ | 0 | 0.017 | 0.0 | 11→11 | 116.83 |
