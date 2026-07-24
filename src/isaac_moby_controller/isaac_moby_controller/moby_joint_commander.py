import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from sensor_msgs.msg import JointState
import math


class MobyJointCommander(Node):
    def __init__(self):
        super().__init__('moby_joint_commander')

        self.WHEEL_RADIUS = 0.099

        self.wheel_positions = {
            'fl': (0.393, 0.2054),
            'fr': (0.393, -0.2054),
            'rl': (-0.393, 0.2054),
            'rr': (-0.393, -0.2054)
        }

        self.module_joints = {
            'fl': ('fl_rot_joint', 'fl_tract_joint'),
            'fr': ('fr_rot_joint', 'fr_tract_joint'),
            'rl': ('rl_rot_joint', 'rl_tract_joint'),
            'rr': ('rr_rot_joint', 'rr_tract_joint')
        }

        self.arm_initial_positions = {
            'joint0': 0.0,
            'joint1': 0.5,
            'joint2': -2.0,
            'joint3': 0.0,
            'joint4': -1.7,
            'joint5': 0.0
        }

        self.arm_joint_names = list(self.arm_initial_positions.keys())

        self.sub_cmd_vel = self.create_subscription(
            Twist, '/cmd_vel', self.cmd_vel_callback, 10)

        self.sub_joint_states = self.create_subscription(
            JointState, '/joint_states', self.joint_state_callback, 10)

        self.pub_joint_cmd = self.create_publisher(
            JointState, '/joint_command', 10)

        self.current_steer_angles = {
            'fl': 0.0, 'fr': 0.0, 'rl': 0.0, 'rr': 0.0
        }

        self.get_logger().info("Moby Joint Commander (Corrected) Started.")

    def joint_state_callback(self, msg):
        for key, (rot_name, _) in self.module_joints.items():
            if rot_name in msg.name:
                idx = msg.name.index(rot_name)
                self.current_steer_angles[key] = msg.position[idx]

    def cmd_vel_callback(self, msg):
        vx = msg.linear.x
        vy = msg.linear.y
        wz = msg.angular.z

        cmd_msg = JointState()
        cmd_msg.header.stamp = self.get_clock().now().to_msg()

        for key in ['fl', 'fr', 'rl', 'rr']:
            px, py = self.wheel_positions[key]

            wheel_vx = vx - wz * py
            wheel_vy = vy + wz * px

            target_linear_vel = math.sqrt(wheel_vx**2 + wheel_vy**2)
            target_ang = math.atan2(wheel_vy, wheel_vx)

            if abs(target_linear_vel) < 0.001:
                target_linear_vel = 0.0
                target_ang = self.current_steer_angles[key]

            opt_ang, opt_linear_vel = self.optimize_steering(
                self.current_steer_angles[key],
                target_ang,
                target_linear_vel
            )

            wheel_angular_vel = opt_linear_vel / self.WHEEL_RADIUS

            rot_joint, tract_joint = self.module_joints[key]

            cmd_msg.name.append(rot_joint)
            cmd_msg.position.append(opt_ang)
            cmd_msg.velocity.append(0.0)
            cmd_msg.effort.append(0.0)

            cmd_msg.name.append(tract_joint)
            cmd_msg.position.append(0.0)
            cmd_msg.velocity.append(wheel_angular_vel)
            cmd_msg.effort.append(0.0)

        for name in self.arm_joint_names:
            cmd_msg.name.append(name)
            cmd_msg.position.append(self.arm_initial_positions[name])
            cmd_msg.velocity.append(0.0)
            cmd_msg.effort.append(0.0)

        self.pub_joint_cmd.publish(cmd_msg)

    def optimize_steering(self, current_ang, target_ang, target_vel):
        diff = target_ang - current_ang
        while diff > math.pi:
            diff -= 2 * math.pi
        while diff < -math.pi:
            diff += 2 * math.pi

        if abs(diff) > math.pi / 2:
            if diff > 0:
                diff -= math.pi
            else:
                diff += math.pi
            target_vel = -target_vel

        final_ang = current_ang + diff
        return final_ang, target_vel


def main(args=None):
    rclpy.init(args=args)
    node = MobyJointCommander()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
