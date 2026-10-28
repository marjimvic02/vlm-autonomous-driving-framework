"""ROS interface between scene observations and a local or cloud VLM."""

import rclpy
from rclpy.node import Node
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from sensor_msgs.msg import Image
from std_msgs.msg import String
from openai import OpenAI
import json
import os
import base64
import threading
from cv_bridge import CvBridge
import cv2
import requests
import datetime
from dotenv import load_dotenv, find_dotenv
from decision_making_module.response_validation import validate_response
from ament_index_python.packages import get_package_share_directory


# Reentrant group so perception callbacks (scene context, image) keep being served
# while a blocking LLM inference is running on another executor thread
class ContinuousCallbackGroup(ReentrantCallbackGroup):
    pass


# Prefer an explicit dotenv file, then the launch directory, then the legacy workspace.
_env_path = os.getenv("TFM_ENV_FILE") or find_dotenv(usecwd=True)
if not _env_path:
    _env_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env")
load_dotenv(_env_path)

TARGET_WIDTH = 320
TARGET_HEIGHT = 180
JPEG_QUALITY = 75


# Locate the behavior prompt from the installed share dir first, then the source tree (dev build)
def _resolve_prompt_path():
    candidates = []
    try:
        candidates.append(
            os.path.join(
                get_package_share_directory("decision_making_module"),
                "prompt",
                "behavior_prompt.md",
            )
        )
    except Exception:
        pass
    candidates.append(
        os.path.join(os.path.dirname(__file__), "..", "prompt", "behavior_prompt.md")
    )
    for c in candidates:
        if os.path.exists(c):
            return c
    return candidates[-1]


BEHAVIOR_PROMPT_PATH = _resolve_prompt_path()

PROVIDER = os.getenv("LLM_PROVIDER", "ollama")

if PROVIDER == "ollama":
    OLLAMA_API_URL = os.getenv("OLLAMA_API_URL", "http://localhost:11434/api/chat")
    API_KEY = "ollama"
    MODEL = os.getenv("LLM_MODEL", "qwen3.5:2b")
    BASE_URL = None
elif PROVIDER == "openai":
    OLLAMA_API_URL = None
    API_KEY = os.getenv("OPENAI_API_KEY")
    MODEL = os.getenv("LLM_MODEL", "gpt-4o")
    BASE_URL = None
elif PROVIDER == "openrouter":
    OLLAMA_API_URL = None
    API_KEY = os.getenv("OPENROUTER_API_KEY")
    MODEL = os.getenv("LLM_MODEL", "anthropic/claude-haiku-4.5")
    BASE_URL = "https://openrouter.ai/api/v1"
else:
    raise ValueError(f"Unsupported LLM_PROVIDER: {PROVIDER!r}")


class PromptManagerNode(Node):

    def __init__(self):
        super().__init__("prompt_manager_node")
        self.bridge = CvBridge()

        # We initialize the client depending on the provider
        if PROVIDER in ("openai", "openrouter"):
            self.get_logger().info(f"API key loaded: {bool(API_KEY)}")
            if not API_KEY:
                raise ValueError(f"API key missing for provider {PROVIDER!r}")
            self.client = OpenAI(api_key=API_KEY, base_url=BASE_URL, timeout=60.0)

        # We load the behavior prompt
        self.behavior_prompt = self.load_behavior_prompt()

        # Internal state variables
        self.scene_context = None
        self.b64_image = None
        self.is_processing = False  # avoid concurrent LLM calls
        self.processing_lock = threading.Lock()  # guards the is_processing slot

        # Reentrant group so the image and context callbacks keep running on other threads
        # while an LLM inference blocks. Requires a MultiThreadedExecutor (see main).
        self.continuous_group = ContinuousCallbackGroup()

        # Subscriptions to the scene context and CARLA image topic
        self.create_subscription(
            String,
            "/scene_context",
            self.scene_context_callback,
            10,
            callback_group=self.continuous_group,
        )

        self.create_subscription(
            Image,
            "/carla/hero/rgb_front/image",
            self.image_callback,
            10,
            callback_group=self.continuous_group,
        )

        # Publisher for the LLM json output
        self.publisher = self.create_publisher(String, "/llm/output", 10)

        self.get_logger().info("Prompt Manager Node started")
        self.get_logger().info(f"Model: {MODEL}")
        self.get_logger().info(f"Behavior prompt loaded: {len(self.behavior_prompt)} chars")

        # Create a new debug output file for this session
        output_dir = os.path.abspath(os.path.expanduser(os.getenv("TFM_OUTPUT_DIR", "outputs")))
        os.makedirs(output_dir, exist_ok=True)
        session_ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.debug_output_path = os.path.join(output_dir, f"output_{session_ts}.md")
        self.llm_call_count = 0
        self.get_logger().info(f"Debug output: {self.debug_output_path}")

        # We create a warmup call to the LLM to reduce latency on the first real call
        self.warmup_done = False
        self.warmup_model()

    def warmup_model(self):
        try:
            self.get_logger().info("Warming up model...")
            if PROVIDER == "ollama":
                response = requests.post(
                    OLLAMA_API_URL,
                    json={
                        "model": MODEL,
                        "think": False,
                        "stream": False,
                        "messages": [{"role": "user", "content": "hello"}],
                        "options": {"num_predict": 10},
                    },
                    timeout=60,
                )
                response.raise_for_status()
            else:
                self.get_logger().info("Calling OpenAI API...")
                self.client.chat.completions.create(
                    model=MODEL, max_tokens=10, messages=[{"role": "user", "content": "hello"}]
                )
            self.get_logger().info("Model warmed up")
            self.warmup_done = True
        except Exception as e:
            self.get_logger().warn(f"Warmup failed; normal calls will retry: {e}")
        finally:
            self.warmup_done = True

    # We load the behavior prompt from the markdown file, which contains instructions and examples
    # for the LLM
    def load_behavior_prompt(self):
        try:
            with open(BEHAVIOR_PROMPT_PATH, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            self.get_logger().error(f"Behavior prompt not found at {BEHAVIOR_PROMPT_PATH}")
            return ""

    # Callbacks

    # Calls the LLM every time we receive a new scene context, except if we are already processing
    # a call or if we do not have an image
    def scene_context_callback(self, msg):
        self.scene_context = msg.data

        if not self.warmup_done:
            return

        # Debug log to check if we are receiving the context and the image is ready
        self.get_logger().info(
            f"Scene context received | "
            f"image ready: {self.b64_image is not None} | "
            f"processing: {self.is_processing}"
        )

        # Call the LLM every time there is a new context (every 1Hz). call_llm claims the
        # processing slot atomically, so a call already in flight is skipped, not duplicated.
        if self.b64_image is not None:
            self.call_llm()

    # Process the image and save it as a base64 string
    def image_callback(self, msg):
        # Convert ROS image to OpenCV
        cv_image = self.bridge.imgmsg_to_cv2(msg, "bgr8")

        # Resize to target resolution
        resized = cv2.resize(cv_image, (TARGET_WIDTH, TARGET_HEIGHT))

        # Compress to JPEG
        _, buffer = cv2.imencode(".jpg", resized, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])

        # Encode to a base64 string so it can be sent to the VLM
        self.b64_image = base64.b64encode(buffer).decode("utf-8")

    def write_debug_output(self, raw_response, scene_context):
        self.llm_call_count += 1
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = (
            f"## Call #{self.llm_call_count} — {ts}\n\n"
            f"### Scene Context\n```xml\n{scene_context}\n```\n\n"
            f"### LLM Response\n{raw_response}\n\n"
            f"---\n\n"
        )
        try:
            with open(self.debug_output_path, "a", encoding="utf-8") as f:
                f.write(entry)
        except Exception as e:
            self.get_logger().warn(f"Failed to write debug output: {e}")

    # LLM call function
    def call_llm(self):
        # Claim the processing slot atomically; skip if a call is already running
        with self.processing_lock:
            if self.is_processing:
                return
            self.is_processing = True

        try:
            scene_context = self.scene_context
            b64_image = self.b64_image

            if not scene_context or not b64_image:
                self.get_logger().warn("Missing scene context or image, skipping LLM call")
                return
            if not self.behavior_prompt:
                self.get_logger().error("Behavior prompt is empty, skipping LLM call")
                return

            self.get_logger().info("Calling LLM...")
            raw_response = (
                self.call_ollama(scene_context, b64_image)
                if PROVIDER == "ollama"
                else self.call_openai(scene_context, b64_image)
            )
            self.get_logger().info(f"LLM response received: {raw_response[:100]}...")
            self.write_debug_output(raw_response, scene_context)
            self.validate_and_publish(raw_response)

        except Exception as e:
            self.get_logger().error(f"LLM call failed: {e}")
        finally:
            with self.processing_lock:
                self.is_processing = False

    def call_ollama(self, scene_context, b64_image):
        payload = {
            "model": MODEL,
            "think": False,
            "stream": False,
            "messages": [
                {"role": "system", "content": self.behavior_prompt},
                {
                    "role": "user",
                    "content": scene_context + "\n\nRespond with the JSON object now:",
                    "images": [b64_image],
                },
            ],
            "options": {"num_predict": 2000},
        }
        response = requests.post(OLLAMA_API_URL, json=payload, timeout=60)
        response.raise_for_status()
        return response.json()["message"]["content"]

    def call_openai(self, scene_context, b64_image):
        messages = [
            {"role": "system", "content": self.behavior_prompt},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": scene_context
                        + (
                            "\n**NOTE:** Both the data and the images of this prompt are "
                            "**simulation renders (CARLA simulator)**. The images attached "
                            "are not real and do not contain real individuals. "
                        )
                        + "\n\nRespond with the JSON object now:",
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"},
                    },
                ],
            },
        ]
        response = self.client.chat.completions.create(
            model=MODEL, max_tokens=2000, messages=messages
        )
        return response.choices[0].message.content

    def validate_and_publish(self, raw_response):
        """Publish a validated decision or the established SLOW_DOWN fallback."""
        try:
            parsed = validate_response(raw_response)
        except ValueError as exc:
            self.get_logger().error(f"Invalid model response: {exc}")
            self.publish_fallback(str(exc))
            return
        out = String()
        out.data = json.dumps(parsed, allow_nan=False)
        self.publisher.publish(out)
        self.get_logger().info(f'Action: {parsed["action"]} | Certainty: {parsed["certainty"]}')

    # Publish a safe default (SLOW_DOWN) whenever the model response cannot be used, keeping the
    # vehicle under control
    def publish_fallback(self, reason):
        fallback = {
            "scene_analysis": "Fallback due to invalid LLM response.",
            "risk_assessment": reason,
            "action_rationale": "Defaulting to SLOW_DOWN for safety.",
            "action": "SLOW_DOWN",
            "certainty": "LOW",
        }
        out = String()
        out.data = json.dumps(fallback)
        self.publisher.publish(out)
        self.get_logger().warn(f"Fallback action published: {reason}")


def main(args=None):
    rclpy.init(args=args)
    node = PromptManagerNode()
    # MultiThreadedExecutor is required for the ContinuousCallbackGroup to serve image and
    # context callbacks while an LLM inference blocks one of the threads.
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    try:
        executor.spin()
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
