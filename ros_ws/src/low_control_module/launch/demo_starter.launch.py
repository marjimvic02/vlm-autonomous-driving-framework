"""Launch the bridge, ego sensors and the three VLM driving nodes.

Start CARLA separately with ``pixi run carla``. Default startup delays preserve
those used in the experiments; they are launch arguments for other machines.
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    """Describe the simulator connections and delayed framework startup."""
    objects_default = os.path.join(
        get_package_share_directory("low_control_module"), "launch", "objects.json"
    )
    defaults = {
        "objects_definition_file": objects_default,
        "host": "localhost",
        "port": "2000",
        "timeout": "10",
        "llm_provider": "ollama",
        "llm_model": "qwen3.5:2b",
        "spawn_delay": "10.0",
        "perception_delay": "160.0",
        "decision_delay": "165.0",
        "control_delay": "175.0",
    }
    cfg = {name: LaunchConfiguration(name) for name in defaults}
    declares = [
        DeclareLaunchArgument(name, default_value=value) for name, value in defaults.items()
    ]

    def include(package, filename, arguments):
        return IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(get_package_share_directory(package), filename)
            ),
            launch_arguments=arguments.items(),
        )

    connection = {name: cfg[name] for name in ("host", "port", "timeout")}
    bridge = include("carla_ros_bridge", "carla_ros_bridge.launch.py", connection)
    spawn = TimerAction(
        period=cfg["spawn_delay"],
        actions=[
            include(
                "carla_spawn_objects",
                "carla_spawn_objects.launch.py",
                {**connection, "objects_definition_file": cfg["objects_definition_file"]},
            )
        ],
    )
    scene_context = TimerAction(
        period=cfg["perception_delay"],
        actions=[
            Node(package="perception_module", executable="scene_context_node", output="screen")
        ],
    )
    prompt_mgr = TimerAction(
        period=cfg["decision_delay"],
        actions=[
            Node(
                package="decision_making_module",
                executable="prompt_manager",
                output="screen",
                additional_env={
                    "LLM_PROVIDER": cfg["llm_provider"],
                    "LLM_MODEL": cfg["llm_model"],
                },
            )
        ],
    )
    dispatcher = TimerAction(
        period=cfg["control_delay"],
        actions=[
            Node(
                package="low_control_module",
                executable="action_dispatcher",
                output="screen",
                parameters=[
                    {
                        "host": cfg["host"],
                        "port": ParameterValue(cfg["port"], value_type=int),
                        "timeout": ParameterValue(cfg["timeout"], value_type=float),
                    }
                ],
            )
        ],
    )
    return LaunchDescription(declares + [bridge, spawn, scene_context, prompt_mgr, dispatcher])
