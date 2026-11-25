"""Nav2 (map server, planner, controller, behaviors, BT Navigator) on the generated warehouse map.
Run after gazebo.launch.py. map->odom is a static identity-offset TF at the robot spawn pose."""
from pathlib import Path

import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import OpaqueFunction
from launch_ros.actions import LifecycleNode, Node


def _setup(context):
    share = Path(get_package_share_directory("vatp_sim"))
    out = Path.home() / ".ros" / "vatp"
    sc = yaml.safe_load((out / "scenario.yaml").read_text())
    sx, sy = sc["world"]["zones"]["dock"]["access"]
    params = str(share / "config" / "nav2_params.yaml")
    common = dict(output="screen", parameters=[params, {"use_sim_time": True}])
    nodes = [
        Node(package="vatp_sim", executable="ground_truth_localizer", name="ground_truth_localizer",
             output="screen", parameters=[{"use_sim_time": True}]),
        Node(package="nav2_map_server", executable="map_server", name="map_server", output="screen",
             parameters=[params, {"use_sim_time": True, "yaml_filename": str(out / "maps" / "warehouse.yaml")}]),
        Node(package="nav2_planner", executable="planner_server", name="planner_server", **common),
        Node(package="nav2_controller", executable="controller_server", name="controller_server",
             remappings=[("cmd_vel", "/cmd_vel")], **common),
        Node(package="nav2_behaviors", executable="behavior_server", name="behavior_server",
             remappings=[("cmd_vel", "/cmd_vel")], **common),
        Node(package="nav2_bt_navigator", executable="bt_navigator", name="bt_navigator", **common),
        Node(package="nav2_lifecycle_manager", executable="lifecycle_manager", name="lifecycle_manager_nav",
             output="screen", parameters=[{"use_sim_time": True, "autostart": True, "bond_timeout": 0.0,
                                           "node_names": ["map_server", "planner_server", "controller_server",
                                                          "behavior_server", "bt_navigator"]}]),
    ]
    return nodes


def generate_launch_description():
    return LaunchDescription([OpaqueFunction(function=_setup)])
