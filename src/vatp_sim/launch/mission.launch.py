"""Everything: Gazebo + Nav2 + planner + lifecycle skill server (Gazebo backend) + lifecycle BT executor.

    ros2 launch vatp_sim mission.launch.py backend:=mock gui:=false
    ros2 run vatp_ros benchmark --n 20 --timeout 900            # (second terminal)
Nodes start staggered because the simulator needs ~30 s before Nav2 and the skills can connect.
"""
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    sim = get_package_share_directory("vatp_sim") + "/launch/"
    inc = lambda f, **kw: IncludeLaunchDescription(  # noqa: E731
        PythonLaunchDescriptionSource(sim + f), launch_arguments={k: v for k, v in kw.items()}.items())
    return LaunchDescription([
        DeclareLaunchArgument("backend", default_value="auto"),
        DeclareLaunchArgument("scenario", default_value="0"),
        DeclareLaunchArgument("gui", default_value="false"),
        DeclareLaunchArgument("defect_rate", default_value="0.0"),
        inc("gazebo.launch.py", scenario=LaunchConfiguration("scenario"), gui=LaunchConfiguration("gui")),
        TimerAction(period=30.0, actions=[inc("nav.launch.py")]),
        TimerAction(period=34.0, actions=[
            Node(package="vatp_ros", executable="planner_node", name="vatp_planner", output="screen",
                 parameters=[{"backend": LaunchConfiguration("backend"),
                              "defect_rate": LaunchConfiguration("defect_rate")}]),
            Node(package="vatp_ros", executable="skill_server", name="vatp_skill_server", output="screen",
                 parameters=[{"backend": "gazebo", "autostart": True}]),
            Node(package="vatp_bt", executable="bt_executor", name="vatp_bt_executor", output="screen",
                 parameters=[{"autostart": True}]),
        ]),
    ])
