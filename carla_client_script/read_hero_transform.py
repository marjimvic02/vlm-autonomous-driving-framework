#!/usr/bin/env python3
"""
read_hero_transform.py - read the hero's current CARLA transform and print it ready to
paste into objects.json (carla_spawn_objects spawn_point) for a fixed, reproducible spawn.

Workflow:
    1. Start CARLA + bridge + hero (or CARLA + a manual-control vehicle with role_name=hero).
    2. Drive the hero to the exact start point you want for the demo, and stop.
    3. Run this script. Paste the printed spawn_point block into the hero entry of objects.json.

The bridge's carla_spawn_objects reads spawn_point in CARLA's native frame, which is exactly
what hero.get_transform() returns, so the values are directly usable. Run in the env that has
the carla python package (your pixi 'ros' env):
    python3 read_hero_transform.py
"""

import time
import json
import argparse
import carla


# Query the world until an actor with the given role_name appears.
def get_hero(world, role_name="hero", timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        for actor in world.get_actors():
            if actor.attributes.get("role_name") == role_name:
                return actor
        time.sleep(0.5)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=2000)
    ap.add_argument("--role", default="hero")
    ap.add_argument(
        "--z-offset",
        type=float,
        default=0.3,
        help="meters added to z so the ego does not spawn embedded in the road",
    )
    args = ap.parse_args()

    client = carla.Client(args.host, args.port)
    client.set_timeout(10.0)
    world = client.get_world()

    hero = get_hero(world, args.role)
    if hero is None:
        print(
            f"No actor with role_name={args.role!r} found. "
            f"Start CARLA + bridge + hero (or a manual-control vehicle) first."
        )
        return

    tf = hero.get_transform()
    cmap = world.get_map()

    # Snap to the nearest driving waypoint so the fixed spawn sits centered on the lane,
    # not slightly off from where a hand-driven car happened to stop.
    wp = cmap.get_waypoint(tf.location, lane_type=carla.LaneType.Driving)
    snapped = wp.transform if wp is not None else tf

    def block(t, label):
        sp = {
            "x": round(t.location.x, 3),
            "y": round(t.location.y, 3),
            "z": round(t.location.z + args.z_offset, 3),
            "roll": round(t.rotation.roll, 3),
            "pitch": round(t.rotation.pitch, 3),
            "yaw": round(t.rotation.yaw, 3),
        }
        print(f"\n# {label}")
        print('"spawn_point": ' + json.dumps(sp))

    print(f"Map: {cmap.name}   hero: {hero.type_id}")
    block(tf, "RAW transform (exactly where the hero is now)")
    block(snapped, "WAYPOINT-SNAPPED transform (centered on lane, recommended)")
    print("\nPaste one spawn_point block into the hero entry of objects.json.")
    print("If the ego spawns embedded in or floating above the road, tune --z-offset.")


if __name__ == "__main__":
    main()
