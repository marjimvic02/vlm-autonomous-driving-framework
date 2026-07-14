"""
Pure-logic tests for the core decision logic of the framework.
Runs with plain `python3 test_logic.py` — no ROS, no CARLA needed.

The idea is to copy the exact boolean expressions used in the nodes, so if I break
a sign, a boundary or make a copy-paste mistake, these tests catch it. They do NOT
check the ROS wiring or the CARLA convention (traffic-light facing), that part can
only be verified in the simulator.

The geometry helpers are imported from the shared module instead of being copied here,
so if that math ever drifts it shows up in these tests too.
"""
import os
import sys
from math import radians

# Import the shared, ROS-free geometry helpers straight from the perception package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'perception_module'))
from perception_module.geometry_utils import (  # noqa: E402
    angle_to_direction, faces_ego as _faces_ego_rad)

# ---- constants copied from the nodes ----
TL_STOP_THRESHOLD = 20.0
OBJ_STOP_THRESHOLD = 10.0  # must match action_dispatcher.OBJ_STOP_THRESHOLD
TL_FACING_TOLERANCE = 50.0
INF = float('inf')
VALID_ACTIONS = {
    'FOLLOW_LANE', 'SPEED_UP', 'SLOW_DOWN', 'STOP',
    'TURN_LEFT', 'TURN_RIGHT', 'CHANGE_LANE_LEFT', 'CHANGE_LANE_RIGHT',
}

passed = failed = 0
def check(name, got, exp):
    global passed, failed
    ok = got == exp
    passed += ok; failed += not ok
    print(f'[{"PASS" if ok else "FAIL"}] {name}: got={got} exp={exp}')


# ---- 1. P5 override truth table (llm_output_callback) ----
def should_override(action, red_tl_dist, obj_dist):
    return (action == 'STOP'
            and red_tl_dist != INF
            and red_tl_dist > TL_STOP_THRESHOLD
            and obj_dist > OBJ_STOP_THRESHOLD)

print('\n--- P5 override ---')
check('no TL, no object -> keep STOP (the bug we fixed)', should_override('STOP', INF, INF), False)
check('far red, nothing ahead -> downgrade',              should_override('STOP', 60.0, INF), True)
check('near red -> keep STOP',                            should_override('STOP', 10.0, INF), False)
check('far red but near object -> keep STOP',             should_override('STOP', 60.0, 8.0), False)
check('far red, far object -> downgrade',                 should_override('STOP', 60.0, 30.0), True)
check('not a STOP -> never override',                     should_override('FOLLOW_LANE', 60.0, INF), False)


# ---- 2. safe target_speed conversion (dispatch_action) ----
def resolved_speed(raw, default):
    try:
        speed = float(raw)
    except (TypeError, ValueError):
        speed = None
    if speed is not None and 0.0 <= speed <= 14.0:
        return speed
    return default

print('\n--- safe target_speed ---')
check('None -> default',          resolved_speed(None, 8.33), 8.33)
check('garbage string -> default', resolved_speed('fast', 8.33), 8.33)
check('empty string -> default',   resolved_speed('', 8.33), 8.33)
check('valid string -> parsed',    resolved_speed('8.5', 8.33), 8.5)
check('over range -> default',     resolved_speed(20.0, 8.33), 8.33)
check('negative -> default',       resolved_speed(-1.0, 8.33), 8.33)
check('valid float -> kept',       resolved_speed(5.56, 8.33), 5.56)


# ---- 3. certainty guardrail, case-insensitive (validate_and_publish) ----
def is_low(c):
    return str(c).strip().upper() == 'LOW'

print('\n--- certainty normalization ---')
for v, exp in [('LOW', True), ('low', True), ('Low', True), (' LOW ', True),
               ('HIGH', False), ('MEDIUM', False)]:
    check(f'certainty {v!r}', is_low(v), exp)


# ---- 4. action whitelist (llm_output_callback) ----
print('\n--- whitelist ---')
check('BOGUS rejected', 'BOGUS' in VALID_ACTIONS, False)
check('STOP accepted',  'STOP' in VALID_ACTIONS, True)


# ---- 5. parsed payload must be a dict (validate_and_publish) ----
import json
print('\n--- isinstance dict ---')
check('object -> ok',  isinstance(json.loads('{"action":"STOP"}'), dict), True)
check('string -> reject', isinstance(json.loads('"STOP"'), dict), False)
check('list -> reject',   isinstance(json.loads('[1,2]'), dict), False)
check('number -> reject', isinstance(json.loads('5'), dict), False)


# ---- 6. TL facing filter math (get_nearby_traffic_lights) ----
# NOTE: validates the math is self-consistent under the anti-parallel assumption.
# It does NOT prove CARLA's convention is anti-parallel — verify that in sim.
# Thin degrees wrapper around the shared (radians) helper used by the node.
def faces_ego(tl_yaw_deg, ego_yaw_deg):
    return _faces_ego_rad(radians(tl_yaw_deg), radians(ego_yaw_deg), TL_FACING_TOLERANCE)

print('\n--- TL facing filter (anti-parallel assumption) ---')
check('exactly anti-parallel -> faces',     faces_ego(180, 0), True)
check('same heading -> rejected',           faces_ego(0, 0), False)
check('cross traffic (90 deg) -> rejected', faces_ego(90, 0), False)
check('near anti-parallel (within tol) -> faces', faces_ego(200, 0), True)
check('just outside tol -> rejected',       faces_ego(125, 0), False)


# ---- 7. angle_to_direction full coverage, no gaps over (-180, 180] ----
# angle_to_direction is imported from perception_module.geometry_utils (shared source).
print('\n--- angle_to_direction coverage ---')
covered = all(isinstance(angle_to_direction(a / 10.0), str)
              for a in range(-1800, 1801))
check('every angle in (-180,180] maps to a sector', covered, True)


print(f'\n==== {passed} passed, {failed} failed ====')
exit(1 if failed else 0)
