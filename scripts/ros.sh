#!/usr/bin/env bash
# Source the compiled overlay before invoking a ROS command.
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ ! -f "$project_root/ros_ws/install/setup.bash" ]]; then
  echo 'ROS overlay missing. Run: pixi run -e ros build_bridge' >&2
  exit 1
fi
# ROS-generated setup scripts can reference unset variables.
set +u
source "$project_root/ros_ws/install/setup.bash"
set -u
exec "$@"
