"""Verify request lifecycle behavior using the actual node methods."""

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ros_ws/src/decision_making_module"))


def load_prompt_manager():
    names = [
        "rclpy",
        "rclpy.node",
        "rclpy.callback_groups",
        "rclpy.executors",
        "sensor_msgs",
        "sensor_msgs.msg",
        "std_msgs",
        "std_msgs.msg",
        "openai",
        "cv_bridge",
        "cv2",
        "requests",
        "dotenv",
        "ament_index_python",
        "ament_index_python.packages",
    ]
    stubs = {name: ModuleType(name) for name in names}
    stubs["rclpy.node"].Node = object
    stubs["rclpy.callback_groups"].ReentrantCallbackGroup = object
    stubs["rclpy.executors"].MultiThreadedExecutor = Mock()
    stubs["sensor_msgs.msg"].Image = object
    stubs["std_msgs.msg"].String = SimpleNamespace
    stubs["openai"].OpenAI = Mock()
    stubs["cv_bridge"].CvBridge = Mock()
    stubs["requests"].post = Mock()
    stubs["dotenv"].load_dotenv = Mock()
    stubs["dotenv"].find_dotenv = Mock(return_value="")
    stubs["ament_index_python.packages"].get_package_share_directory = Mock(return_value="/tmp")
    path = ROOT / "ros_ws/src/decision_making_module/decision_making_module/prompt_manager.py"
    spec = importlib.util.spec_from_file_location("prompt_manager_under_test", path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs), patch.dict(os.environ, {"LLM_PROVIDER": "ollama"}):
        spec.loader.exec_module(module)
    return module


prompt = load_prompt_manager()


class PromptLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.node = prompt.PromptManagerNode.__new__(prompt.PromptManagerNode)
        self.node.get_logger = Mock(return_value=Mock())
        self.node.warmup_done = False
        self.node.publisher = Mock()

    def test_failed_warmup_does_not_disable_later_requests(self):
        with patch.object(prompt.requests, "post", side_effect=OSError("service unavailable")):
            self.node.warmup_model()
        self.assertTrue(self.node.warmup_done)

    def test_successful_warmup_checks_http_status(self):
        result = Mock()
        with patch.object(prompt.requests, "post", return_value=result):
            self.node.warmup_model()
        result.raise_for_status.assert_called_once()
        self.assertTrue(self.node.warmup_done)

    def test_invalid_response_publishes_fallback(self):
        self.node.validate_and_publish('{"action": []}')
        import json

        data = json.loads(self.node.publisher.publish.call_args.args[0].data)
        self.assertEqual(data["action"], "SLOW_DOWN")
        self.assertEqual(data["certainty"], "LOW")

    def test_ollama_http_failure_propagates_to_call_handler(self):
        self.node.behavior_prompt = "test prompt"
        result = Mock()
        result.raise_for_status.side_effect = RuntimeError("HTTP failure")
        with patch.object(prompt.requests, "post", return_value=result):
            with self.assertRaises(RuntimeError):
                self.node.call_ollama("context", "image")
        result.json.assert_not_called()
