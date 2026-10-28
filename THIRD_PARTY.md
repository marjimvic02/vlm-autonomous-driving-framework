# Vendored dependencies and attribution

The project includes third-party ROS sources to preserve the patches used with CARLA 0.9.16. They are distributed as vendored code with their notices and licenses, rather than as Git submodules.

| Directory | Origin | Reference revision | License |
| --- | --- | --- | --- |
| `ros_ws/src/carla-ros-bridge` | `https://github.com/ttgamage/carla-ros-bridge` | `c596934b430173a5713bc1ac191ff23ae8df9686` | [MIT](ros_ws/src/carla-ros-bridge/LICENSE) |
| `ros_ws/src/ros-carla-msgs` | `https://github.com/carla-simulator/ros-carla-msgs` | `081fdcdc8a4f8d4ce936b792c4ef13aba3fd7478` | [MIT](ros_ws/src/ros-carla-msgs/LICENSE) |

The bridge fork retains notices from CARLA and its other contributors. Local changes relative to the reference revision are preserved in [this patch](docs/third_party/carla-ros-bridge.patch): the CARLA version, covariance wrappers and classification certainty in `traffic_participant.py`, and the fixed spawn point in `objects.json`. The experimental sensor configuration is also installed by the project's `low_control_module` package so it can be used outside the source tree.

The original `.git` metadata from both copies is retained locally under `.local/vendor-git/`, excluded from publication. This prevents Git from treating the dependencies as nested repositories without a downloadable reference. Review the patches and revalidate integration before replacing these sources with newer versions.

`derived_object_msgs` is a local ROS 2 compatibility package. It retains the existing MIT declaration in its `package.xml`; no additional upstream provenance was inferred or license declaration changed during cleanup. Locally archived ROS template tests retain their Apache-2.0 headers from the Open Source Robotics Foundation; the archive is excluded from publication.

The CARLA simulator, Python client, ROS 2, Pixi, installed libraries and VLM models/services are external dependencies with their own terms. Simulator binaries and model weights are not included in this repository.
