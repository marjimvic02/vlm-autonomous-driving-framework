"""Shared geometry helpers for the perception nodes.

The perception node and the tests use the same coordinate conventions.
"""

from math import degrees


# Wrap an angle in degrees to the [-180, 180) range
def normalize_angle_deg(angle):
    return (angle + 180) % 360 - 180


# Map a relative angle in degrees [-180, 180) to one of the 8 sector labels
def angle_to_direction(angle):
    if -22.5 < angle <= 22.5:
        return "FRONT"
    elif 22.5 < angle <= 67.5:
        return "FRONT-LEFT"
    elif 67.5 < angle <= 112.5:
        return "LEFT"
    elif 112.5 < angle <= 157.5:
        return "BEHIND-LEFT"
    elif angle > 157.5 or angle <= -157.5:
        return "BEHIND"
    elif -157.5 < angle <= -112.5:
        return "BEHIND-RIGHT"
    elif -112.5 < angle <= -67.5:
        return "RIGHT"
    else:
        return "FRONT-RIGHT"


# True if a traffic light governs the ego lane: its heading is roughly anti-parallel
# to the ego's (it faces oncoming traffic). Both yaws are in radians, tolerance in degrees.
def faces_ego(tl_yaw, ego_yaw, tol_deg):
    heading_diff = normalize_angle_deg(degrees(tl_yaw - ego_yaw))
    return abs(abs(heading_diff) - 180.0) <= tol_deg
