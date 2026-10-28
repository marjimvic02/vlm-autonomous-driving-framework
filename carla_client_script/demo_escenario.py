"""
Sets up the demo scenario in CARLA: seeded background traffic plus the optional
actors (obstacle, pedestrian and ambulance) that each test case needs.
Driving the hero is left to the framework, this script only populates the world.

Run AFTER CARLA, the bridge and the hero are up.
"""

import time
import random
import argparse
import carla

# Configuration
HOST = "localhost"
PORT = 2000
TM_PORT = 8000
SEED = 0  # repeatable initialization; asynchronous runs may still differ

AMBIENT_VEHICLES = 15  # background traffic count
AMBIENT_SPEED_DIFF = 10.0  # % slower than limit, applied globally for calm traffic

# Placement (meters along the road from the hero, at spawn time)
OBSTACLE_DISTANCE = 40.0  # stationary vehicle ahead in the hero's lane
PEDESTRIAN_DISTANCE = 35.0  # crossing point ahead
AMBULANCE_BEHIND = 30.0  # ambulance starts this far behind the hero

# Distance-based triggers (hero-to-actor, meters)
PED_TRIGGER_DIST = 18.0  # pedestrian starts crossing when hero is this close
PED_CROSS_SPEED = 1.5  # m/s
POLL_HZ = 10.0

spawned = []  # everything created, for cleanup


# Query the world until the bridge-spawned hero appears. Returns the hero actor, or None
# if it does not show up within timeout seconds. The querying loop matters once every node
# and CARLA script is launched together.
def get_hero(world, timeout=30.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        actors = list(world.get_actors())
        for actor in actors:
            if actor.attributes.get("role_name") == "hero":
                return actor
        time.sleep(0.5)
    return None


# True if both waypoints run in the same travel direction. In CARLA the sign of lane_id
# encodes the direction, so a positive product means both lanes go the same way
def same_direction(wp_a, wp_b):
    return wp_a.lane_id * wp_b.lane_id > 0


# Seeded background traffic on autopilot, away from the hero
def spawn_ambient(world, bp_lib, tm, hero, vehicle_count):
    spawn_points = world.get_map().get_spawn_points()
    random.shuffle(spawn_points)  # random.seed already set
    hero_loc = hero.get_location()
    vehicle_bps = [
        b for b in bp_lib.filter("vehicle.*") if int(b.get_attribute("number_of_wheels")) == 4
    ]

    count = 0
    for sp in spawn_points:
        if count >= vehicle_count:
            break
        if sp.location.distance(hero_loc) < 15.0:  # don't box in the hero
            continue
        bp = random.choice(vehicle_bps)
        if bp.has_attribute("role_name"):
            bp.set_attribute("role_name", "autopilot")
        v = world.try_spawn_actor(bp, sp)
        if v is None:
            continue
        v.set_autopilot(True, TM_PORT)
        spawned.append(v)
        count += 1
    print(f"[ambient] spawned {count} background vehicles")


# Stationary vehicle in the hero's lane, ahead
def spawn_obstacle(world, bp_lib, hero_wp):
    nxt = hero_wp.next(OBSTACLE_DISTANCE)
    if not nxt:
        print("[obstacle] no road ahead, skipped")
        return
    tf = nxt[0].transform
    tf.location.z += 0.3  # small lift so the vehicle does not clip the ground when spawning
    bp = bp_lib.find("vehicle.audi.tt")
    obstacle = world.try_spawn_actor(bp, tf)
    if obstacle is None:
        print("[obstacle] spawn failed (occupied?)")
        return
    obstacle.apply_control(carla.VehicleControl(hand_brake=True))
    spawned.append(obstacle)
    print(f"[obstacle] stationary vehicle at {OBSTACLE_DISTANCE:.0f}m ahead")


# Pedestrian waiting at the road edge ahead; crosses when triggered.
# Returns (walker, cross_direction) or (None, None)
def spawn_pedestrian(world, bp_lib, hero_wp):
    nxt = hero_wp.next(PEDESTRIAN_DISTANCE)
    if not nxt:
        print("[pedestrian] no road ahead, skipped")
        return None, None
    wp = nxt[0]
    right = wp.transform.get_right_vector()
    # Start at the right edge of the lane, will cross toward the left
    margin = (
        wp.lane_width / 2.0 + 0.5
    )  # half the lane reaches the edge, +0.5 m to stand just off the road
    start = carla.Location(
        x=wp.transform.location.x + right.x * margin,
        y=wp.transform.location.y + right.y * margin,
        z=wp.transform.location.z + 1.0,
    )
    bp = random.choice(bp_lib.filter("walker.pedestrian.*"))
    if bp.has_attribute("is_invincible"):
        bp.set_attribute("is_invincible", "false")
    walker = world.try_spawn_actor(bp, carla.Transform(start))
    if walker is None:
        print("[pedestrian] spawn failed")
        return None, None
    spawned.append(walker)
    cross_dir = carla.Vector3D(x=-right.x, y=-right.y, z=0.0)
    print(f"[pedestrian] waiting at {PEDESTRIAN_DISTANCE:.0f}m ahead, will cross on approach")
    return walker, cross_dir


# Emergency vehicle with beacons, in the same-direction left lane if it exists,
# starting behind the hero so it approaches from the rear
def spawn_ambulance(world, bp_lib, tm, hero_wp):
    lane = hero_wp.get_left_lane()
    if (
        lane is None
        or lane.lane_type != carla.LaneType.Driving
        or not same_direction(hero_wp, lane)
    ):
        print(
            "[ambulance] no same-direction left lane here "
            "(expected in Town10) — using the hero lane behind instead"
        )
        lane = hero_wp
    back = lane.previous(AMBULANCE_BEHIND)
    if not back:
        print("[ambulance] no road behind, skipped")
        return None
    tf = back[0].transform
    tf.location.z += 0.3  # small lift so the vehicle does not clip the ground when spawning
    amb_bps = bp_lib.filter("vehicle.*.ambulance")
    if not amb_bps:
        amb_bps = bp_lib.filter("vehicle.ford.ambulance")
    if not amb_bps:
        print("[ambulance] no ambulance blueprint in this CARLA build, skipped")
        return None
    amb = world.try_spawn_actor(amb_bps[0], tf)
    if amb is None:
        print("[ambulance] spawn failed (occupied?)")
        return None
    # Emergency beacons (visual only)
    amb.set_light_state(
        carla.VehicleLightState(
            carla.VehicleLightState.Special1 | carla.VehicleLightState.Special2
        )
    )
    amb.set_autopilot(True, TM_PORT)
    tm.ignore_lights_percentage(amb, 100.0)  # emergency runs reds
    tm.vehicle_percentage_speed_difference(amb, -40.0)  # 40% over the limit
    tm.auto_lane_change(amb, False)
    spawned.append(amb)
    print("[ambulance] approaching from behind with beacons on")
    return amb


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        choices=["free", "traffic", "obstacle", "pedestrian", "ambulance"],
        default="traffic",
    )
    parser.add_argument(
        "--vehicles", type=int, default=None, help="ambient vehicle count (free: 0; others: 15)"
    )
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()
    vehicle_count = (
        args.vehicles
        if args.vehicles is not None
        else (0 if args.scenario == "free" else AMBIENT_VEHICLES)
    )
    if vehicle_count < 0:
        parser.error("--vehicles must be non-negative")
    random.seed(args.seed)
    client = carla.Client(args.host, args.port)
    client.set_timeout(10.0)
    world = client.get_world()
    bp_lib = world.get_blueprint_library()
    tm = client.get_trafficmanager(TM_PORT)
    tm.global_percentage_speed_difference(AMBIENT_SPEED_DIFF)

    print(f"Map: {world.get_map().name}")
    hero = get_hero(world)
    if hero is None:
        print("Hero not found. Start CARLA + bridge + hero spawn first.")
        return
    print(f"Hero found: {hero.type_id}")

    hero_map = world.get_map()
    hero_wp = hero_map.get_waypoint(hero.get_location(), lane_type=carla.LaneType.Driving)

    try:
        spawn_ambient(world, bp_lib, tm, hero, vehicle_count)

        walker, cross_dir = (None, None)
        if args.scenario == "obstacle":
            spawn_obstacle(world, bp_lib, hero_wp)
        if args.scenario == "pedestrian":
            walker, cross_dir = spawn_pedestrian(world, bp_lib, hero_wp)
        if args.scenario == "ambulance":
            spawn_ambulance(world, bp_lib, tm, hero_wp)

        print("\nScenario ready. Driving the hero is up to the framework. Ctrl-C to clean up.\n")

        ped_triggered = False
        period = 1.0 / POLL_HZ
        while True:
            hero_loc = hero.get_location()

            # Pedestrian crossing trigger (distance-based -> reproducible)
            if walker is not None and not ped_triggered:
                if hero_loc.distance(walker.get_location()) < PED_TRIGGER_DIST:
                    walker.apply_control(
                        carla.WalkerControl(direction=cross_dir, speed=PED_CROSS_SPEED)
                    )
                    ped_triggered = True
                    print("[pedestrian] crossing now")

            time.sleep(period)
    except KeyboardInterrupt:
        print("\nCleaning up...")
    finally:
        client.apply_batch([carla.command.DestroyActor(a) for a in spawned])
        print(f"Destroyed {len(spawned)} actors. Bye.")


if __name__ == "__main__":
    main()
