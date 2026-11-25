"""Thin controller for the arm + gripper through the ros2_control JointTrajectory controllers."""
from __future__ import annotations

import time

from builtin_interfaces.msg import Duration
from rclpy.node import Node
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint

from .arm_kinematics import GRIPPER_CLOSED, GRIPPER_OPEN, HOME, topdown_ik

ARM_JOINTS = [f"arm_joint_{i}" for i in range(1, 7)]
GRIP_JOINTS = ["left_finger_joint", "right_finger_joint"]


def _traj_multi(names, waypoints, secs_total):
    """Joint trajectory through several waypoints, evenly spaced in time."""
    m = JointTrajectory()
    m.joint_names = names
    n = len(waypoints)
    for i, pos in enumerate(waypoints):
        p = JointTrajectoryPoint()
        p.positions = [float(v) for v in pos]
        t = secs_total * (i + 1) / n
        p.time_from_start = Duration(sec=int(t), nanosec=int((t % 1) * 1e9))
        m.points.append(p)
    return m


def _traj(names, pos, secs):
    m = JointTrajectory()
    m.joint_names = names
    p = JointTrajectoryPoint()
    p.positions = [float(v) for v in pos]
    p.time_from_start = Duration(sec=int(secs), nanosec=int((secs % 1) * 1e9))
    m.points = [p]
    return m


class ArmControl:
    def __init__(self, node: Node):
        self.node = node
        self.arm = node.create_publisher(JointTrajectory, "/arm_controller/joint_trajectory", 10)
        self.grip = node.create_publisher(JointTrajectory, "/gripper_controller/joint_trajectory", 10)

    def _wait(self, secs: float) -> None:
        time.sleep(secs + 0.3)  # sim runs ~real time; settle margin

    def move(self, q, secs: float = 2.5) -> None:
        self.arm.publish(_traj(ARM_JOINTS, q, secs))
        self._wait(secs)

    def line(self, p0, p1, secs: float = 3.0, steps: int = 8) -> None:
        """Straight Cartesian line (robot frame) between two grasp-frame positions, tool kept vertical."""
        pts = [topdown_ik(*[a + (b - a) * (i / steps) for a, b in zip(p0, p1)]) for i in range(1, steps + 1)]
        self.arm.publish(_traj_multi(ARM_JOINTS, pts, secs))
        self._wait(secs)

    def gripper(self, opening: float, secs: float = 1.2) -> None:
        self.grip.publish(_traj(GRIP_JOINTS, [opening, opening], secs))
        self._wait(secs)

    def open(self) -> None:
        self.gripper(GRIPPER_OPEN)

    def close(self) -> None:
        self.gripper(GRIPPER_CLOSED, 2.0)

    def home(self) -> None:
        self.move(HOME, 3.0)

    # --- top-down pick/place in the ROBOT frame (x forward, y left, z up from floor)
    # approach high (clears every object while the wrist swings from the stowed pose), then descend vertically.
    APPROACH = 0.28

    def pick(self, x: float, y: float, z_grasp: float) -> None:
        self.open()
        self.move(topdown_ik(x, y, z_grasp + self.APPROACH), 3.5)
        self.line((x, y, z_grasp + self.APPROACH), (x, y, z_grasp), 3.0)
        self.close()
        self.line((x, y, z_grasp), (x, y, z_grasp + self.APPROACH), 3.0)
        self.move(HOME, 3.5)

    def place(self, x: float, y: float, z_release: float) -> None:
        self.move(topdown_ik(x, y, z_release + self.APPROACH), 3.5)
        self.line((x, y, z_release + self.APPROACH), (x, y, z_release), 3.0)
        self.open()
        self.line((x, y, z_release), (x, y, z_release + self.APPROACH), 3.0)
        self.move(HOME, 3.5)


def world_to_robot(buf, x: float, y: float):
    """Map-frame (x, y) -> base_footprint frame using the live TF (robot pose has Nav2-tolerance error)."""
    import math

    from rclpy.time import Time
    t = buf.lookup_transform("map", "base_footprint", Time()).transform
    q = t.rotation
    yaw = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
    dx, dy = x - t.translation.x, y - t.translation.y
    return (math.cos(yaw) * dx + math.sin(yaw) * dy, -math.sin(yaw) * dx + math.cos(yaw) * dy)
