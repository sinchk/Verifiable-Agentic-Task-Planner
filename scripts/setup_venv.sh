#!/usr/bin/env bash
# Create the project venv (sees system rclpy) and install Python deps.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -q -r requirements.txt
.venv/bin/pip install -q -e src/vatp_core --no-deps --no-build-isolation 2>/dev/null || true
echo "venv ready: source .venv/bin/activate"
