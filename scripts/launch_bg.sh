#!/usr/bin/env bash
# usage: launch_bg.sh <logfile> <ros2 launch args...>   (detached; survives the calling shell)
LOG="$1"; shift
cd "$(dirname "$0")/.."
source scripts/env.sh
setsid nohup ros2 launch "$@" > "$LOG" 2>&1 < /dev/null &
disown
echo "started: ros2 launch $* (log: $LOG)"
