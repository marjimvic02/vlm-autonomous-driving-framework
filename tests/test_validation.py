"""Exercise the same response validator called by the ROS decision node."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ros_ws/src/decision_making_module"))
from decision_making_module.response_validation import validate_response  # noqa: E402


def response(**overrides):
    data = {
        "scene_analysis": "Road ahead is clear.",
        "risk_assessment": "No immediate risk.",
        "action_rationale": "Continue along the lane.",
        "action": "FOLLOW_LANE",
        "certainty": "HIGH",
        "target_speed": 8.0,
    }
    data.update(overrides)
    return json.dumps(data)


class ResponseValidationTests(unittest.TestCase):
    def test_valid_decision_preserves_action_and_speed(self):
        self.assertEqual(validate_response(response())["target_speed"], 8.0)
        self.assertEqual(validate_response(response())["action"], "FOLLOW_LANE")

    def test_thinking_and_markdown_are_removed(self):
        raw = "<think>internal notes</think>\n```json\n" + response() + "\n```"
        self.assertEqual(validate_response(raw)["action"], "FOLLOW_LANE")

    def test_malformed_or_non_object_json_is_rejected(self):
        for raw in ["", "{", "[]", '"STOP"', "null", "12", None]:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                validate_response(raw)

    def test_missing_empty_or_non_text_fields_are_rejected(self):
        for field in [
            "scene_analysis",
            "risk_assessment",
            "action_rationale",
            "action",
            "certainty",
        ]:
            for value in [None, [], {}, 42, "", "   "]:
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    validate_response(response(**{field: value}))
        data = json.loads(response())
        del data["certainty"]
        with self.assertRaises(ValueError):
            validate_response(json.dumps(data))

    def test_unknown_actions_and_certainty_are_rejected(self):
        for override in [{"action": "REVERSE"}, {"action": "Turn Left"}, {"certainty": "unknown"}]:
            with self.subTest(override=override), self.assertRaises(ValueError):
                validate_response(response(**override))

    def test_low_certainty_overrides_action_and_removes_requested_speed(self):
        data = validate_response(response(action="SPEED_UP", certainty=" low ", target_speed=13.0))
        self.assertEqual(data["action"], "SLOW_DOWN")
        self.assertEqual(data["certainty"], "LOW")
        self.assertNotIn("target_speed", data)

    def test_optional_speed_is_clamped_or_discarded(self):
        for value, expected in [(-2, 0.0), (20, 14.0), (4.5, 4.5)]:
            with self.subTest(value=value):
                self.assertEqual(
                    validate_response(response(target_speed=value))["target_speed"], expected
                )
        for value in [True, None, "8", float("nan"), float("inf"), float("-inf")]:
            with self.subTest(value=value):
                self.assertNotIn("target_speed", validate_response(response(target_speed=value)))


if __name__ == "__main__":
    unittest.main()
