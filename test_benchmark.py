import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from app import DecisionError, legal_moves
from benchmark import generate_cases, run_trial, summarize, target_distance


class BenchmarkTests(unittest.TestCase):
    def test_generated_targets_are_reproducible_with_legal_bfs_witnesses(self):
        first = generate_cases(123, 4, 32, 7, 10000)
        self.assertEqual(first, generate_cases(123, 4, 32, 7, 10000))
        cases, reference = first
        self.assertFalse(reference["truncated"])
        self.assertGreater(max(case["reference_steps"] or 0 for case in cases), 3)
        self.assertEqual(len({case["goal"] for case in cases}), 5)
        for case in cases:
            if case["kind"] == "impossible":
                self.assertEqual(case["goal"], "MU")
                self.assertIsNone(case["reference_steps"])
                continue
            current = "MI"
            for step in case["witness"]:
                self.assertEqual(step["current"], current)
                self.assertIn(step["move"], legal_moves(current))
                current = step["move"]["result"]
                self.assertLessEqual(len(current), 32)
            self.assertEqual(current, case["goal"])
            self.assertEqual(len(case["witness"]), case["reference_steps"])

    def test_insufficient_bfs_budget_is_explicit(self):
        with self.assertRaisesRegex(ValueError, "too few targets"):
            generate_cases(1, 4, 8, 3, 2)

    @patch("benchmark.choose_move")
    def test_baselines_are_keyless_and_apply_identical_execution_limits(self, choose):
        cases, _ = generate_cases(123, 4, 16, 6, 1000)
        for strategy in ("random", "heuristic"):
            for case in cases:
                result = run_trial(case, strategy, 7, 6, 16, 3)
                self.assertLessEqual(result["steps"], 6)
                self.assertEqual(len(result["history"]), len(set(result["history"])))
                self.assertTrue(all(len(value) <= 16 for value in result["history"]))
                self.assertEqual(result["provider_calls"], 0)
                for before, after in zip(result["history"], result["history"][1:]):
                    self.assertIn(after, [move["result"] for move in legal_moves(before)])
        choose.assert_not_called()

    def test_random_seed_reproduces_choices(self):
        case = {"goal": "MU", "kind": "impossible", "reference_steps": None}
        first = run_trial(case, "random", 42, 10, 32, 4)
        second = run_trial(case, "random", 42, 10, 32, 4)
        self.assertEqual(first["history"], second["history"])
        self.assertEqual(first["evidence"], second["evidence"])

    def test_heuristic_baseline_matches_documented_example(self):
        case = {"goal": "MUI", "kind": "reachable", "reference_steps": 3}
        result = run_trial(case, "heuristic", 1, 10, 32, 4)
        self.assertEqual(result["outcome"], "found")
        self.assertEqual(result["history"], ["MI", "MII", "MIIII", "MUI"])

    @patch("app.require_compatible_ollama")
    def test_provider_measurements_count_real_groups_and_overrides(self, _compatible):
        response = io.BytesIO(json.dumps({"answers": {"next_move": {
            "choice": "A", "probabilities": {"A": 1, "B": 0},
        }}}).encode())
        case = {"goal": "MII", "kind": "reachable", "reference_steps": 1}
        with patch("app.urllib.request.urlopen", return_value=response):
            result = run_trial(case, "guided", 1, 3, 32, 4, "ollama", "nimble")
        self.assertEqual(result["outcome"], "found")
        self.assertEqual(result["provider_calls"], 1)
        self.assertEqual(result["evaluated_groups"], 1)
        self.assertEqual(result["override_count"], 1)
        self.assertTrue(result["evidence"][0]["applied"])
        summary = summarize([result])[0]
        self.assertEqual(summary["override_rate"], 1)
        self.assertEqual(summary["mean_excess_steps_over_bounded_bfs"], 0)

    def test_provider_failures_remain_failures_in_summary(self):
        case = {"goal": "MUI", "kind": "reachable", "reference_steps": 3}
        trace = {"provider_calls": 1, "override_count": 0, "rounds": []}
        with patch("benchmark.choose_move", side_effect=DecisionError("Provider failed", trace)):
            result = run_trial(case, "model", 1, 10, 32, 4, "ollama", "nimble")
        self.assertEqual(result["outcome"], "provider_error")
        self.assertEqual(result["provider_calls"], 1)
        self.assertEqual(summarize([result])[0]["success_rate"], 0)

    def test_impossible_trials_are_not_in_reachable_success_denominator(self):
        reachable = run_trial(
            {"goal": "MUI", "kind": "reachable", "reference_steps": 3},
            "heuristic", 1, 10, 32, 4,
        )
        impossible = run_trial(
            {"goal": "MU", "kind": "impossible", "reference_steps": None},
            "heuristic", 1, 10, 32, 4,
        )
        summaries = summarize([reachable, impossible])
        self.assertEqual(summaries[0]["success_rate"], 1)
        self.assertIsNone(summaries[1]["success_rate"])
        self.assertIsNone(summaries[1]["override_rate"])

    def test_distance_matches_browser_metric_examples(self):
        self.assertEqual(target_distance("MI", "MUI"), 1)
        self.assertEqual(target_distance("MIIII", "MUI"), 3)
        self.assertEqual(target_distance("MU", "MU"), 0)

    def test_cli_produces_complete_keyless_comparison(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "results.json"
            process = subprocess.run(
                [sys.executable, str(Path(__file__).with_name("benchmark.py")),
                 "--targets", "2", "--repeats", "1", "--output", str(output)],
                capture_output=True, text=True, timeout=20, check=True,
            )
            report = json.loads(output.read_text(encoding="utf-8"))
        self.assertIn("Results saved", process.stdout)
        self.assertTrue(report["completed"])
        self.assertEqual(len(report["trials"]), 6)
        self.assertEqual(report["configuration"]["providers"], [])
        self.assertTrue(all(row["provider_calls"] == 0 for row in report["trials"]))
        self.assertEqual(report["summary"], summarize(report["trials"]))


if __name__ == "__main__":
    unittest.main()
