#!/usr/bin/env bash
# Native setup only. Docker already includes build tools and Gazebo.
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PX4_DIR="${PROJECT_DIR}/dependencies/PX4-Autopilot"
if [ ! -e "${PX4_DIR}/.git" ]; then
    echo 'Initialize submodules first: git submodule update --init --recursive' >&2
    exit 1
fi
bash "${PX4_DIR}/Tools/setup/ubuntu.sh"
make -C "${PX4_DIR}" px4_sitl
