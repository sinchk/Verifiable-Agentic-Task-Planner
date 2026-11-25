"""Gazebo Harmonic warehouse + mobile manipulator + ros2_control (+ bridges).

    ros2 launch vatp_sim gazebo.launch.py scenario:=0 gui:=false
Generates the world SDF and the Nav2 map for the chosen scenario into ~/.ros/vatp/.
"""
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription, OpaqueFunction, RegisterEventHandler, TimerAction
from launch.conditions import IfCondition
from launch.event_handlers import OnProcessExit
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def _setup(context):
    from vatp_core.scenarios import make_scenario
    from vatp_sim.world_gen import WORLD_NAME, world_sdf, write_nav_map

    idx = int(LaunchConfiguration("scenario").perform(context))
    sc = make_scenario(idx, int(LaunchConfiguration("seed").perform(context)), jitter=False)
    out = Path.home() / ".ros" / "vatp"
    out.mkdir(parents=True, exist_ok=True)
    (out / "world.sdf").write_text(world_sdf(sc.world))
    (out / "scenario.yaml").write_text(sc.to_yaml())
    write_nav_map(sc.world, out / "maps")

    share = get_package_share_directory("vatp_sim")
    controllers = str(Path(share) / "config" / "controllers.yaml")
    robot_description = ParameterValue(
        Command(["xacro ", str(Path(share) / "urdf" / "vatp_amr.urdf.xacro"), " controllers_yaml:=", controllers]),
        value_type=str)
    headless = LaunchConfiguration("gui").perform(context) != "true"
    gz_args = f"-r {'-s --headless-rendering ' if headless else ''}{out / 'world.sdf'}"

    gz = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(PathJoinSubstitution([get_package_share_directory("ros_gz_sim"), "launch", "gz_sim.launch.py"])),
        launch_arguments={"gz_args": gz_args, "on_exit_shutdown": "true"}.items())
    rsp = Node(package="robot_state_publisher", executable="robot_state_publisher", output="screen",
               parameters=[{"robot_description": robot_description, "use_sim_time": True}])
    sp = sc.world.zones["dock"].access
    spawn = Node(package="ros_gz_sim", executable="create", output="screen",
                 arguments=["-topic", "robot_description", "-name", "vatp_amr", "-world", WORLD_NAME,
                            "-x", str(sp[0]), "-y", str(sp[1]), "-z", "0.02"])
    bridge = Node(package="ros_gz_bridge", executable="parameter_bridge", output="screen",
                  parameters=[{"config_file": str(Path(share) / "config" / "bridge.yaml"), "use_sim_time": True}])

    def spawner(name):
        return Node(package="controller_manager", executable="spawner", output="screen",
                    arguments=[name, "--controller-manager", "/controller_manager", "--controller-manager-timeout", "60"])

    chain = [spawner("joint_state_broadcaster"), spawner("arm_controller"), spawner("gripper_controller")]
    ctrl = TimerAction(period=6.0, actions=[chain[0]])
    h1 = RegisterEventHandler(OnProcessExit(target_action=chain[0], on_exit=[chain[1]]))
    h2 = RegisterEventHandler(OnProcessExit(target_action=chain[1], on_exit=[chain[2]]))
    return [gz, rsp, spawn, bridge, ctrl, h1, h2]


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument("scenario", default_value="0"),
        DeclareLaunchArgument("seed", default_value="0"),
        DeclareLaunchArgument("gui", default_value="false"),
        OpaqueFunction(function=_setup),
    ])
