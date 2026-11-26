#!/usr/bin/env bash
# Benchmark an LLM planner on the 20-scenario suite using the fast symbolic skill backend.
# usage: scripts/run_llm_symbolic.sh <gemini-model> <tag> [thinking-level]
# Needs GEMINI_API_KEY (loaded by scripts/env.sh). Results: runs/llm/<stamp>-<tag>/
cd "$(dirname "$0")/.."
MODEL="$1"; TAG="$2"; THINK="${3:-}"
source scripts/env.sh
export VATP_GEMINI_MODEL="$MODEL"
[ -n "$THINK" ] && export VATP_GEMINI_THINKING="$THINK"
OUT=runs/llm; mkdir -p "$OUT"
bash scripts/stop_all.sh
ros2 launch vatp_ros symbolic.launch.py backend:=gemini > "$OUT/$TAG.launch.log" 2>&1 &
LPID=$!
sleep 10
# a slow model response must not be miscounted as an executor timeout
ros2 param set /vatp_bt_executor service_timeout_s 600.0 > "$OUT/$TAG.param.log" 2>&1
ros2 run vatp_ros benchmark --n 20 --seed 0 --timeout 1200 --max-replans 3 --out "$OUT" --tag "$TAG" > "$OUT/$TAG.bench.log" 2>&1
kill "$LPID" 2>/dev/null
bash scripts/stop_all.sh
echo "LLM_BENCH_DONE $TAG"
