#!/usr/bin/env bash
# System dependencies for the Verifiable Agentic Task Planner.
# Target: Ubuntu 24.04 + ROS 2 Jazzy + Gazebo Harmonic.
# Usage: sudo bash scripts/install_system_deps.sh
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo: sudo bash $0" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive

PKGS=(
  # Python tooling
  python3-pip python3-venv python3-colcon-common-extensions ros-dev-tools
  # ros2_control + Gazebo integration
  ros-jazzy-ros2-control ros-jazzy-ros2-controllers ros-jazzy-gz-ros2-control
  # Robot description / TF tooling
  ros-jazzy-joint-state-publisher ros-jazzy-joint-state-publisher-gui
  ros-jazzy-tf2-tools ros-jazzy-rqt-graph
  # Dashboards
  ros-jazzy-foxglove-bridge ros-jazzy-rosbridge-server
  # Manipulation
  ros-jazzy-moveit
)

apt-get update
apt-get install -y "${PKGS[@]}"

echo
echo "Done. Verify with: command -v colcon && python3 -m venv /tmp/vt && echo ok"
