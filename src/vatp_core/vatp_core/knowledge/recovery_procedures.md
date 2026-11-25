# Recovery procedures

## RP-01 UNEXPECTED_OBSTACLE in a zone
tags: UNEXPECTED_OBSTACLE ZONE_OCCUPIED obstacle blocked zone loading_bay new object
An object that was not in the plan appeared in a zone the mission needs. Recovery: update the scene (the obstacle is now listed in the zone), NavigateTo the zone, PickObject the obstacle if graspable and within payload, NavigateTo staging, PlaceObject it in staging, then resume the remaining mission steps. If the obstacle is not graspable or too heavy, RequestHumanHelp.

## RP-02 GRASP_FAILED
tags: GRASP_FAILED grasp pick failed retry regrasp slip
A grasp failed. Recovery: retry the PickObject up to 2 more times using RetryUntilSuccessful (num_attempts 3). If it still fails, Fallback to RequestHumanHelp. Do not change zones between attempts; the robot is already positioned correctly.

## RP-03 NAV_BLOCKED / NAV_TIMEOUT
tags: NAV_BLOCKED NAV_TIMEOUT navigate blocked path timeout costmap
Navigation failed. Recovery: Wait 3 seconds, retry NavigateTo once. If the destination zone is occupied by an object, treat as UNEXPECTED_OBSTACLE (RP-01). If it keeps failing, RequestHumanHelp.

## RP-04 PLACE_FAILED
tags: PLACE_FAILED place failed drop release
A placement failed while the object is still held. Recovery: retry PlaceObject once; if it fails again place the object in staging (NavigateTo staging then PlaceObject) so the gripper is empty, then RequestHumanHelp.

## RP-05 Replanning scope
tags: replan patch subtree remaining mission resume completed steps
When replanning mid-mission, produce a tree for the REMAINING mission only, starting from the current scene (robot position, held object, object locations). Never repeat steps whose effects already hold. The gripper may currently be holding an object: place it or use it before picking something else.

## RP-06 Escalation
tags: escalate human help abort safe unrecoverable
If no safe recovery exists, finish with RequestHumanHelp and leave the robot stationary with the gripper state reported via ReportStatus. Never improvise skills outside the skill library.

## RP-07 OBJECT_LOST dropped payload
tags: OBJECT_LOST dropped lost slipped payload carrying floor gripper_empty
The held object slipped out of the gripper while driving. The gripper is now empty and the object lies on the floor near the robot, listed in the nearest zone. Recovery: NavigateTo that zone, PickObject the object again (RetryUntilSuccessful, 3 attempts), then continue the remaining mission. Prefer fewer, shorter drives while carrying.
