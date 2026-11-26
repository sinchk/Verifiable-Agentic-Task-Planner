# Validator ablation: injected defects, symbolic backend (20 scenarios)

Offline reference planner, **a defect injected into the first answer of every plan and replan** (7 defect classes), symbolic skill backend, seed 0.
Condition ON = full system (validator rejects, repair loop regenerates). Condition OFF = the validator still runs but its verdict is ignored and there is no repair loop:
the first answer executes as generated. (A plan that cannot even be compiled into a tree cannot run in either condition.)

| | gate ON | gate OFF |
|---|---|---|
| mission success | 20/20 | 1/20 |
| injected faults recovered | 12/12 | 1/12 |
| planner calls (plans + replans) | 29 | 39 |
| planner calls whose first answer the validator flags | 29 | 39 |
| repairs performed | 20 | 0 |
| total replans | 9 | 18 |
| geofence crossings counted by the simulator | 0 | 0 |

## How the 20 missions ended

| outcome | gate ON | gate OFF |
|---|---|---|
| success | 20 | 1 |
| executor refused a hallucinated skill (BT.CPP registry) | 0 | 7 |
| replan budget exhausted on PLAN_INVALID | 0 | 5 |
| tree reported complete, goal NOT achieved | 0 | 6 |
| other (no result message) | 0 | 1 |

## Reading it
* The gate turns defective plans into repaired plans: every flagged answer is rejected, regenerated with the validator's error text, and the mission succeeds.
* Without the gate the same defective answers execute. Most missions fail; the most dangerous outcome is the **false success**: the executor reports the tree complete while the goal
  was not achieved. Only the benchmark's independent goal check against ground truth reveals it.
* Hallucinated skills are also stopped by BT.CPP's node registry ("Node not recognized"), a second line of defence. The other defect classes (missing navigation, ungrounded
  parameters, dropped placement, retry explosion) are not caught by the registry: they reach the skill servers and either fail there at run time or silently miss the goal.
* The simulator counted **0 geofence crossings in both conditions**: with this defect mix no executed plan produced a counted straight-leg crossing, so this experiment does **not** show geofence harm.
* Scope: defects are injected at a 100% rate by a test double, so this measures the gate's effect on injected defects, not how often a real LLM errs (see the LLM runs for that).

Per-condition tables: [gate ON](gate_on/summary.md) · [gate OFF](gate_off/summary.md).
