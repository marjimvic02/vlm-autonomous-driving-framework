"""Exercise actual dispatcher callbacks with ROS and CARLA interfaces replaced."""

import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch


def load_dispatcher():
    stubs = {
        name: ModuleType(name)
        for name in ["rclpy", "rclpy.node", "std_msgs", "std_msgs.msg", "carla"]
    }
    stubs["rclpy.node"].Node = object
    stubs["std_msgs.msg"].String = SimpleNamespace
    path = (
        Path(__file__).resolve().parents[1]
        / "ros_ws/src/low_control_module/low_control_module/action_dispatcher.py"
    )
    spec = importlib.util.spec_from_file_location("dispatcher_under_test", path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)
    return module


dispatcher = load_dispatcher()


class DispatcherTests(unittest.TestCase):
    def setUp(self):
        self.node = dispatcher.ActionDispatcher.__new__(dispatcher.ActionDispatcher)
        self.node.ready = True
        self.node.get_logger = Mock(return_value=Mock())
        self.node.last_llm_time = 1.0
        self.node.current_action = None
        self.node.action_start_time = None
        self.node.closest_forward_red_tl_dist = float("inf")
        self.node.closest_forward_obj_dist = float("inf")
        self.node.committed_action_pub = Mock()
        self.node.hero = object()
        self.node.tm = Mock()
        self.node.last_dispatched_action = None

    def test_invalid_payload_does_not_refresh_watchdog_or_commit(self):
        for payload in ["[]", "null", "{", "{}", '{"action": []}', '{"action": "REVERSE"}']:
            with self.subTest(payload=payload):
                self.node.llm_output_callback(SimpleNamespace(data=payload))
                self.assertEqual(self.node.last_llm_time, 1.0)
                self.node.committed_action_pub.publish.assert_not_called()

    def test_unavailable_simulator_ignores_decisions(self):
        self.node.ready = False
        self.node.llm_output_callback(SimpleNamespace(data='{"action": "FOLLOW_LANE"}'))
        self.node.committed_action_pub.publish.assert_not_called()

    def test_stop_override_requires_real_far_light_and_no_close_object(self):
        self.node.dispatch_action = Mock()
        for light, obj, expected in [
            (float("inf"), float("inf"), "STOP"),
            (60, 30, "SLOW_DOWN"),
            (60, 8, "STOP"),
            (20, 30, "STOP"),
            (60, 10, "STOP"),
        ]:
            with self.subTest(light=light, obj=obj):
                self.node.closest_forward_red_tl_dist = light
                self.node.closest_forward_obj_dist = obj
                self.node.llm_output_callback(SimpleNamespace(data='{"action": "STOP"}'))
                self.assertEqual(self.node.current_action, expected)

    def test_emergency_action_interrupts_commitment(self):
        self.node.current_action = "TURN_LEFT"
        self.node.action_start_time = 19.0
        with patch.object(dispatcher.time, "time", return_value=20.0):
            self.assertFalse(self.node.can_accept_action("FOLLOW_LANE"))
            self.assertTrue(self.node.can_accept_action("STOP"))
            self.assertTrue(self.node.can_accept_action("SLOW_DOWN"))

    def test_speed_rules_and_discrete_maneuver_are_applied(self):
        self.node.dispatch_action({"action": "FOLLOW_LANE", "target_speed": 0})
        self.assertEqual(self.node.target_speed_ms, 8.33)
        self.node.dispatch_action({"action": "SLOW_DOWN", "target_speed": 4})
        self.assertEqual(self.node.target_speed_ms, 4.0)
        self.node.dispatch_action({"action": "SLOW_DOWN", "target_speed": True})
        self.assertEqual(self.node.target_speed_ms, 4.17)
        self.node.dispatch_action({"action": "STOP", "target_speed": 12})
        self.assertEqual(self.node.target_speed_ms, 0)
        self.node.dispatch_action({"action": "CHANGE_LANE_LEFT"})
        self.node.dispatch_action({"action": "CHANGE_LANE_LEFT"})
        self.node.tm.force_lane_change.assert_called_once_with(self.node.hero, False)

    def test_watchdog_reduces_speed_and_publishes_committed_action(self):
        with patch.object(dispatcher.time, "time", return_value=10.0):
            self.node.stale_check_callback()
        self.assertEqual(self.node.current_action, "SLOW_DOWN")
        self.assertEqual(self.node.target_speed_ms, 4.17)
        self.assertEqual(
            self.node.committed_action_pub.publish.call_args.args[0].data, "SLOW_DOWN"
        )

    def test_ramp_limits_command_increment(self):
        self.node.current_speed_ms = 0.0
        self.node.target_speed_ms = 8.33
        self.node.speed_ramp_callback()
        self.assertAlmostEqual(self.node.current_speed_ms, 0.3)
        self.node.tm.set_desired_speed.assert_called_once()
        self.assertAlmostEqual(self.node.tm.set_desired_speed.call_args.args[1], 1.08)

    def test_scene_context_finds_frontal_distances(self):
        xml = (
            "<surroundings_data><traffic_light><state>RED</state>"
            "<direction>FRONT-LEFT</direction><distance>30</distance></traffic_light>"
            "<object><direction>FRONT</direction><distance>8</distance></object>"
            "</surroundings_data>"
        )
        self.node.scene_context_callback(SimpleNamespace(data=xml))
        self.assertEqual(self.node.closest_forward_red_tl_dist, 30)
        self.assertEqual(self.node.closest_forward_obj_dist, 8)
        self.node.scene_context_callback(SimpleNamespace(data="<invalid"))
        self.assertEqual(self.node.closest_forward_red_tl_dist, 30)
