#!/usr/bin/env bash
# Stop every process this project launches. Matches on full command lines because Linux
# truncates process names to 15 chars (so `pkill -x robot_state_publisher` silently misses).
# Safe to run repeatedly; never matches this script's own command line.
PATTERNS=(
  "ros2 launch" "gz sim" "ros_gz" "parameter_bridge" "robot_state_publisher"
  "static_transform_publisher" "ground_truth_localizer" "controller_manager" "spawner"
  "move_group" "nav2_" "lifecycle_manager" "map_server" "planner_server" "controller_server"
  "behavior_server" "bt_navigator" "planner_node" "skill_server" "bt_executor"
  "gazebo_skill_server" "frame_recorder" "foxglove_bridge" "component_container" "rviz2"
)
for p in "${PATTERNS[@]}"; do
  pkill -f -- "$p" 2>/dev/null
done
sleep 2
for p in "${PATTERNS[@]}"; do
  pkill -9 -f -- "$p" 2>/dev/null
done
sleep 1
exit 0
