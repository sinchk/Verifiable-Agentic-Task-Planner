#!/usr/bin/env bash
# Stop only the benchmark client (leave the simulation/stack running).
pkill -f "vatp_ros/benchmark" 2>/dev/null
pkill -f "lib/vatp_ros/benchmark" 2>/dev/null
exit 0
