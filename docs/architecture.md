# Architecture and interfaces

The framework implements a hierarchical perception, planning and execution loop. CARLA provides the physical environment, sensors and actuation. An external VLM service provides high-level planning. Three project ROS 2 packages coordinate the workflow.

## Perception

`scene_context_node` maintains the latest received values and publishes an XML fragment on `/scene_context` at 1 Hz. Sensor readings are not timestamp-synchronized. Initial values are zero and lists are empty until messages arrive.

| Input | ROS type | Information used |
| --- | --- | --- |
| `/carla/hero/speedometer` | `std_msgs/Float32` | Speed in m/s |
| `/carla/hero/imu` | `sensor_msgs/Imu` | x/y acceleration and z angular velocity |
| `/carla/hero/odometry` | `nav_msgs/Odometry` | Position and orientation |
| `/carla/hero/objects` | `derived_object_msgs/ObjectArray` | Object classes, positions and velocities |
| `/carla/traffic_lights/info` | `carla_msgs/CarlaTrafficLightInfoList` | Traffic-light positions and orientations |
| `/carla/traffic_lights/status` | `carla_msgs/CarlaTrafficLightStatusList` | Traffic-light states |

Objects within 50 m are considered, excluding those within 0.5 m of the ego center. The five closest objects are included. Relative positions are mapped to eight angular sectors. Angles are normalized to `[-180, 180)`; axes follow the bridge coordinate system.

Traffic lights within 80 m are considered, excluding those behind the ego or without an approximately antiparallel heading (50° tolerance). This is a geometric heuristic rather than an explicit traffic-light-to-lane association. Traffic-light topics use `TRANSIENT_LOCAL` QoS, and the context includes the age of the latest status update.

The context has two top-level elements, `<self_data>` and `<surroundings_data>`; consumers wrap them in a root element for XML parsing. The estimated braking distance is `v² / (2 × 3.0) × 1.5`, in meters. It does not explicitly include travel during inference.

Object and traffic-light pseudo-sensors provide ideal simulator information. Although `objects.json` spawns additional sensors, the planner does not consume all of them.

## Decision-making

`prompt_manager` subscribes to `/scene_context` and `/carla/hero/rgb_front/image`. It resizes the image to **320 × 180**, compresses it as JPEG at quality 75 and encodes it in base64. Each request combines the [experimental behavior prompt](../ros_ws/src/decision_making_module/prompt/behavior_prompt.md), XML context and image.

A multithreaded executor keeps subscriptions active during blocking inference. A lock permits only one inference call at a time; incoming contexts do not create additional requests while another call is running. The node uses the latest available observations, without a queue of pending inferences or navigation memory.

Ollama uses its native HTTP API. OpenAI and OpenRouter use the OpenAI-compatible client. Initial warmup is best-effort: subsequent calls remain enabled if it fails. The node records the raw response before validation.

The `/llm/output` message is a `std_msgs/String` containing a JSON object:

```json
{
  "scene_analysis": "Description of the scene.",
  "risk_assessment": "Assessment of the observed risks.",
  "action_rationale": "Reason for the selected action.",
  "action": "FOLLOW_LANE",
  "target_speed": 8.0,
  "certainty": "HIGH"
}
```

The validator removes `<think>` tags and Markdown fences, requires nonempty text fields, checks the eight-action vocabulary and accepts certainty levels `LOW`, `MEDIUM` or `HIGH`. Optional speed is bounded to [0, 14] m/s; nonnumeric or nonfinite values are discarded. Invalid responses produce `SLOW_DOWN`. `LOW` certainty also forces `SLOW_DOWN`, removing the requested speed so that the dispatcher uses its default.

Type and finite-value checks were strengthened during repository preparation. Campaign analysis retains its historical criteria, described in [experiments](experiments.md).

## Control

`action_dispatcher` subscribes to `/llm/output` and `/scene_context` and connects directly to the CARLA API and Traffic Manager. It searches for an actor with `role_name=hero` for up to 30 s. ROS parameters `host`, `port` and `timeout` are propagated from the launch file.

The dispatcher enables ego autopilot, disables Traffic Manager's automatic traffic-light compliance and autonomous lane changes, and sets its random seed to zero. Traffic Manager's collision response remains enabled. Driving still depends on that controller; an empty route lets it select paths at junctions and does not implement destination-based navigation.

| Action | Default speed (m/s) | Minimum duration (s) |
| --- | ---: | ---: |
| `FOLLOW_LANE` | 8.33 | 2.5 |
| `SPEED_UP` | 13.89 | 2.5 |
| `SLOW_DOWN` | 4.17 | 2.5 |
| `STOP` | 0.00 | 4.0 |
| `TURN_LEFT` / `TURN_RIGHT` | 5.56 | 8.0 |
| `CHANGE_LANE_LEFT` / `CHANGE_LANE_RIGHT` | 8.33 | 5.0 |

The VLM's speed is accepted for `FOLLOW_LANE` and `SPEED_UP` when `5 < v ≤ 14`, or for `SLOW_DOWN` when `0 ≤ v ≤ 5`; otherwise the default is used. `STOP` always requests zero. A ramp updated at 10 Hz limits the change in the speed **command** to 3 m/s². Actual acceleration depends on vehicle dynamics and Traffic Manager.

Urgent actions `STOP` and `SLOW_DOWN` can interrupt any action. Other commands respect the current action's minimum duration. Every accepted action restarts that duration, including repeated commands. Turns and lane changes are sent to Traffic Manager only when the action changes, to avoid queuing the same maneuver repeatedly.

`STOP` is replaced by `SLOW_DOWN` if a frontal red light exists beyond 20 m and no frontal object is within 10 m. Frontal sectors include `FRONT-LEFT` and `FRONT-RIGHT`. After 8 s without a valid output, the watchdog forces `SLOW_DOWN`. Accepted actions are published as text on `/action_committed`; the perception node does not consume this topic.

## Safeguard scope

Filtering limits format errors, unknown actions, command oscillation and gaps between decisions. It does not verify the full semantic correctness of a maneuver or guarantee a safe stop for every failure. The fallback and watchdog request reduced speed rather than a complete stop. There is no general freshness check for context or images.

The experimental prompt is preserved to retain the identity of the evaluated setup. Some prompt instructions differ from runtime checks; for example, the prompt permits up to 6 m/s for certain slowdowns near traffic lights, while the dispatcher accepts at most 5 m/s for `SLOW_DOWN`. The thesis, prompt and implemented safeguards should be read together.
