#!/usr/bin/env bash
set -euo pipefail
carla_root="${CARLA_ROOT:?Set CARLA_ROOT to your CARLA 0.9.16 installation directory}"
exec bash "$carla_root/CarlaUE4.sh" "$@"
