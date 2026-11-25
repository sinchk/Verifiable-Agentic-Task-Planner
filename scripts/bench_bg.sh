#!/usr/bin/env bash
# usage: bench_bg.sh <logfile> [benchmark args...]
# Runs the scenario benchmark against an already-running stack (mission.launch.py), detached.
LOG="$1"; shift
cd "$(dirname "$0")/.."
source scripts/env.sh
setsid nohup ros2 run vatp_ros benchmark "$@" > "$LOG" 2>&1 < /dev/null &
disown
echo "benchmark started (log: $LOG)"
