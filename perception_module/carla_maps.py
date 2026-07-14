"""Shared CARLA enum mappings for the perception nodes.

Kept here in one place so every node uses the same mapping and they don't end up drifting apart.
"""

# Traffic light state codes, taken from carla_msgs/CarlaTrafficLightStatus
STATE_DICT = {0: 'RED', 1: 'YELLOW', 2: 'GREEN', 3: 'OFF', 4: 'UNKNOWN'}

# Object class codes, taken from derived_object_msgs/Object
CLASSIFICATION_MAP = {
    0: 'UNKNOWN', 1: 'UNKNOWN_SMALL', 2: 'UNKNOWN_MEDIUM',
    3: 'UNKNOWN_BIG', 4: 'PEDESTRIAN', 5: 'BIKE',
    6: 'CAR', 7: 'TRUCK', 8: 'MOTORCYCLE',
    9: 'OTHER_VEHICLE', 10: 'BARRIER', 11: 'SIGN'
}
