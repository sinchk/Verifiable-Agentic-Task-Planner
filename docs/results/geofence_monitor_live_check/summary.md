# Runtime geofence monitor: live check in Gazebo

`scripts/check_geofence_monitor.py` against the full simulation (scenario s03, offline planner). The monitor samples the robot pose (TF) at 10 Hz and measures the clearance of the
robot **envelope** (0.60 x 0.40 m base plus the stowed arm, 0.52 m ahead of `base_footprint`, 0.30 m behind, 0.20 m each side) to every keep-out.
* **violation** = envelope within 2 cm of a keep-out (a physical barrier stops the robot just short of overlap);
* **margin breach** = robot centre closer than 0.3 m to a keep-out (the validator's definition of a too-close leg).

```
check                                                       viol  margin  min ctr m  min fp m  result
1 baseline (robot far from the aisle)                          0       0        3.0      2.48  PASS
2 margin approach (centre 0.25 m from the aisle)               0       1       0.25      0.05  PASS
3 real contact (driven into the barrier)                       1       1       0.25       0.0  PASS
4 events on /vatp/events                                                                       GEOFENCE_MARGIN, GEOFENCE_VIOLATION

ALL CHECKS PASSED
  event: GEOFENCE_MARGIN robot centre 0.25 m from keep-out 'restricted_aisle' (margin 0.30 m) at (6.75, 6.00)
  event: GEOFENCE_VIOLATION robot footprint touches keep-out 'restricted_aisle' at (6.47, 6.00); centre clearance 0.53 m
```

## What each check shows
1. Baseline: robot parked far from the aisle gives no events.
2. Margin approach: robot placed with its centre 0.25 m from the aisle (short side towards it, 0.05 m clear) gives exactly one margin breach and no violation; the measured clearances equal the geometry.
3. Real contact: the robot is *driven* at 0.3 m/s into the 0.3 m high barrier. The **stowed arm touches first**: base_footprint stops 0.51 m short of the barrier face. This is why the envelope includes the arm: a base-only footprint reported 0.21 m clear at that moment.
4. Events: `GEOFENCE_MARGIN` and `GEOFENCE_VIOLATION` reach `/vatp/events` after the next skill call.

## A validated mission with the monitor running ([mission_s03](mission_s03/summary.md))
Scenario s03 (the geofence template: the straight route is illegal, the legal corridor is the loading bay), offline reference planner, Gazebo + Nav2: mission succeeded, **0 contact episodes, 0 margin breaches,
closest approach of the robot centre to the aisle 1.475 m** (the validator only requires 0.3 m; Nav2's inflation keeps the robot much further away).

## Scope
* This is a live check plus one mission. The 20-scenario Gazebo tables in the README were recorded before the monitor existed and carry no geofence measurement; re-running them is the way to measure all 20.
* The envelope covers the stowed arm. During pick and place the arm extends further, but those skills run at zones away from the keep-out, and the monitor samples only the base pose.
