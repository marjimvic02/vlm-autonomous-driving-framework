#!/usr/bin/env bash
# Build against the active Pixi ROS environment from any checkout location.
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
env_prefix="${CONDA_PREFIX:?Run this script with pixi run -e ros build_bridge}"
cd "$project_root/ros_ws"
colcon --log-base "${TFM_BUILD_LOG_DIR:-log}" build --symlink-install \
  --build-base "${TFM_BUILD_DIR:-build}" \
  --install-base "${TFM_INSTALL_DIR:-install}" \
  --packages-skip carla_ad_demo carla_walker_agent \
  --cmake-args \
    -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
    "-DPython_ROOT_DIR=$env_prefix" \
    "-DPython_EXECUTABLE=$env_prefix/bin/python3.11" \
    "-DPython_INCLUDE_DIR=$env_prefix/include/python3.11" \
    "-DPython_LIBRARY=$env_prefix/lib/libpython3.11.so" \
    "-DPython_NumPy_INCLUDE_DIR=$env_prefix/lib/python3.11/site-packages/numpy/core/include" \
    "-DPython3_ROOT_DIR=$env_prefix" \
    "-DPython3_EXECUTABLE=$env_prefix/bin/python3.11" \
    "-DPython3_INCLUDE_DIR=$env_prefix/include/python3.11" \
    "-DPython3_LIBRARY=$env_prefix/lib/libpython3.11.so" \
    "-DPython3_NumPy_INCLUDE_DIR=$env_prefix/lib/python3.11/site-packages/numpy/core/include"
