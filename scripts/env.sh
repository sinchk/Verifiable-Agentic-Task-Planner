#!/usr/bin/env bash
# Source me:  source scripts/env.sh
# ROS 2 Jazzy + this workspace + the project venv's site-packages (anthropic, brotli, ...).
_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source /opt/ros/jazzy/setup.bash
[ -f "$_ROOT/install/setup.bash" ] && source "$_ROOT/install/setup.bash"
export PYTHONPATH="$_ROOT/.venv/lib/python3.12/site-packages:${PYTHONPATH:-}"
# API key: read from ~/.bashrc without echoing it (non-interactive shells skip .bashrc)
if [ -z "${ANTHROPIC_API_KEY:-}" ] && grep -q '^export ANTHROPIC_API_KEY=' "$HOME/.bashrc" 2>/dev/null; then
  export "$(grep -m1 '^export ANTHROPIC_API_KEY=' "$HOME/.bashrc" | sed 's/^export //')"
fi
# Gemini key (same mechanism, never echoed)
for _k in GEMINI_API_KEY GOOGLE_API_KEY; do
  if [ -z "${!_k:-}" ] && grep -q "^export $_k=" "$HOME/.bashrc" 2>/dev/null; then
    export "$(grep -m1 "^export $_k=" "$HOME/.bashrc" | sed 's/^export //')"
  fi
done
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-42}"
