# Architecture

## Design principle

> **The LLM proposes; a deterministic program disposes.**
> A language model never calls a robot API. It emits a *plan* in a constrained vocabulary; a validator
> that contains no model proves or refutes safety properties of that plan *before the robot moves*;
> only a validated plan is turned into BehaviorTree.CPP XML and executed. When execution fails, the same
> loop runs again on the *current* scene.

```
                     ┌──────────────────────────── RAG memory (BM25) ───────────────────────────┐
                     │  SC-01..09 safety constraints (always)   RP-01..06 recovery (by failure)  │
                     └───────────────┬───────────────────────────────────────────┬───────────────┘
 instruction ─┐                      ▼                                           │
 scene graph ─┴─►  PROMPT ─► LLM (JSON-schema constrained flat BT graph) ─► compile ─► VALIDATOR ─┐
                                   ▲                                                             │ issues
                                   └─────────── repair prompt (validator errors) ◄───────────────┤
                                                                                                 │ valid
                                                   BT.CPP XML (round-tripped, validated *as executed*)
                                                                    ▼
   ┌─────────────────── vatp_bt  (C++ lifecycle node) ───────────────────┐
   │ tick BT.CPP tree @30 Hz, Groot2 on :1667, MissionEvent stream        │
   │ FAILURE → FALLBACK_TRIGGERED → GetWorld (re-perceive) → Replan(...)  │──► planner (same loop)
   │        → validated patch for the REMAINING mission → TREE_SWAPPED    │
   └───────────────┬──────────────────────────────────────────────────────┘
                   ▼  ExecuteSkill actions (one server per skill)
   ┌──────── vatp_ros skill_server (lifecycle) — pluggable backend ────────┐
   │ symbolic : ground-truth world + injected faults        (fast, CI)      │
   │ gazebo   : Nav2 · perception · IK pick/place · real obstacle spawning  │
   └────────────────────────────────────────────────────────────────────────┘
```

## The validator (`vatp_core/validator.py`)

| layer | proves |
|---|---|
| L1 structure | only whitelisted nodes; legal arity; unique names; bounded size/depth/retry-product |
| L2 ports | every attribute declared, typed, in range, naming a real zone/object; no `{blackboard}` indirection |
| L3 semantics | symbolic execution over **all success/failure outcomes**: preconditions at every action (no illegal transitions), keep-out geofence on every leg, transit corridors, payload, capacity |
| L4 goals | every success path of the root establishes declared **and** externally required goals and leaves the gripper empty |

Properties worth knowing:

* Validates the **XML that will execute** (plan → XML → parse → validate), not an intermediate form.
* Fallback branches are analysed from the state in which earlier alternatives *failed* (skills are transactional).
* Dead branches (e.g. the "clear the bay" branch when the bay is believed clear) are still checked statically.
* Messages are constructive (`GEOFENCE_PATH … route via dock, loading_bay`) and feed the repair prompt.
* Mutation-tested: `test_repair_loop_fixes_every_injected_defect_class` injects 7 defect classes and asserts the
  validator rejects each one and the repair loop recovers.

## Why a flat node graph instead of nested JSON/XML from the model?

Grammar-constrained decoding cannot express recursive schemas. A flat `{id, type, params, children[]}` list is
(a) constrainable, and (b) makes dangling children, cycles and shared parents *explicit, reportable errors*.
`bt.compile_plan` turns it into a tree; `bt.to_xml` emits BT.CPP v4 XML.

## Single source of truth

`vatp_core/spec/skills.yaml` defines skills, ports, kinds, pre/effects. It is read by the LLM prompt, the schema
`enum`, the validator, **and the C++ executor** (which registers BT.CPP node types dynamically from it; a gtest
asserts the registration). Adding a skill is a YAML change plus a server implementation.

## Recovery semantics

The executor does not blindly retry. Local failures are absorbed by `RetryUntilSuccessful` nodes the planner
inserts (RP-02/04). When the *tree* fails, the supervisor re-perceives the world, calls `Replan` with the failing
node/skill/code, and receives a plan for the **remaining mission only** (goals already satisfied are dropped,
a held object must be handled first). That plan passes the same validator against the *current* world. The
running tree is swapped at the failure boundary; completed steps are never re-executed. Replans are budgeted
(`max_replans`); exhaustion ends the mission safely rather than looping.

## Simulation notes (honest list of shortcuts)

* **Localisation** is ground truth (`map→odom` from Gazebo's pose) — the standard simulation stand-in for AMCL;
  wheel odometry drifts under slip.
* **Geofences** are enforced three times: the validator (plan time), the Nav2 static map where keep-outs are occupied
  (run time), and a physical barrier in the world. A fourth component *measures* rather than enforces: the runtime geofence monitor
  (`vatp_core/geofence.py`, driven by the Gazebo backend) samples the real robot pose and reports contact and clearance-margin breaches.
* **Perception** is Gazebo ground-truth pose snapshots (`gz topic`), not vision. The VLM hook point is the scene
  graph handed to the planner.
* **Grasping** is physical (friction fingers, verified by lifting the object). Arm motion uses closed-form IK with a
  high approach and a vertical Cartesian descent; MoveIt 2 is the planned drop-in replacement behind `ArmControl`.
* **The offline planner** (`backend=mock`) is a deterministic goal-regression test double, never an LLM result. Its
  latency is meaningless; it exists for CI, defect-injection tests and to validate the pipeline independent of API
  availability.
