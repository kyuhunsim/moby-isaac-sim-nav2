#!/usr/bin/env python3
"""Open the authored Moby simple-room USD and run it."""

import argparse
import json
import math
import os
import sys
import tempfile
import traceback
from pathlib import Path


ISAAC_ROOT = Path(
    os.environ.get("ISAAC_SIM_ROOT", "/home/rise/isaac-sim_5.1.0")
).expanduser()
SOURCE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = (
    SOURCE_ROOT
    if (SOURCE_ROOT / "assets").is_dir()
    else Path(__file__).resolve().parents[2] / "share" / "isaac_moby_sim"
)
DEFAULT_COMMAND_FILE = PROJECT_ROOT / "config" / "people_commands.txt"
DEFAULT_SCENARIO_FILE = PROJECT_ROOT / "config" / "people_scenarios.json"
DEFAULT_EXPERIENCE = ISAAC_ROOT / "apps" / "isaacsim.exp.full.kit"
HEADLESS_EXPERIENCE = ISAAC_ROOT / "apps" / "isaacsim.exp.base.python.kit"
BRIDGE_LIB_DIR = ISAAC_ROOT / "exts" / "isaacsim.ros2.bridge" / "humble" / "lib"
BUNDLED_RCLPY_DIR = ISAAC_ROOT / "exts" / "isaacsim.ros2.bridge" / "humble" / "rclpy"
PEOPLE_LOOP_SETTING = "/exts/omni.anim.people/command_settings/number_of_loop"
PEOPLE_COMMAND_SETTING = "/exts/omni.anim.people/command_settings/command_file_path"


def configure_ros_environment():
    os.environ.setdefault("ROS_DISTRO", "humble")
    os.environ.setdefault("ROS_VERSION", "2")
    os.environ.setdefault("ROS_PYTHON_VERSION", "3")
    os.environ.setdefault("RMW_IMPLEMENTATION", "rmw_fastrtps_cpp")

    if BUNDLED_RCLPY_DIR.is_dir():
        python_entries = [item for item in os.environ.get("PYTHONPATH", "").split(":") if item]
        bundled_rclpy = str(BUNDLED_RCLPY_DIR)
        if bundled_rclpy not in python_entries:
            os.environ["PYTHONPATH"] = ":".join([bundled_rclpy, *python_entries])
        if bundled_rclpy not in sys.path:
            sys.path.insert(0, bundled_rclpy)

    if not BRIDGE_LIB_DIR.is_dir():
        return

    bridge = str(BRIDGE_LIB_DIR)
    entries = [item for item in os.environ.get("LD_LIBRARY_PATH", "").split(":") if item]
    if bridge not in entries:
        os.environ["LD_LIBRARY_PATH"] = ":".join([bridge, *entries])


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-usd",
        default=str(
            PROJECT_ROOT / "assets" / "scenes" / "moby_simple_room_final.usd"
        ),
        help="The already-authored USD to open.",
    )
    parser.add_argument("--headless", action="store_true")
    parser.add_argument(
        "--no-ros-bridge",
        action="store_true",
        help="Do not load the Isaac ROS2 bridge (USD/People-only diagnostic).",
    )
    parser.add_argument(
        "--no-people-collision",
        action="store_true",
        help="Do not add the runtime capsule collision proxy to the person.",
    )
    parser.add_argument(
        "--people-loops",
        default=None,
        help="Isaac People loop count. 'inf' keeps the Actor command sequence running.",
    )
    parser.add_argument(
        "--people-speed-scale",
        type=float,
        default=None,
        help=(
            "Scale the People GoTo Walk animation in (0, 1]. "
            "Measure character motion to convert this value to m/s."
        ),
    )
    parser.add_argument(
        "--people-speed-mps",
        type=float,
        default=None,
        help="Exact route speed used by --people-motion-mode kinematic.",
    )
    parser.add_argument(
        "--people-motion-mode",
        choices=("people", "kinematic"),
        default=None,
        help=(
            "'people' uses the Isaac People extension. 'kinematic' moves the "
            "character deterministically along the waypoints in m/s."
        ),
    )
    parser.add_argument(
        "--people-start-delay",
        type=float,
        default=None,
        help="Simulation seconds to wait before deterministic person motion starts.",
    )
    parser.add_argument(
        "--command-file",
        default=None,
        help=(
            "Isaac People command file. Pass an empty string to keep "
            "the stage/UI command setting."
        ),
    )
    parser.add_argument(
        "--scenario-file",
        default=str(DEFAULT_SCENARIO_FILE),
        help="JSON file containing named people routes and speed scales.",
    )
    parser.add_argument(
        "--scenario",
        help="Named scenario from --scenario-file. CLI values override the scenario.",
    )
    parser.add_argument(
        "--list-scenarios",
        action="store_true",
        help="List named scenarios and exit before Isaac Sim is started.",
    )
    parser.add_argument(
        "--people-waypoint",
        action="append",
        default=[],
        metavar="X,Y,Z",
        help=(
            "People GoTo waypoint. Repeat the option to create a route. "
            "This overrides --command-file and scenario waypoints."
        ),
    )
    parser.add_argument(
        "--people-start-at-first-waypoint",
        action="store_true",
        help="Place the People character at the first waypoint before playback.",
    )
    parser.add_argument(
        "--people-character",
        default="Character",
        help="Character name used in generated Isaac People commands.",
    )
    parser.add_argument(
        "--character-prim",
        default="/World/Characters/Character",
        help="USD prim whose ground-truth pose and velocity are published.",
    )
    parser.add_argument(
        "--person-frame-id",
        default="map",
        help="ROS frame assigned to the character world pose.",
    )
    parser.add_argument(
        "--person-publish-rate",
        type=float,
        default=20.0,
        help="Ground-truth person pose/twist publication rate in Hz. 0 disables it.",
    )
    parser.add_argument(
        "--frames",
        type=int,
        default=0,
        help="Run a finite number of frames, then exit. 0 keeps the app alive.",
    )
    parser.add_argument(
        "--no-play",
        action="store_true",
        help="Open and load the stage without starting the timeline.",
    )
    return parser.parse_args()


def parse_waypoint(text):
    """Parse a CLI waypoint formatted as X,Y,Z."""
    values = [item.strip() for item in text.split(",")]
    if len(values) != 3:
        raise ValueError(f"waypoint must be X,Y,Z, got: {text}")
    return tuple(float(value) for value in values)


def load_scenarios(path):
    """Load and validate the named scenario dictionary."""
    scenario_path = Path(path).expanduser().resolve()
    if not scenario_path.is_file():
        raise RuntimeError(f"Scenario file not found: {scenario_path}")
    payload = json.loads(scenario_path.read_text(encoding="utf-8"))
    scenarios = payload.get("scenarios", {})
    if not isinstance(scenarios, dict):
        raise RuntimeError("scenario file must contain an object named 'scenarios'")
    return scenarios


def resolve_people_configuration(args):
    """Resolve route, speed and loop values from defaults, scenario and CLI."""
    people_requested = any(
        (
            args.list_scenarios,
            args.scenario,
            bool(args.people_waypoint),
            args.command_file is not None,
            args.people_speed_scale is not None,
            args.people_speed_mps is not None,
            args.people_motion_mode is not None,
            args.people_start_delay is not None,
            args.people_loops is not None,
            args.people_start_at_first_waypoint,
        )
    )
    if not people_requested:
        return None

    scenarios = load_scenarios(args.scenario_file)
    if args.list_scenarios:
        for name, scenario in scenarios.items():
            description = scenario.get("description", "")
            print(f"{name}: {description}")
        return None

    scenario = {}
    if args.scenario:
        if args.scenario not in scenarios:
            choices = ", ".join(sorted(scenarios)) or "<none>"
            raise RuntimeError(
                f"Unknown scenario '{args.scenario}'. Available: {choices}")
        scenario = scenarios[args.scenario]

    waypoints = scenario.get("waypoints", [])
    if args.people_waypoint:
        waypoints = [parse_waypoint(value) for value in args.people_waypoint]
        command_file = ""
    elif args.command_file is not None:
        waypoints = []
        command_file = args.command_file
    else:
        waypoints = [tuple(float(value) for value in point) for point in waypoints]
        command_file = "" if waypoints else str(DEFAULT_COMMAND_FILE)
    for waypoint in waypoints:
        if len(waypoint) != 3:
            raise RuntimeError(f"Each scenario waypoint must have 3 values: {waypoint}")

    speed_scale = args.people_speed_scale
    if speed_scale is None:
        speed_scale = float(scenario.get("speed_scale", 1.0))
    speed_mps = args.people_speed_mps
    if speed_mps is None:
        speed_mps = float(scenario.get("speed_mps", 0.8))
    motion_mode = args.people_motion_mode
    if motion_mode is None:
        motion_mode = str(scenario.get("motion_mode", "people"))
    if motion_mode not in ("people", "kinematic"):
        raise RuntimeError(
            f"motion_mode must be 'people' or 'kinematic', got: {motion_mode}")
    if speed_mps <= 0.0:
        raise RuntimeError("people speed_mps must be positive")
    if motion_mode == "kinematic" and not waypoints:
        raise RuntimeError("kinematic people motion requires at least one waypoint")
    start_delay_s = args.people_start_delay
    if start_delay_s is None:
        start_delay_s = float(scenario.get("start_delay_s", 0.0))
    if start_delay_s < 0.0:
        raise RuntimeError("people start_delay_s must be non-negative")
    loops = args.people_loops
    if loops is None:
        loops = str(scenario.get("loops", "inf"))

    return {
        "name": args.scenario or "custom",
        "description": scenario.get("description", ""),
        "speed_scale": speed_scale,
        "speed_mps": speed_mps,
        "motion_mode": motion_mode,
        "start_delay_s": start_delay_s,
        "loops": loops,
        "waypoints": waypoints,
        "command_file": command_file,
    }


def write_people_command_file(character, waypoints):
    """Write a temporary Isaac People command file for a waypoint route."""
    handle = tempfile.NamedTemporaryFile(
        mode="w", prefix="moby_people_", suffix=".txt", delete=False,
        encoding="utf-8")
    try:
        for x, y, z in waypoints:
            handle.write(f"{character} GoTo {x:.6f} {y:.6f} {z:.6f} _\n")
    finally:
        handle.close()
    return Path(handle.name)


def ensure_people_navmesh(app, character_prim_path, waypoints, max_frames=300):
    """Wait for, or bake, the NavMesh required by People GoTo validation."""
    if not waypoints:
        return None
    try:
        import carb
        import omni.anim.navigation.core as navigation
        from isaacsim.core.prims import SingleXFormPrim
    except (ImportError, RuntimeError) as exc:
        print(f"People NavMesh check skipped: {exc}", flush=True)
        return None

    nav_interface = navigation.acquire_interface()
    navmesh = nav_interface.get_navmesh()
    prim = SingleXFormPrim(
        character_prim_path,
        name="people_navmesh_probe",
        reset_xform_properties=False,
    )
    start, _ = prim.get_world_pose()
    start_point = carb.Float3(*[float(value) for value in start])
    target_points = [carb.Float3(*[float(value) for value in point]) for point in waypoints]

    def get_accessible_targets(mesh):
        if mesh is None:
            return None
        try:
            accessible_targets = []
            for target in target_points:
                closest, _ = mesh.query_closest_point(target, agent_radius=0.5)
                if closest is None:
                    return None
                path = mesh.query_shortest_path(
                    start_point, closest, agent_radius=0.5)
                if path is None or not path.get_points():
                    return None
                accessible_targets.append(
                    (float(closest[0]), float(closest[1]), float(closest[2])))
            return accessible_targets
        except (RuntimeError, TypeError, ValueError):
            return None

    accessible_targets = get_accessible_targets(navmesh)
    if accessible_targets is None:
        print("People NavMesh is not ready; starting NavMesh bake", flush=True)
        try:
            nav_interface.start_navmesh_baking()
        except (RuntimeError, TypeError):
            pass
        for _ in range(max_frames):
            app.update()
            navmesh = nav_interface.get_navmesh()
            accessible_targets = get_accessible_targets(navmesh)
            if accessible_targets is not None:
                break

    if accessible_targets is not None:
        print(
            f"People NavMesh path check: ready; targets={accessible_targets}",
            flush=True,
        )
        return accessible_targets
    else:
        print(
            "People NavMesh path check: failed; GoTo commands may be invalid",
            flush=True,
        )
        return None


def ensure_character_collision(stage, character_prim_path):
    """Add a runtime PhysX capsule so the person cannot geometrically overlap Moby."""
    try:
        from pxr import Gf, Sdf, UsdGeom, UsdPhysics
    except ImportError as exc:
        print(f"People collision proxy skipped: {exc}", flush=True)
        return

    parent = stage.GetPrimAtPath(character_prim_path)
    if not parent.IsValid():
        print(
            f"People collision proxy skipped: prim not found {character_prim_path}",
            flush=True,
        )
        return

    collision_path = Sdf.Path(
        f"{character_prim_path.rstrip('/')}/PeopleCollisionProxy")
    capsule = UsdGeom.Capsule.Define(stage, collision_path)
    capsule.CreateRadiusAttr(0.35)
    capsule.CreateHeightAttr(1.35)
    # Capsule.Define() can return an already-authored proxy (or a prim that
    # inherited xformOp:translate from the USD).  Adding a second translate
    # op then raises a Tf.ErrorException.  Reuse the existing op when present.
    xformable = UsdGeom.Xformable(capsule.GetPrim())
    translate_op = next(
        (
            op for op in xformable.GetOrderedXformOps()
            if op.GetOpType() == UsdGeom.XformOp.TypeTranslate
        ),
        None,
    )
    if translate_op is None:
        translate_op = xformable.AddTranslateOp()
    translate_op.Set(Gf.Vec3d(0.0, 0.0, 0.82))
    UsdPhysics.CollisionAPI.Apply(capsule.GetPrim())
    # Keep the proxy invisible in the camera while retaining PhysX collision.
    UsdGeom.Imageable(capsule.GetPrim()).MakeInvisible()
    print(
        f"People collision proxy enabled: {collision_path} "
        "(radius=0.35 m, height=1.35 m)",
        flush=True,
    )


def ensure_people_character(stage, requested_prim_path):
    """Require an authored Isaac People character, never a geometric proxy."""
    if stage.GetPrimAtPath(requested_prim_path).IsValid():
        return requested_prim_path
    raise RuntimeError(
        f"Isaac People character not found: {requested_prim_path}. "
        "The supplied simple-room USD includes "
        "/World/Characters/Character; custom USDs must include an authored "
        "Isaac People character too."
    )


def set_people_start_pose(prim_path, waypoint):
    """Place the character at a route endpoint before People records its origin."""
    try:
        import numpy as np
        from isaacsim.core.prims import SingleXFormPrim

        prim = SingleXFormPrim(
            prim_path, name="people_start_pose", reset_xform_properties=False)
        prim.set_world_pose(position=np.asarray(waypoint, dtype=float))
        print(f"People start pose: {tuple(waypoint)}", flush=True)
    except (ImportError, RuntimeError, TypeError, ValueError) as exc:
        print(f"People start pose could not be set: {exc}", flush=True)


class PersonStatePublisher:
    """Publish an Isaac People prim's world pose, velocity and commanded route."""

    def __init__(self, stage, timeline, prim_path, frame_id, rate_hz, waypoints):
        import rclpy
        from builtin_interfaces.msg import Time
        from geometry_msgs.msg import PoseStamped, TwistStamped
        from nav_msgs.msg import Path as PathMessage
        from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
        from pxr import Usd, UsdGeom

        if not rclpy.ok():
            rclpy.init(args=None)
        self.rclpy = rclpy
        self.Time = Time
        self.PoseStamped = PoseStamped
        self.TwistStamped = TwistStamped
        self.PathMessage = PathMessage
        self.Usd = Usd
        self.UsdGeom = UsdGeom
        self.timeline = timeline
        self.frame_id = frame_id
        self.period = 1.0 / max(0.1, rate_hz)
        self.previous_time = None
        self.previous_position = None
        self.previous_yaw = None
        self.last_publish_time = None

        self.prim = stage.GetPrimAtPath(prim_path)
        if not self.prim.IsValid():
            raise RuntimeError(f"Character prim not found: {prim_path}")
        self.xformable = self.UsdGeom.Xformable(self.prim)
        self.node = rclpy.create_node("isaac_people_ground_truth")
        self.pose_publisher = self.node.create_publisher(
            PoseStamped, "/people/character/pose", 10)
        self.twist_publisher = self.node.create_publisher(
            TwistStamped, "/people/character/twist", 10)
        route_qos = QoSProfile(
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        self.route_publisher = self.node.create_publisher(
            PathMessage, "/people/character/route", route_qos)
        initial_matrix = self.xformable.ComputeLocalToWorldTransform(
            self.Usd.TimeCode.Default())
        initial_position = tuple(
            float(value) for value in initial_matrix.ExtractTranslation())
        self.publish_route([initial_position, *waypoints])

    @staticmethod
    def yaw_from_quaternion(w, x, y, z):
        return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))

    def publish_route(self, waypoints):
        route = self.PathMessage()
        route.header.frame_id = self.frame_id
        route.header.stamp = self.stamp_from_simulation_time(
            float(self.timeline.get_current_time()))
        for x, y, z in waypoints:
            pose = self.PoseStamped()
            pose.header = route.header
            pose.pose.position.x = float(x)
            pose.pose.position.y = float(y)
            pose.pose.position.z = float(z)
            pose.pose.orientation.w = 1.0
            route.poses.append(pose)
        self.route_publisher.publish(route)

    def stamp_from_simulation_time(self, simulation_time):
        stamp = self.Time()
        bounded = max(0.0, simulation_time)
        stamp.sec = int(bounded)
        stamp.nanosec = int((bounded - stamp.sec) * 1e9)
        return stamp

    def update(self):
        simulation_time = float(self.timeline.get_current_time())
        if (
            self.last_publish_time is not None
            and simulation_time >= self.last_publish_time
            and simulation_time - self.last_publish_time < self.period
        ):
            self.rclpy.spin_once(self.node, timeout_sec=0.0)
            return

        matrix = self.xformable.ComputeLocalToWorldTransform(
            self.Usd.TimeCode.Default())
        translation = matrix.ExtractTranslation()
        quaternion = matrix.ExtractRotationQuat()
        imaginary = quaternion.GetImaginary()
        qw = float(quaternion.GetReal())
        qx, qy, qz = (float(value) for value in imaginary)
        yaw = self.yaw_from_quaternion(qw, qx, qy, qz)
        stamp = self.stamp_from_simulation_time(simulation_time)

        pose = self.PoseStamped()
        pose.header.frame_id = self.frame_id
        pose.header.stamp = stamp
        pose.pose.position.x = float(translation[0])
        pose.pose.position.y = float(translation[1])
        pose.pose.position.z = float(translation[2])
        pose.pose.orientation.w = qw
        pose.pose.orientation.x = qx
        pose.pose.orientation.y = qy
        pose.pose.orientation.z = qz
        self.pose_publisher.publish(pose)

        twist = self.TwistStamped()
        twist.header = pose.header
        if (
            self.previous_time is not None
            and simulation_time > self.previous_time
            and self.previous_position is not None
        ):
            dt = simulation_time - self.previous_time
            twist.twist.linear.x = (
                float(translation[0]) - self.previous_position[0]) / dt
            twist.twist.linear.y = (
                float(translation[1]) - self.previous_position[1]) / dt
            twist.twist.linear.z = (
                float(translation[2]) - self.previous_position[2]) / dt
            yaw_delta = math.atan2(
                math.sin(yaw - self.previous_yaw),
                math.cos(yaw - self.previous_yaw),
            )
            twist.twist.angular.z = yaw_delta / dt
        self.twist_publisher.publish(twist)

        self.previous_time = simulation_time
        self.previous_position = tuple(float(value) for value in translation)
        self.previous_yaw = yaw
        self.last_publish_time = simulation_time
        self.rclpy.spin_once(self.node, timeout_sec=0.0)

    def close(self):
        self.node.destroy_node()
        if self.rclpy.ok():
            self.rclpy.shutdown()


class KinematicPersonController:
    """Move a character deterministically through waypoints with ping-pong loops."""

    def __init__(self, prim_path, timeline, waypoints, speed_mps, start_delay_s):
        import numpy as np
        from isaacsim.core.prims import SingleXFormPrim

        self.np = np
        self.timeline = timeline
        self.prim_path = prim_path
        self.speed_mps = float(speed_mps)
        self.start_delay_s = float(start_delay_s)
        self.prim = SingleXFormPrim(
            prim_path, name="kinematic_person", reset_xform_properties=False)
        start_position, _ = self.prim.get_world_pose()
        # ``--people-start-at-first-waypoint`` places the character at the
        # first route point before this controller is constructed.  Remove
        # that duplicated point so the kinematic controller does not spend a
        # frame (or appear to dwell at the endpoint) before reversing.
        raw_points = [
            np.asarray(start_position, dtype=float),
            *[np.asarray(point, dtype=float) for point in waypoints],
        ]
        self.points = [raw_points[0]]
        for point in raw_points[1:]:
            if float(self.np.linalg.norm(point - self.points[-1])) > 1e-4:
                self.points.append(point)
        if len(self.points) < 2:
            raise RuntimeError(
                "kinematic people motion requires two distinct route points"
            )
        self.position = self.points[0].copy()
        self.target_index = 1
        self.direction = 1
        self.previous_time = None
        self.start_time = None
        self.character = None
        self.animation_prim_path = prim_path
        self.animation_status = None

    def _set_animation(self, walking):
        """Drive the USD character's existing animation graph.

        Kinematic mode keeps the People extension loaded for the authored
        animation graph, but disables its command loop. Setting the same
        Action/Walk variables used by a People GoTo command keeps the visual
        person walking while this controller owns the transform and exact
        m/s.
        """
        if self.character is None:
            try:
                import omni.anim.graph.core as animation_graph

                self.character = animation_graph.get_character(
                    self.animation_prim_path)
            except (ImportError, RuntimeError, TypeError):
                self.character = None

            # The authored character asset can place the SkelRoot below the
            # user-facing Xform. Discover that graph prim automatically.
            if self.character is None:
                try:
                    import omni.usd

                    stage = omni.usd.get_context().get_stage()
                    for candidate in stage.Traverse():
                        schemas = candidate.GetAppliedSchemas()
                        if (
                            candidate.GetTypeName() != "SkelRoot"
                            and not any(
                                "AnimationGraphAPI" in schema
                                for schema in schemas
                            )
                        ):
                            continue
                        try:
                            found = animation_graph.get_character(
                                str(candidate.GetPath()))
                        except (RuntimeError, TypeError):
                            found = None
                        if found is not None:
                            self.character = found
                            self.animation_prim_path = str(candidate.GetPath())
                            break
                except (ImportError, RuntimeError):
                    pass
        if self.character is None:
            if self.animation_status != "unavailable":
                prim = getattr(self.prim, "prim", None)
                if prim is not None:
                    print(
                        "Character animation graph unavailable: "
                        f"{self.prim_path} "
                        f"type={prim.GetTypeName()} "
                        f"schemas={prim.GetAppliedSchemas()}",
                        flush=True,
                    )
                    print(
                        "Animation graph candidates: "
                        + ", ".join(
                            f"{child.GetPath()}[{child.GetTypeName()}]"
                            for child in prim.GetAllChildren()
                        ),
                        flush=True,
                    )
                else:
                    print(
                        f"Character animation graph unavailable: {self.prim_path}",
                        flush=True,
                    )
                self.animation_status = "unavailable"
            return
        if self.animation_status != "ready":
            print(
                f"Character animation graph connected: {self.prim_path}",
                flush=True,
            )
            self.animation_status = "ready"
        try:
            self.character.set_variable("Action", "Walk" if walking else "None")
            self.character.set_variable("Walk", 1.0 if walking else 0.0)
            if walking:
                # People GoTo also feeds PathPoints to the graph. Supplying
                # the same variable keeps the locomotion state active while
                # the kinematic controller owns the transform.
                import carb

                target = self.points[self.target_index]
                current = carb.Float3(*[float(value) for value in self.position])
                target_point = carb.Float3(*[float(value) for value in target])
                try:
                    self.character.set_variable("PathPoints", [current, target_point])
                except (RuntimeError, TypeError, ValueError):
                    # Some custom character graphs do not expose PathPoints;
                    # Action/Walk still provides the locomotion transition.
                    pass
        except RuntimeError:
            # The graph can be unavailable for the first frame after stage
            # load; retry on the next update.
            self.character = None

    def _advance_target(self):
        if self.direction > 0 and self.target_index >= len(self.points) - 1:
            self.direction = -1
        elif self.direction < 0 and self.target_index <= 0:
            self.direction = 1
        self.target_index += self.direction

    def update(self):
        now = float(self.timeline.get_current_time())
        if self.start_time is None or now < self.start_time:
            self.start_time = now
        if now - self.start_time < self.start_delay_s:
            self.previous_time = now
            self._set_animation(False)
            self.prim.set_world_pose(position=self.position)
            return
        if self.previous_time is None or now <= self.previous_time:
            self.previous_time = now
            self._set_animation(False)
            self.prim.set_world_pose(position=self.position)
            return
        remaining_motion = self.speed_mps * (now - self.previous_time)
        self.previous_time = now

        while remaining_motion > 0.0:
            target = self.points[self.target_index]
            delta = target - self.position
            distance = float(self.np.linalg.norm(delta))
            if distance <= 1e-6:
                self.position = target.copy()
                self._advance_target()
                continue
            step = min(distance, remaining_motion)
            self.position += delta * (step / distance)
            remaining_motion -= step
            if step >= distance - 1e-9:
                self._advance_target()
        self._set_animation(True)
        self.prim.set_world_pose(position=self.position)


def configure_people_walk_speed(scale):
    """Scale People GoTo root-motion input without editing the source USD."""
    if not 0.0 < scale <= 1.0:
        raise ValueError("--people-speed-scale must be in (0, 1]")
    if scale == 1.0:
        return

    from omni.anim.people.scripts.commands.base_command import Command

    original_walk = Command.walk

    def scaled_walk(command, dt):
        result = original_walk(command, dt)
        command.character.set_variable(
            "Walk", min(1.0, command.actual_walk_speed * scale))
        return result

    Command.walk = scaled_walk


def main():
    args = parse_args()
    if not args.no_ros_bridge:
        configure_ros_environment()
    people_config = resolve_people_configuration(args)
    if args.list_scenarios:
        return 0
    people_enabled = people_config is not None
    source = Path(args.source_usd).expanduser().resolve()
    if not source.exists():
        print(f"ERROR: stage not found: {source}", file=sys.stderr)
        print("Pass the USD path with --source-usd.", file=sys.stderr)
        return 2

    from isaacsim import SimulationApp

    # Full App is useful for interactive GUI playback, but it initializes
    # window/RTX extensions that can crash in headless environments before
    # the stage is opened. Use the smaller Python experience for headless
    # finite headless runs; it still loads the required extensions below.
    experience = HEADLESS_EXPERIENCE if args.headless else DEFAULT_EXPERIENCE
    app = SimulationApp(
        {
            "headless": args.headless,
            # Isaac-Sim Full enables the ROS bridge from its .kit file before
            # Python gets control. Disable that autoload, then load the bridge
            # explicitly before stage composition so saved OmniGraph ROS nodes
            # resolve without triggering the early rclpy crash.
            "extra_args": ["--/isaac/startup/ros_bridge_extension="],
        },
        experience=str(experience),
    )
    person_publisher = None
    temporary_command_file = None
    try:
        import omni.timeline
        import omni.usd
        import carb
        from isaacsim.core.utils.extensions import enable_extension

        # The authored USD's character behavior expects omni.anim.people to be
        # registered before the stage is composed.  This is also the order
        # The embedded Biped_Setup graph must observe the stage-open event to
        # create its CharacterManager binding, including headless kinematic
        # runs.
        preload_people = people_enabled
        if preload_people:
            enable_extension("omni.anim.people")
        if not args.no_ros_bridge:
            # Autoload is disabled in SimulationApp.extra_args, so register
            # the bridge before stage composition. The saved OmniGraph must
            # resolve its ROS2 node types while the USD is opened.
            enable_extension("isaacsim.ros2.bridge")
        else:
            print("ROS2 bridge: disabled (USD/People-only diagnostic)", flush=True)
        app.update()

        # Configure the authored People behavior before composing the USD.
        # Otherwise character_behavior.py can consume the stale UI command
        # during stage open and report `GoTo: invalid command`.
        settings = carb.settings.get_settings()
        if people_enabled and people_config["motion_mode"] == "people":
            configure_people_walk_speed(people_config["speed_scale"])
            settings.set(PEOPLE_LOOP_SETTING, str(people_config["loops"]))
            command_file_value = people_config["command_file"]
            if people_config["waypoints"]:
                temporary_command_file = write_people_command_file(
                    args.people_character, people_config["waypoints"])
                command_file_value = str(temporary_command_file)
            if command_file_value:
                command_file = Path(command_file_value).expanduser().resolve()
                if not command_file.is_file():
                    raise RuntimeError(f"Command file not found: {command_file}")
                settings.set(PEOPLE_COMMAND_SETTING, str(command_file))

        if not omni.usd.get_context().open_stage(str(source)):
            raise RuntimeError(f"Failed to open stage: {source}")
        for _ in range(120):
            app.update()

        stage = omni.usd.get_context().get_stage()
        if people_enabled:
            args.character_prim = ensure_people_character(stage, args.character_prim)
            # Let Kit resolve the embedded animation graph and asset references
            # before the motion controller addresses the character.
            app.update()

        if people_enabled and not preload_people:
            enable_extension("omni.anim.people")
            app.update()

        if people_enabled and not args.no_people_collision:
            ensure_character_collision(
                omni.usd.get_context().get_stage(), args.character_prim)

        if (
            people_enabled
            and
            args.people_start_at_first_waypoint
            and people_config["waypoints"]
        ):
            set_people_start_pose(
                args.character_prim, people_config["waypoints"][0])

        if people_enabled and people_config["motion_mode"] == "people":
            navmesh_targets = ensure_people_navmesh(
                app,
                args.character_prim,
                people_config["waypoints"],
            )
            if navmesh_targets is not None and temporary_command_file is not None:
                # People validates the raw command target against the baked
                # mesh with a strict 0.1 m tolerance. Use the exact closest
                # mesh points so a waypoint on a floor seam is accepted.
                temporary_command_file.unlink(missing_ok=True)
                temporary_command_file = write_people_command_file(
                    args.people_character, navmesh_targets)
                settings.set(
                    PEOPLE_COMMAND_SETTING, str(temporary_command_file))

        if people_enabled and people_config["motion_mode"] != "people":
            # Keep omni.anim.people loaded so it initializes the Character's
            # animation graph, but prevent the USD behavior script from
            # appending its implicit GoTo-to-origin loop. The kinematic
            # controller drives Action/Walk and the world transform directly.
            print(
                "People command loop: disabled; animation graph: enabled",
                flush=True,
            )
            settings.set(PEOPLE_LOOP_SETTING, "0")
            settings.set(PEOPLE_COMMAND_SETTING, "")

        timeline = omni.timeline.get_timeline_interface()
        person_controller = None
        if people_enabled and people_config["motion_mode"] == "kinematic":
            person_controller = KinematicPersonController(
                prim_path=args.character_prim,
                timeline=timeline,
                waypoints=people_config["waypoints"],
                speed_mps=people_config["speed_mps"],
                start_delay_s=people_config["start_delay_s"],
            )
        if not args.no_play:
            timeline.set_looping(True)
            timeline.play()

        if people_enabled and args.person_publish_rate > 0.0 and not args.no_ros_bridge:
            stage = omni.usd.get_context().get_stage()
            person_publisher = PersonStatePublisher(
                stage=stage,
                timeline=timeline,
                prim_path=args.character_prim,
                frame_id=args.person_frame_id,
                rate_hz=args.person_publish_rate,
                waypoints=people_config["waypoints"],
            )
        elif people_enabled and args.no_ros_bridge and args.person_publish_rate > 0.0:
            print(
                "Person ROS publisher: disabled because --no-ros-bridge is set",
                flush=True,
            )

        if args.frames > 0:
            for _ in range(args.frames):
                app.update()
                if person_controller is not None:
                    person_controller.update()
                if person_publisher is not None:
                    person_publisher.update()
            return 0

        print(f"Running Moby stage: {source}", flush=True)
        if people_enabled:
            print(f"People scenario: {people_config['name']}", flush=True)
            print(f"People motion mode: {people_config['motion_mode']}", flush=True)
            if people_config["motion_mode"] == "kinematic":
                print(f"People route speed: {people_config['speed_mps']} m/s", flush=True)
                print(
                    f"People start delay: {people_config['start_delay_s']} s",
                    flush=True,
                )
            else:
                print(f"People speed scale: {people_config['speed_scale']}", flush=True)
            print(f"People waypoints: {people_config['waypoints']}", flush=True)
        else:
            print("People motion: disabled", flush=True)
        print("ROS topics are provided by the saved Isaac OmniGraph stage.", flush=True)
        while app.is_running():
            app.update()
            if person_controller is not None:
                person_controller.update()
            if person_publisher is not None:
                person_publisher.update()
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception:
        # Keep runner failures visible even when Isaac Sim closes the Kit app
        # before Python flushes the normal traceback.
        traceback.print_exc()
        return 1
    finally:
        if person_publisher is not None:
            person_publisher.close()
        if temporary_command_file is not None:
            temporary_command_file.unlink(missing_ok=True)
        app.close()


if __name__ == "__main__":
    sys.exit(main())
