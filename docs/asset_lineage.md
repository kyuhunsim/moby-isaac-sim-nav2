# Asset lineage

## Current simulation stage

The first golden stage is:

```text
src/isaac_moby_sim/assets/scenes/moby_simple_room_final.usd
```

It was copied from:

```text
$ISAAC_SIM_ROOT/usd/moby_simple_room_final.usd
```

The older `moby_simple_room.usd` and `moby_planning_test_보관.usd` files are not part of
the initial runtime path.

## Robot description

`urdf/moby.urdf` contains the Moby mobile base and the six-axis Indy arm (`joint0` through
`joint5`), together with the Moby wheel and sensor frames. The Isaac Sim USD is the
runtime asset; the URDF is the ROS description source. Its mesh paths use
`isaac_moby_description/model/meshes`.

The RP2 USD is kept separately because it may be referenced by authored USD stages:

```text
src/isaac_moby_sim/assets/arm/indy_rp2_v2.usd
```

Before publishing the repository, inspect all USD references and collect any external
mesh or Omniverse asset dependencies that are needed for an offline launch.
