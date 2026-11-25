#!/usr/bin/env bash
# Record a real Gazebo mission (cameras + live executor events) into runs/recording_s08/.
# usage: scripts/record_demo.sh [scenario_index=8]
cd "$(dirname "$0")/.."
IDX="${1:-8}"
source scripts/env.sh
OUT="runs/recording_s$(printf %02d "$IDX")"
rm -rf "$OUT"; mkdir -p "$OUT"

bash scripts/stop_all.sh
ros2 launch vatp_sim mission.launch.py backend:=mock scenario:="$IDX" gui:=false > "$OUT/stack.log" 2>&1 &
LPID=$!
sleep 90

ros2 run vatp_sim frame_recorder --ros-args \
  -p out_dir:="$OUT" -p fps:=4.0 \
  -p title:="Verifiable Agentic Task Planner  -  live fault recovery in Gazebo" \
  -p subtitle:="scenario s$(printf %02d "$IDX") | obstacle spawns mid-mission | planner = offline reference (no LLM)" \
  > "$OUT/recorder.log" 2>&1 &
RPID=$!
sleep 4

ros2 run vatp_ros benchmark --n 20 --only "$IDX" --physical --timeout 900 --out "$OUT/bench" --tag demo \
  > "$OUT/bench.log" 2>&1

sleep 3
kill -INT "$RPID" 2>/dev/null
sleep 3
kill "$LPID" 2>/dev/null
bash scripts/stop_all.sh
echo RECORD_DONE
