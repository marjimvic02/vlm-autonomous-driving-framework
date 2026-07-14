import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32, String
from sensor_msgs.msg import Imu
from nav_msgs.msg import Odometry
from transforms3d.euler import quat2euler
from derived_object_msgs.msg import ObjectArray
from carla_msgs.msg import CarlaTrafficLightStatusList, CarlaTrafficLightInfoList
from rclpy.qos import QoSProfile, DurabilityPolicy
from math import sqrt, degrees, atan2
import time

from perception_module.geometry_utils import (
    angle_to_direction, normalize_angle_deg, faces_ego)
from perception_module.carla_maps import STATE_DICT, CLASSIFICATION_MAP

DISTANCE_THRESHOLD = 50.0 # In meters. Max distance to consider an object relevant for the scene context
EGO_SELF_RADIUS = 0.5 # In meters. Objects overlapping the ego center are the ego itself, not obstacles
MAX_OBJECTS = 5 # Max number of nearby objects to include in the scene context, sorted by distance
TL_THRESHOLD = 80 # In meters. Max distance to consider a TL relevant for the scene context
TL_FACING_TOLERANCE = 50.0  # In degrees. A TL governs the ego if its heading is within this of anti-parallel

DECEL = 3.0          # m/s² must match RAMP_RATE in the dispatcher
SAFETY_MARGIN = 1.5  # multiplier added on top of the theoretical braking distance


class SceneContextNode(Node):

    def __init__(self):
        super().__init__('scene_context_node')

        # Internal states (Synchronous)
        self.speed = 0.0
        self.wz = 0.0
        self.ax = 0.0
        self.ay = 0.0
        self.ego_x = 0.0
        self.ego_y = 0.0
        self.yaw = 0.0
        self.ego_yaw = 0.0

        # Internal states (Asynchronous)
        self.tl_info = {}
        self.tl_status = []
        self.tl_last_updated = None
        self.objects = []

        # QoS for the latched traffic light topics (transient local)
        qos_latched = QoSProfile(
            depth=1,
            durability=DurabilityPolicy.TRANSIENT_LOCAL
        )

        # Sensors subscriptions (Synchronous)
        # Speedometer
        self.create_subscription(
            Float32,
            '/carla/hero/speedometer',
            self.speed_callback,
            10
        )

        # IMU (Inertial Measurement Unit)
        self.create_subscription(
            Imu,
            '/carla/hero/imu',
            self.imu_callback,
            10
        )        

        # Odometry
        self.create_subscription(
            Odometry,
            '/carla/hero/odometry',
            self.odom_callback,
            10
        )

        # Surrounding objects information
        self.create_subscription(
            ObjectArray,
            '/carla/hero/objects',
            self.objects_callback,
            10
        )

        #  Sensors subscriptions (Asynchronous)
        self.create_subscription(
            CarlaTrafficLightInfoList,
            '/carla/traffic_lights/info',
            self.tl_info_callback,
            qos_latched
        )

        self.create_subscription(
            CarlaTrafficLightStatusList,
            '/carla/traffic_lights/status',
            self.tl_status_callback,
            qos_latched
        )

        # Publishers
        self.publisher = self.create_publisher(
            String,
            '/scene_context',
            10
        )

        # Timer at 1Hz that coordinates the xml update with aligned information from all the sensors
        self.create_timer(
            1.0,
            self.timer_callback
        )

        self.get_logger().info('Scene context node Initialized')

    # Callback definitions (Synchronous)
    def speed_callback(self, msg):
        self.speed = msg.data

    def imu_callback(self, msg):
        # Angular velocity (Gyroscope)
        self.wz = msg.angular_velocity.z
        # Linear acceleration (Accelerometer)
        self.ax = msg.linear_acceleration.x
        self.ay = msg.linear_acceleration.y

    def odom_callback(self, msg):
        self.ego_x = msg.pose.pose.position.x
        self.ego_y = msg.pose.pose.position.y

        # Orientation in quaternion format
        q = msg.pose.pose.orientation

        # Transform to Roll Pitch Yaw (Better interpretation)
        _, _, yaw = quat2euler([q.w, q.x, q.y, q.z])
        self.yaw = degrees(yaw)
        self.ego_yaw = yaw  # In radians for angle-related calculations     

    # Build the list of nearby objects, each with its distance, speed and direction relative to the ego vehicle
    def objects_callback(self, msg):
        nearby = []

        for obj in msg.objects:
            ox = obj.pose.pose.position.x
            oy = obj.pose.pose.position.y
            distance = sqrt((ox - self.ego_x)**2 + (oy - self.ego_y)**2)

            # Discard objects overlapping the ego center (the ego itself)
            if distance < EGO_SELF_RADIUS:
                continue

            if distance < DISTANCE_THRESHOLD:
                    obj_speed = sqrt(
                        obj.twist.twist.linear.x**2 +
                        obj.twist.twist.linear.y**2)

                    # Absolute angle towards the object
                    angle_to_obj = atan2(oy - self.ego_y, ox - self.ego_x)

                    # Relative angle with respect to the ego vehicle, normalized to (-180, 180]
                    relative_angle = normalize_angle_deg(degrees(angle_to_obj - self.ego_yaw))

                    direction = angle_to_direction(relative_angle)

                    nearby.append({
                        'id': obj.id,
                        'class': CLASSIFICATION_MAP.get(obj.classification, 'UNKNOWN'),
                        'distance': round(distance, 1),
                        'speed': round(obj_speed, 2),
                        'direction': direction,
                        'relative_angle': round(relative_angle, 1)
                    })

        nearby.sort(key=lambda x: x['distance'])
        self.objects = nearby[:MAX_OBJECTS]

    # Callback definitions (Asynchronous)
    def tl_info_callback(self, msg):
        for tl in msg.traffic_lights:
            self.tl_info[tl.id] = (
                tl.transform.position.x,
                tl.transform.position.y,
                tl.transform.orientation)

    def tl_status_callback(self, msg):
        self.tl_status = msg.traffic_lights
        self.tl_last_updated = time.time()

    def get_nearby_traffic_lights(self):
        if not self.tl_info or not self.tl_status:
            return []

        # Join the two topics by id: status gives the current state (dynamic), info gives the position
        # and orientation (static), and we need both to place and evaluate each traffic light
        nearby = []
        info_by_id = {tl.id: self.tl_info[tl.id]
                      for tl in self.tl_status if tl.id in self.tl_info}

        for tl in self.tl_status:
            if tl.id not in info_by_id:
                continue
            px, py, q = info_by_id[tl.id]
            distance = sqrt((px - self.ego_x)**2 + (py - self.ego_y)**2)

            if distance < TL_THRESHOLD:
                angle_to_tl = atan2(py - self.ego_y, px - self.ego_x)
                relative_angle = normalize_angle_deg(degrees(angle_to_tl - self.ego_yaw))
                direction = angle_to_direction(relative_angle)

                # Discard TLs that are BEHIND the ego vehicle to reduce the noise inside the context
                if "BEHIND" in direction:
                    self.get_logger().debug(
                        f'TL {tl.id} ignored (behind ego): direction={direction}')
                    continue

                # Keep only the lights that face the ego vehicle (anti-parallel filter)
                _, _, tl_yaw = quat2euler([q.w, q.x, q.y, q.z])
                if not faces_ego(tl_yaw, self.ego_yaw, TL_FACING_TOLERANCE):
                    self.get_logger().debug(
                        f'TL {tl.id} ignored (not facing ego)')
                    continue

                nearby.append({
                    'id': tl.id,
                    'state': STATE_DICT.get(tl.state, 'UNKNOWN'),
                    'distance': round(distance, 1),
                    'direction': direction
                })



        nearby.sort(key=lambda x: x['distance'])
        return nearby 

    # xml formatter
    def build_xml(self):
        if self.tl_last_updated is not None:
            tl_age = round(time.time() - self.tl_last_updated, 1)
        else:
            tl_age = 'unknown'

        nearby_tls = self.get_nearby_traffic_lights()

        # Kinematic braking distance (v^2 / 2a) with a safety margin, so the VLM knows how much room it needs to stop
        braking_dist = round((self.speed ** 2) / (2 * DECEL) * SAFETY_MARGIN, 1)

        xml = '<self_data>\n'
        xml += f'  <speed>{self.speed:.2f}</speed>\n'
        xml += f'  <braking_distance>{braking_dist}</braking_distance>\n'
        xml += f'  <yaw>{self.yaw:.2f}</yaw>\n'
        xml += f'  <acceleration>\n'
        xml += f'    <x>{self.ax:.3f}</x>\n'
        xml += f'    <y>{self.ay:.3f}</y>\n'
        xml += f'  </acceleration>\n'
        xml += f'  <angular_velocity>\n'
        xml += f'    <z>{self.wz:.3f}</z>\n'
        xml += f'  </angular_velocity>\n'
        xml += '</self_data>\n'

        xml += '<surroundings_data>\n'

        xml += f'  <traffic_lights last_updated="{tl_age}s">\n'
        for tl in nearby_tls:
            xml += '    <traffic_light>\n'
            xml += f'      <id>{tl["id"]}</id>\n'
            xml += f'      <state>{tl["state"]}</state>\n'
            xml += f'      <distance>{tl["distance"]}</distance>\n'
            xml += f'      <direction>{tl["direction"]}</direction>\n'
            xml += '    </traffic_light>\n'
        xml += '  </traffic_lights>\n'

        xml += '  <nearby_objects>\n'
        for obj in self.objects:
            xml += '    <object>\n'
            xml += f'      <id>{obj["id"]}</id>\n'
            xml += f'      <class>{obj["class"]}</class>\n'
            xml += f'      <distance>{obj["distance"]}</distance>\n'
            xml += f'      <speed>{obj["speed"]}</speed>\n'
            xml += f'      <direction>{obj["direction"]}</direction>\n'
            xml += f'      <relative_angle>{obj["relative_angle"]}</relative_angle>\n'
            xml += '    </object>\n'
        xml += '  </nearby_objects>\n'

        xml += '</surroundings_data>'
        return xml        

    # Timer callback
    def timer_callback(self):
        xml = self.build_xml()
        out = String()
        out.data = xml
        self.publisher.publish(out)
        self.get_logger().info('Scene context published')
        self.get_logger().debug(f'\n{xml}')


def main(args=None):
    rclpy.init(args=args)
    node = SceneContextNode()
    rclpy.spin(node)
    # Destroy the node explicitly
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()