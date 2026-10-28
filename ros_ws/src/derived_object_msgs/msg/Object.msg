# Detection level constants
uint8 OBJECT_DETECTED=0
uint8 OBJECT_TRACKED=1

# Classification constants
uint8 CLASSIFICATION_UNKNOWN=0
uint8 CLASSIFICATION_UNKNOWN_SMALL=1
uint8 CLASSIFICATION_UNKNOWN_MEDIUM=2
uint8 CLASSIFICATION_UNKNOWN_BIG=3
uint8 CLASSIFICATION_PEDESTRIAN=4
uint8 CLASSIFICATION_BIKE=5
uint8 CLASSIFICATION_CAR=6
uint8 CLASSIFICATION_TRUCK=7
uint8 CLASSIFICATION_MOTORCYCLE=8
uint8 CLASSIFICATION_OTHER_VEHICLE=9
uint8 CLASSIFICATION_BARRIER=10
uint8 CLASSIFICATION_SIGN=11

std_msgs/Header header
uint8 id
uint8 detection_level
bool is_static
geometry_msgs/PoseWithCovariance pose
geometry_msgs/TwistWithCovariance twist
geometry_msgs/AccelWithCovariance accel
shape_msgs/SolidPrimitive shape
uint8 object_classified
uint8 classification
float32 classification_certainty
uint32 classification_age
