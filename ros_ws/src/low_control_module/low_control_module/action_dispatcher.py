"""Translate semantic driving actions into CARLA Traffic Manager commands."""

import time
import math
import xml.etree.ElementTree as ET

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import carla
import json

RAMP_RATE = 3.0  # m/s per second (approx. 10.8 km/h per second)

DEFAULT_SPEEDS_MS = {
    "FOLLOW_LANE": 8.33,  # 30 km/h
    "SPEED_UP": 13.89,  # 50 km/h
    "SLOW_DOWN": 4.17,  # 15 km/h
    "STOP": 0.0,
    "TURN_LEFT": 5.56,  # 20 km/h, safe turning speed
    "TURN_RIGHT": 5.56,
    "CHANGE_LANE_LEFT": 8.33,
    "CHANGE_LANE_RIGHT": 8.33,
}

VALID_ACTIONS = set(DEFAULT_SPEEDS_MS.keys())

EMERGENCY_ACTIONS = {"STOP", "SLOW_DOWN"}

ACTION_MIN_DURATION = (
    {  # Minimum time (in seconds) an action must last before a new one can be accepted
        "FOLLOW_LANE": 2.5,
        "SPEED_UP": 2.5,
        "SLOW_DOWN": 2.5,
        "STOP": 4.0,
        "TURN_LEFT": 8.0,
        "TURN_RIGHT": 8.0,
        "CHANGE_LANE_LEFT": 5.0,
        "CHANGE_LANE_RIGHT": 5.0,
    }
)

STALE_TIMEOUT = 8.0  # seconds without LLM output, forces SLOW_DOWN

TL_STOP_THRESHOLD = 20.0  # In meters. STOP overridden to SLOW_DOWN if red TL is farther than this

OBJ_STOP_THRESHOLD = 10.0  # In meters. STOP is respected if obstacle is within this distance


class ActionDispatcher(Node):
    def __init__(self):
        super().__init__("action_dispatcher_node")

        self.declare_parameter("host", "localhost")
        self.declare_parameter("port", 2000)
        self.declare_parameter("timeout", 10.0)
        self.ready = False
        self.hero = None
        # Last action issued as a discrete TM action, used to avoid re-issuing it.
        # Initialized here so dispatch_action stays safe even if the CARLA client fails below
        self.last_dispatched_action = None

        # Subscription to LLM output topic
        self.create_subscription(String, "/llm/output", self.llm_output_callback, 10)

        # Publish the action accepted by the control layer for observation and logging.
        self.committed_action_pub = self.create_publisher(String, "/action_committed", 10)

        # Subscription to scene context to read closest frontal red TL distance and closest frontal
        # object distance
        self.closest_forward_red_tl_dist = float("inf")
        self.closest_forward_obj_dist = float("inf")
        self.create_subscription(String, "/scene_context", self.scene_context_callback, 10)

        # Initialize CARLA client
        try:
            self.client = carla.Client(
                self.get_parameter("host").value, self.get_parameter("port").value
            )
            self.client.set_timeout(self.get_parameter("timeout").value)
            self.world = self.client.get_world()
            self.get_logger().info(f"CARLA client [OK]. Map: {self.world.get_map().name}")
        except Exception as e:
            self.get_logger().error(f"CARLA client unavailable[FAIL]: {e}")
            return

        # Connect to Traffic Manager client
        try:
            self.tm = self.client.get_trafficmanager(8000)
            self.get_logger().info("Traffic Manager [OK]")
        except Exception as e:
            self.get_logger().error(f"Traffic Manager [FAIL]: {e}")
            return

        # Find ego vehicle
        try:
            self.hero = self.get_hero(self.world)
            if self.hero:
                self.get_logger().info(f"Hero vehicle found [OK]: {self.hero.type_id}")
                self.hero.set_autopilot(True, 8000)  # Enable TM autopilot for the ego vehicle
                self.get_logger().info("Ego vehicle set to autopilot [OK]")
                # Disable TM automatic stop on red TLs
                self.tm.ignore_lights_percentage(self.hero, 100)
                self.get_logger().info("TM TLs compliance disabled [OK]")
                # Disable TM autonomous lane changes
                self.tm.auto_lane_change(self.hero, False)
                self.get_logger().info("TM autonomous lane changes disabled [OK]")
                # Reduce the randomness of the TM seed to zero for reproducibility
                self.tm.set_random_device_seed(0)
                self.get_logger().info("TM random seed set to zero [OK]")
            else:
                self.get_logger().error(
                    "Hero vehicle not found [FAIL]: no actor with role_name=hero"
                )
                return
        except Exception as e:
            self.get_logger().error(f"Hero vehicle not found [FAIL]: {e}")
            return

        # Speed ramp state
        self.target_speed_ms = 8.33
        self.current_speed_ms = 0.0
        self.create_timer(0.1, self.speed_ramp_callback)  # 10 Hz

        # Commitment state
        self.current_action = None
        self.action_start_time = None
        self.last_llm_time = time.time()
        self.create_timer(1.0, self.stale_check_callback)
        self.ready = True

        # The speed ramp applies the target speed gradually to avoid abrupt changes

    def speed_ramp_callback(self):
        if self.hero is None:
            return
        dt = 0.1  # Timer period (in seconds), the smaller it is the smoother the ramp
        diff = self.target_speed_ms - self.current_speed_ms
        max_delta = RAMP_RATE * dt
        self.current_speed_ms += max(
            min(diff, max_delta), -max_delta
        )  # Clamp the speed change to the ramp rate
        self.tm.set_desired_speed(self.hero, self.current_speed_ms * 3.6)  # TM expects km/h

        # Blocks new actions unless the minimum duration for the current action has elapsed
        # Emergency actions (STOP, SLOW_DOWN) are not affected

    def can_accept_action(self, new_action):
        if new_action in EMERGENCY_ACTIONS:
            return True
        if self.current_action is None:
            return True
        elapsed = (
            time.time() - self.action_start_time
        )  # How long the current action has been active
        return elapsed >= ACTION_MIN_DURATION.get(self.current_action, 2.0)

    # Main pipeline for every VLM output: parse -> validate -> safety overrides -> commitment check
    # -> dispatch
    def llm_output_callback(self, msg):
        if not self.ready:
            return
        try:
            action_data = json.loads(msg.data)
            if not isinstance(action_data, dict):
                raise ValueError("Expected a JSON object")
            new_action = action_data["action"]
            if not isinstance(new_action, str):
                raise ValueError("Action must be a string")
        except (ValueError, KeyError, TypeError) as e:
            self.get_logger().error(f"Invalid LLM output: {e}")
            return

        # Reject any action outside the defined set of valid actions before it reaches dispatch
        if new_action not in VALID_ACTIONS:
            self.get_logger().error(f"Unknown action: [{new_action}] not in {VALID_ACTIONS}")
            return

        self.last_llm_time = time.time()  # Only valid decisions refresh the watchdog.

        # Override STOP to SLOW_DOWN if the closest forward red TL is farther than the threshold
        # Only commit when a real red TL exists, is far, and no near frontal object justifies a
        # full stop
        red_tl_dist = self.closest_forward_red_tl_dist
        obj_dist = self.closest_forward_obj_dist
        if (
            new_action == "STOP"
            and red_tl_dist != float("inf")
            and red_tl_dist > TL_STOP_THRESHOLD
            and obj_dist > OBJ_STOP_THRESHOLD
        ):
            self.get_logger().warn(
                f"STOP overridden to SLOW_DOWN: red TL at "
                f"{red_tl_dist:.1f}m > {TL_STOP_THRESHOLD}m, "
                f"nearest frontal object {obj_dist:.1f}m"
            )
            new_action = "SLOW_DOWN"
            action_data["action"] = "SLOW_DOWN"
            action_data["target_speed"] = DEFAULT_SPEEDS_MS["SLOW_DOWN"]

        # Check commitment before accepting the new action
        if not self.can_accept_action(new_action):
            remaining = ACTION_MIN_DURATION[self.current_action] - (
                time.time() - self.action_start_time
            )
            self.get_logger().info(
                f"Commitment active [{self.current_action}], ignoring [{new_action}] "
                f"({remaining:.1f}s remaining)"
            )
            return

        # Accept the new action and (re)start its commitment timer
        self.current_action = new_action
        self.action_start_time = time.time()

        committed_msg = String()
        committed_msg.data = new_action
        self.committed_action_pub.publish(committed_msg)  # Publish the committed action

        self.dispatch_action(action_data)  # Execute the action in CARLA

    def scene_context_callback(self, msg):
        # Parse XML to find the closest forward red traffic light and object distances
        try:
            root = ET.fromstring(f"<root>{msg.data}</root>")

            # Closest frontal red TL distance
            min_dist = float("inf")
            for tl in root.findall(".//traffic_light"):
                state = tl.find("state")
                direction = tl.find("direction")
                dist = tl.find("distance")
                if state is not None and direction is not None and dist is not None:
                    if state.text == "RED" and "FRONT" in (direction.text or ""):
                        min_dist = min(min_dist, float(dist.text))
            self.closest_forward_red_tl_dist = min_dist

            # Closest frontal object distance
            min_obj = float("inf")
            for obj in root.findall(".//object"):
                direction = obj.find("direction")
                dist = obj.find("distance")
                if direction is not None and dist is not None:
                    if "FRONT" in (direction.text or ""):
                        min_obj = min(min_obj, float(dist.text))
            self.closest_forward_obj_dist = min_obj

        except (ET.ParseError, TypeError, ValueError) as exc:
            self.get_logger().debug(f"Ignoring malformed scene context: {exc}")

        # If no output is received from the VLM within STALE_TIMEOUT seconds, force a SLOW_DOWN
        # action

    def stale_check_callback(self):
        if time.time() - self.last_llm_time > STALE_TIMEOUT:
            if self.current_action != "SLOW_DOWN":
                self.get_logger().warn("LLM output stale, forcing SLOW_DOWN")
                self.target_speed_ms = DEFAULT_SPEEDS_MS["SLOW_DOWN"]
                self.current_action = "SLOW_DOWN"
                self.action_start_time = time.time()
                committed_msg = String()
                committed_msg.data = "SLOW_DOWN"
                self.committed_action_pub.publish(committed_msg)

        # Dispatches the received action to CARLA, in the form of TM behaviors

    def dispatch_action(self, action_data):
        if not self.hero:
            self.get_logger().error("Hero vehicle not found, skipping action")
            return

        action = action_data["action"]
        self.get_logger().info(f"Next action: [{action}]")

        # Sets target speed and ramp callback applies it gradually
        raw_speed = action_data.get("target_speed", None)
        if action == "STOP":
            self.target_speed_ms = 0.0
        else:
            try:
                speed = float(raw_speed)
            except (TypeError, ValueError, OverflowError):
                speed = None
            if isinstance(raw_speed, bool) or (speed is not None and not math.isfinite(speed)):
                speed = None
            # Only trust the speed suggested by the VLM if it falls in a sensible band for the
            # action,
            # otherwise fall back to the default speed defined for that action
            if (speed is not None and 5.0 < speed <= 14.0) and action in {
                "FOLLOW_LANE",
                "SPEED_UP",
            }:
                self.target_speed_ms = speed
            elif (speed is not None and 0.0 <= speed <= 5.0) and action == "SLOW_DOWN":
                self.target_speed_ms = speed
            else:
                self.target_speed_ms = DEFAULT_SPEEDS_MS[action]

        # Discrete TM actions are issued only when the action changes, so a turn or lane
        # change is not re-queued while the same action stays committed across LLM inference cycles
        is_new_action = action != self.last_dispatched_action

        if action == "FOLLOW_LANE":
            if is_new_action:
                # Clear any pending route instruction left by an interrupted turn
                self.tm.set_route(self.hero, [])

        # CARLA convention for force_lane_change(actor, direction): True = right lane, False = left
        # lane
        elif action == "CHANGE_LANE_LEFT":
            if is_new_action:
                self.tm.force_lane_change(self.hero, False)

        elif action == "CHANGE_LANE_RIGHT":
            if is_new_action:
                self.tm.force_lane_change(self.hero, True)

        elif action == "TURN_LEFT":
            if is_new_action:
                self.tm.set_route(self.hero, ["Left"])

        elif action == "TURN_RIGHT":
            if is_new_action:
                self.tm.set_route(self.hero, ["Right"])

        self.last_dispatched_action = action

    # Poll the world until the bridge-spawned hero appears. Returns the hero actor, or None
    # if it does not show up within timeout seconds. The polling loop matters once every node
    # and CARLA script is launched together: a consumer may come up before the bridge has
    # spawned the hero, and a single-pass lookup would race and fail
    def get_hero(self, world, timeout=30.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            actors = list(world.get_actors())
            for actor in actors:
                if actor.attributes.get("role_name") == "hero":
                    return actor
            time.sleep(0.5)
        return None


def main(args=None):
    rclpy.init(args=args)
    node = ActionDispatcher()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
