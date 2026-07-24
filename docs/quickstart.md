# Quickstart

The supported smoke path is intentionally three processes:

1. Isaac Sim opens the authored simple-room stage.
2. `moby_joint_commander` bridges `/cmd_vel` to `/joint_command`.
3. Nav2 starts with one map and one parameter file.

The people route is not part of the Nav2 launch. It belongs to the Isaac Sim stage runner
and is disabled unless explicitly requested.
