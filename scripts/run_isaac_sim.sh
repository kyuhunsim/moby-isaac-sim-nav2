#!/usr/bin/env bash
# Start Isaac Sim with the ROS 2 environment expected by this workspace.
set -eo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
isaac_root="${ISAAC_SIM_ROOT:?Set ISAAC_SIM_ROOT to your Isaac Sim 5.1.0 directory.}"

source /opt/ros/humble/setup.bash

# Do not let an active Conda environment or host preload replace Isaac Sim's
# bundled Python/DDS libraries. UDP avoids a known Fast DDS shared-memory crash
# when Isaac Sim and ROS 2 nodes coexist on this host.
unset LD_PRELOAD CONDA_PREFIX CONDA_DEFAULT_ENV CONDA_PROMPT_MODIFIER
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export FASTDDS_BUILTIN_TRANSPORTS=UDPv4

exec "$isaac_root/python.sh" \
  "$project_root/src/isaac_moby_sim/scripts/run_moby_stage.py" "$@"
