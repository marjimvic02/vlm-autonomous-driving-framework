"""Validate model responses without ROS or simulator dependencies."""

import json
import math
import re

VALID_ACTIONS = frozenset(
    {
        "FOLLOW_LANE",
        "SPEED_UP",
        "SLOW_DOWN",
        "STOP",
        "TURN_LEFT",
        "TURN_RIGHT",
        "CHANGE_LANE_LEFT",
        "CHANGE_LANE_RIGHT",
    }
)
REQUIRED_FIELDS = (
    "scene_analysis",
    "risk_assessment",
    "action_rationale",
    "action",
    "certainty",
)


def validate_response(raw_response):
    """Return a validated decision, raising ValueError for an unusable response.

    Optional speeds are bounded in m/s. LOW certainty keeps the historical
    SLOW_DOWN override and leaves speed selection to the dispatcher.
    """
    if not isinstance(raw_response, str):
        raise ValueError("Model response must be text")
    clean = re.sub(r"<think>.*?</think>", "", raw_response, flags=re.DOTALL)
    clean = re.sub(r"```(?:json)?\s*", "", clean).strip()
    parsed = json.loads(clean)
    if not isinstance(parsed, dict):
        raise ValueError("Model response must be a JSON object")
    for field in REQUIRED_FIELDS:
        if not isinstance(parsed.get(field), str) or not parsed[field].strip():
            raise ValueError(f"Missing or invalid field: {field}")
    if parsed["action"] not in VALID_ACTIONS:
        raise ValueError(f'Invalid action: {parsed["action"]}')
    parsed["certainty"] = parsed["certainty"].strip().upper()
    if parsed["certainty"] not in {"LOW", "MEDIUM", "HIGH"}:
        raise ValueError("Certainty must be LOW, MEDIUM or HIGH")
    if "target_speed" in parsed:
        speed = parsed["target_speed"]
        if (
            isinstance(speed, (int, float))
            and not isinstance(speed, bool)
            and math.isfinite(speed)
        ):
            parsed["target_speed"] = float(max(0.0, min(14.0, speed)))
        else:
            parsed.pop("target_speed")
    if parsed["certainty"] == "LOW":
        parsed["action"] = "SLOW_DOWN"
        parsed.pop("target_speed", None)
        parsed["action_rationale"] = "Action overridden to SLOW_DOWN due to low certainty."
    return parsed
