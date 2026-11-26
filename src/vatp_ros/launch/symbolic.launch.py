"""Planner + lifecycle skill server (symbolic backend) + lifecycle BT executor.

    ros2 launch vatp_ros symbolic.launch.py                      # offline mock planner
    ros2 launch vatp_ros symbolic.launch.py backend:=anthropic   # Claude (needs credits)
    ros2 launch vatp_ros symbolic.launch.py defect_rate:=0.5     # mock injects LLM-style defects
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    args = [
        DeclareLaunchArgument("backend", default_value="auto", description="auto|mock|anthropic"),
        DeclareLaunchArgument("defect_rate", default_value="0.0"),
        DeclareLaunchArgument("seed", default_value="0"),
        DeclareLaunchArgument("enforce_validator", default_value="true", description="false = ablation"),
        DeclareLaunchArgument("time_scale", default_value="0.02",
                              description="wall seconds per simulated second in the symbolic backend"),
        DeclareLaunchArgument("groot_port", default_value="1667"),
    ]
    return LaunchDescription([
        *args,
        Node(package="vatp_ros", executable="planner_node", name="vatp_planner", output="screen",
             parameters=[{"backend": LaunchConfiguration("backend"),
                          "defect_rate": LaunchConfiguration("defect_rate"),
                          "seed": LaunchConfiguration("seed"),
                          "enforce_validator": LaunchConfiguration("enforce_validator")}]),
        Node(package="vatp_ros", executable="skill_server", name="vatp_skill_server", output="screen",
             parameters=[{"time_scale": LaunchConfiguration("time_scale"), "autostart": True}]),
        Node(package="vatp_bt", executable="bt_executor", name="vatp_bt_executor", output="screen",
             parameters=[{"groot_port": LaunchConfiguration("groot_port"), "autostart": True}]),
    ])
