#!/usr/bin/env bash
# Validator ablation on the symbolic backend: every plan gets an injected LLM-style defect.
#   A) validator + repair loop ON     B) validator verdict IGNORED (plans execute as generated)
# usage: scripts/run_ablation.sh [defect_rate=1.0] [n=20]
cd "$(dirname "$0")/.."
RATE="${1:-1.0}"; N="${2:-20}"
source scripts/env.sh
OUT=runs/ablation; mkdir -p "$OUT"

run_condition () {   # $1 = tag, $2 = enforce true|false
  bash scripts/stop_all.sh
  ros2 launch vatp_ros symbolic.launch.py backend:=mock defect_rate:="$RATE" enforce_validator:="$2" \
      > "$OUT/$1.launch.log" 2>&1 &
  LPID=$!
  sleep 9
  ros2 run vatp_ros benchmark --n "$N" --seed 0 --timeout 120 --max-replans 3 --out "$OUT" --tag "$1" \
      > "$OUT/$1.bench.log" 2>&1
  kill "$LPID" 2>/dev/null
  bash scripts/stop_all.sh
}

run_condition validator-ON  true
run_condition validator-OFF false
echo ABLATION_DONE
