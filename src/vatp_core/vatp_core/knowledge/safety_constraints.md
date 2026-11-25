# Safety constraints

## SC-01 Geofence keep-out zones
tags: geofence keepout restricted aisle navigate path route
The robot must never enter or drive through a keep-out geofence (for example the restricted aisle), nor come within the path clearance margin. A direct NavigateTo leg whose straight line crosses a keep-out is illegal. Insert intermediate NavigateTo waypoints (other legal zones such as loading_bay) so every leg is keep-out free. The validator rejects GEOFENCE_PATH and GEOFENCE_TARGET violations.

## SC-02 Payload limit
tags: payload mass weight pick grasp heavy limit
Never pick an object whose mass exceeds the robot payload limit. Objects flagged NOT-GRASPABLE must never be picked. The validator rejects PAYLOAD_EXCEEDED and NOT_GRASPABLE.

## SC-03 One object at a time
tags: gripper holding pick place single object trips sequential
The gripper holds at most one object. Place the held object before picking another. Multi-object missions need one pick-and-place trip per object. Every success path must end with an empty gripper (END_HOLDING is rejected).

## SC-04 Navigate before manipulating
tags: navigate pick place position at zone precondition order
PickObject requires the robot to be at the zone containing the object. PlaceObject requires the robot to be at the destination zone. Always NavigateTo the zone first. The validator rejects NOT_AT_OBJECT and NOT_AT_ZONE.

## SC-05 Zone capacity and no-placing zones
tags: place capacity zone full dock no-placing staging
Do not place objects in zones marked NO-PLACING (e.g. the charging dock) or in zones already at capacity. Use the staging zone to park obstacles that were cleared out of the way.

## SC-06 Verify before assuming
tags: check clear sensing condition blocked loading bay conditional if
When the task is conditional ("if blocked ..."), use a condition node (CheckZoneClear / CheckObjectAt) inside a Fallback so the clearing branch only runs when needed: Fallback[ CheckZoneClear(z), Sequence[ clear steps ] ].

## SC-07 Bounded behaviour
tags: retry bounded loop timeout infinite attempts
Retries must be bounded (num_attempts 1..5, nested products at most 10). Never construct unbounded loops. Prefer a final RequestHumanHelp inside a Fallback over endless retries.

## SC-08 Grounded parameters only
tags: parameters ports blackboard grounded names zone object
Every port value must be a literal name of a known zone or object from the scene description. Blackboard references such as {target} are rejected.

## SC-09 Declare goals
tags: goals postcondition verify object_at gripper_empty zone_clear
Declare the mission postconditions in the plan goals list (object_at, robot_at, gripper_empty, zone_clear). The validator proves each goal holds on every success path of the tree.
