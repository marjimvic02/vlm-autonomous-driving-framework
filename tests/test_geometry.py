"""Verify sector boundaries and the traffic-light orientation filter."""

import sys
import unittest
from math import radians
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ros_ws/src/perception_module"))
from perception_module.geometry_utils import (  # noqa: E402
    angle_to_direction,
    faces_ego,
    normalize_angle_deg,
)


class GeometryTests(unittest.TestCase):
    def test_normalization_wraps_at_both_ends(self):
        for angle, expected in [(180, -180), (-180, -180), (540, -180), (361, 1), (-361, -1)]:
            with self.subTest(angle=angle):
                self.assertEqual(normalize_angle_deg(angle), expected)

    def test_direction_boundaries(self):
        for angle, expected in [
            (0, "FRONT"),
            (22.5, "FRONT"),
            (22.6, "FRONT-LEFT"),
            (67.5, "FRONT-LEFT"),
            (90, "LEFT"),
            (135, "BEHIND-LEFT"),
            (180, "BEHIND"),
            (-135, "BEHIND-RIGHT"),
            (-90, "RIGHT"),
            (-22.5, "FRONT-RIGHT"),
            (-22.4, "FRONT"),
        ]:
            with self.subTest(angle=angle):
                self.assertEqual(angle_to_direction(angle), expected)

    def test_facing_filter_handles_wrapping_and_tolerance(self):
        self.assertTrue(faces_ego(radians(180), 0, 50))
        self.assertTrue(faces_ego(radians(-170), radians(10), 50))
        self.assertTrue(faces_ego(radians(130), 0, 50))
        self.assertFalse(faces_ego(radians(129), 0, 50))
        self.assertFalse(faces_ego(radians(90), 0, 50))
        self.assertFalse(faces_ego(0, 0, 50))
