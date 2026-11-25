"""Perfect localisation for simulation: publishes map->odom from Gazebo's true robot pose.

Wheel odometry drifts under slip; a real robot would correct it against the map (AMCL / SLAM).
In simulation the standard shortcut is  T_map_odom = T_world_base * inverse(T_odom_base).
The Gazebo world frame IS the map frame (scenario coordinates).
"""
import numpy as np
import rclpy
from geometry_msgs.msg import PoseStamped, TransformStamped
from rclpy.node import Node
from rclpy.time import Time
from tf2_ros import Buffer, TransformBroadcaster, TransformListener


def _mat(t, q):
    x, y, z, w = q
    R = np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    M = np.eye(4)
    M[:3, :3], M[:3, 3] = R, t
    return M


def _quat(R):
    t = np.trace(R)
    if t > 0:
        s = np.sqrt(t + 1) * 2
        return ((R[2, 1] - R[1, 2]) / s, (R[0, 2] - R[2, 0]) / s, (R[1, 0] - R[0, 1]) / s, 0.25 * s)
    i = int(np.argmax(np.diag(R)))
    j, k = (i + 1) % 3, (i + 2) % 3
    s = np.sqrt(R[i, i] - R[j, j] - R[k, k] + 1) * 2
    q = [0.0] * 4
    q[i], q[3] = 0.25 * s, (R[k, j] - R[j, k]) / s
    q[j], q[k] = (R[j, i] + R[i, j]) / s, (R[k, i] + R[i, k]) / s
    return tuple(q)


class Localizer(Node):
    def __init__(self):
        super().__init__("ground_truth_localizer")
        self.buf = Buffer()
        TransformListener(self.buf, self)
        self.br = TransformBroadcaster(self)
        self.pose = None
        self.create_subscription(PoseStamped, "/robot_pose", lambda m: setattr(self, "pose", m), 10)
        self.create_timer(1 / 30.0, self.tick)

    def tick(self):
        if self.pose is None:
            return
        try:
            tf = self.buf.lookup_transform("odom", "base_footprint", Time())
        except Exception:  # noqa: BLE001 - TF not ready yet
            return
        p, o = self.pose.pose.position, self.pose.pose.orientation
        T_wb = _mat([p.x, p.y, p.z], [o.x, o.y, o.z, o.w])
        t, r = tf.transform.translation, tf.transform.rotation
        T_ob = _mat([t.x, t.y, t.z], [r.x, r.y, r.z, r.w])
        T = T_wb @ np.linalg.inv(T_ob)
        q = _quat(T[:3, :3])
        msg = TransformStamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id, msg.child_frame_id = "map", "odom"
        msg.transform.translation.x, msg.transform.translation.y, msg.transform.translation.z = map(float, T[:3, 3])
        msg.transform.rotation.x, msg.transform.rotation.y, msg.transform.rotation.z, msg.transform.rotation.w = map(float, q)
        self.br.sendTransform(msg)


def main(args=None):
    rclpy.init(args=args)
    rclpy.spin(Localizer())


if __name__ == "__main__":
    main()
