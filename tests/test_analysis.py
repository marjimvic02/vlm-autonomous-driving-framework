"""Check parsing and nested campaign resolution without private run data."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/analysis"))
from parse_runs import analyze_file  # noqa: E402
from make_thesis_tables import resolve  # noqa: E402


class AnalysisTests(unittest.TestCase):
    def test_calls_and_timestamps_produce_historical_metrics(self):
        data = """## Call #1 — 2026-06-14 12:00:00
### LLM Response
{"scene_analysis":"a","risk_assessment":"b","action_rationale":"c","action":"FOLLOW_LANE","certainty":"HIGH","target_speed":8}
---
## Call #2 — 2026-06-14 12:00:05
### LLM Response
{"scene_analysis":"a","risk_assessment":"b","action_rationale":"c","action":"REVERSE","certainty":"HIGH"}
---
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run.md"
            path.write_text(data)
            metrics, rows = analyze_file(path)
        self.assertEqual(metrics["total"], 2)
        self.assertEqual(metrics["fallback"], 1)
        self.assertEqual(metrics["invalid_action"], 1)
        self.assertEqual(metrics["deltas"], [5.0])
        self.assertFalse(rows[0]["fallback"])
        self.assertTrue(rows[1]["fallback"])

    def test_nested_obstacle_run_two_and_freerun_log_are_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            obstacle = Path(tmp) / "qwen_2B_obs/qwen_2B_obs_2.md"
            obstacle.parent.mkdir()
            obstacle.touch()
            self.assertEqual(resolve(tmp, ["qwen_2B_{sc}"], "obs_2", ".md"), str(obstacle))
            log = Path(tmp) / "qwen_2B_freerun/2B_freerun.log"
            log.parent.mkdir()
            log.touch()
            self.assertEqual(
                resolve(tmp, ["qwen_2B_{sc}", "2B_{sc}"], "freerun", ".log"), str(log)
            )
            self.assertIsNone(resolve(tmp, ["haiku_{sc}"], "traffic", ".md"))
