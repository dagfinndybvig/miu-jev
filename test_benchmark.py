import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from app import DecisionError, legal_moves
import benchmark
import lambda_calc
from benchmark import (
    generate_cases, generate_lambda_cases, novel_lambda_terms, run_trial,
    summarize, target_distance,
)


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

    def test_lambda_cases_are_reproducible_with_legal_normal_order_witnesses(self):
        first = generate_lambda_cases(123, 5)
        self.assertEqual(first, generate_lambda_cases(123, 5))
        cases, reference = first
        self.assertEqual(len(cases), 6)
        self.assertEqual({case["kind"] for case in cases}, {"reachable", "trap", "growth", "impossible"})
        self.assertEqual(cases[-1]["term"], benchmark.OMEGA)
        for case in cases:
            if case["kind"] == "impossible":
                self.assertIsNone(case["reference_steps"])
                self.assertIn("no normal form", case["proof"])
                continue
            current = lambda_calc.describe(case["term"])["current"]
            for step in case["witness"]:
                self.assertEqual(step["current"], current)
                self.assertIn(step["move"], lambda_calc.describe(current)["moves"])
                current = step["move"]["result"]
            self.assertTrue(lambda_calc.describe(current)["solved"])
            self.assertEqual(current, case["goal"])
            self.assertEqual(len(case["witness"]), case["reference_steps"])
        self.assertEqual(
            reference["scope"],
            "Normal-order reference paths, which reach a normal form whenever one exists.",
        )

    def test_lambda_traps_need_strategy_and_omega_never_normalizes(self):
        for term, kind in benchmark.lambda_terms():
            if kind != "trap":
                continue
            state = lambda_calc.describe(term)
            self.assertGreaterEqual(state["redexes"], 2)
            _, normal_form = lambda_calc.normal_order_witness(term, max_steps=20)
            self.assertEqual(normal_form, "λy.y")
        self.assertFalse(lambda_calc.describe(benchmark.OMEGA)["solved"])

    def test_lambda_heuristic_baseline_reaches_normal_forms_within_budget(self):
        cases, _ = generate_lambda_cases(123, 5)
        for case in cases:
            result = run_trial(case, "heuristic", 1, 12, 512, 10, system="lambda")
            if case["kind"] == "impossible":
                self.assertFalse(result["success"])
            else:
                self.assertTrue(result["success"], (case["term"], result["outcome"]))
                self.assertLessEqual(result["steps"], case["reference_steps"] + 2)
        with self.assertRaisesRegex(ValueError, "explicit provider"):
            run_trial(cases[0], "model", 1, 5, 512, 5, system="lambda")

    def test_lambda_run_trial_threads_system_and_hints_to_the_provider(self):
        case = generate_lambda_cases(123, 5)[0][0]
        def fake_choose(provider, model, policy, current, goal, history, moves,
                        max_length, system, hints):
            return {"move": moves[0], "rounds": [], "provider_calls": 0, "override_count": 0}

        with patch("benchmark.choose_move", side_effect=fake_choose) as choose:
            result = run_trial(case, "model", 1, 3, 512, 5, "ollama", "nimble",
                               system="lambda", hints=False)
        self.assertEqual(result["system"], "lambda")
        self.assertFalse(result["hints"])
        self.assertEqual(choose.call_args.kwargs["system"], "lambda")
        self.assertEqual(choose.call_args.kwargs["hints"], False)

    def test_novel_terms_stay_ahead_of_the_curriculum(self):
        first = novel_lambda_terms(123, 4)
        self.assertEqual(first, novel_lambda_terms(123, 4))
        curated = {term for term, _ in benchmark.lambda_terms()}
        terms = [term for term, _ in first]
        self.assertEqual([kind for _, kind in first], ["novel"] * 4)
        self.assertEqual(len(terms), len(set(terms)))
        for term in terms:
            self.assertNotIn(term, curated)
            path, normal_form = lambda_calc.normal_order_witness(term, max_steps=100)
            self.assertIsNotNone(normal_form)
            self.assertGreaterEqual(len(path), benchmark.NOVEL_MIN_REFERENCE_STEPS)
            self.assertLessEqual(len(path), benchmark.NOVEL_MAX_REFERENCE_STEPS)
            current = lambda_calc.describe(term)["current"]
            for step in path:
                self.assertEqual(step["current"], current)
                self.assertIn(step["move"], lambda_calc.describe(current)["moves"])
                current = step["move"]["result"]
            self.assertEqual(current, normal_form)

    def test_lambda_cases_mix_novel_and_curated_terms(self):
        cases, reference = generate_lambda_cases(123, 5, novel=2)
        self.assertEqual(len(cases), 6)
        self.assertEqual(
            sorted(case["kind"] for case in cases),
            ["growth", "impossible", "novel", "novel", "reachable", "trap"],
        )
        self.assertEqual(reference["pool_novel"], 2)
        for case in cases:
            if case["kind"] == "impossible":
                continue
            current = lambda_calc.describe(case["term"])["current"]
            for step in case["witness"]:
                self.assertEqual(step["current"], current)
                self.assertIn(step["move"], lambda_calc.describe(current)["moves"])
                current = step["move"]["result"]
            self.assertEqual(current, case["goal"])
        with self.assertRaisesRegex(ValueError, "reachable slots"):
            generate_lambda_cases(123, 5, novel=4)

    def test_cli_runs_keyless_lambda_comparison_with_novel_terms(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "results.json"
            process = subprocess.run(
                [sys.executable, str(Path(__file__).with_name("benchmark.py")),
                 "--system", "lambda", "--targets", "3", "--repeats", "1",
                 "--novel-terms", "1", "--output", str(output)],
                capture_output=True, text=True, timeout=60, check=True,
            )
            report = json.loads(output.read_text(encoding="utf-8"))
            rejected = subprocess.run(
                [sys.executable, str(Path(__file__).with_name("benchmark.py")),
                 "--novel-terms", "1", "--output", str(output)],
                capture_output=True, text=True, timeout=60,
            )
        self.assertIn("Results saved", process.stdout)
        self.assertEqual(report["configuration"]["novel_terms"], 1)
        self.assertEqual(report["reference"]["pool_novel"], 1)
        self.assertEqual(len(report["trials"]), 8)
        self.assertTrue(any(row["kind"] == "novel" for row in report["trials"]))
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("--novel-terms", rejected.stderr)

    def test_menu_order_arm_is_reproducible_and_audited(self):
        def run_with(menu_order):
            captured = []

            def fake_choose(provider, model, policy, current, goal, history, moves,
                            max_length, system="miu", hints=True):
                captured.append([move["id"] for move in moves])
                return {"move": moves[0], "rounds": [], "provider_calls": 0,
                        "override_count": 0}

            case = {"goal": "MU", "kind": "impossible", "reference_steps": None}
            with patch("benchmark.choose_move", side_effect=fake_choose):
                trial = run_trial(case, "model", 5, 2, 32, 4, "ollama", "nimble",
                                  menu_order=menu_order)
            return trial, captured

        menu_ids = [move["id"] for move in legal_moves("MI")]
        fixed, fixed_calls = run_with("fixed")
        reversed_trial, reversed_calls = run_with("reversed")
        shuffled, shuffled_calls = run_with("shuffled")
        shuffled_again, shuffled_again_calls = run_with("shuffled")

        self.assertEqual(fixed_calls[0], menu_ids)
        self.assertEqual(reversed_calls[0], list(reversed(menu_ids)))
        self.assertEqual(shuffled_calls, shuffled_again_calls)
        self.assertEqual(set(shuffled_calls[0]), set(menu_ids))
        self.assertEqual(fixed["menu_order"], "fixed")
        self.assertEqual(fixed["evidence"][0]["presented"], menu_ids)
        self.assertEqual(reversed_trial["evidence"][0]["presented"], list(reversed(menu_ids)))
        self.assertEqual(shuffled["evidence"][0]["presented"], shuffled_calls[0])
        rows = summarize([fixed, reversed_trial, shuffled])
        self.assertEqual(len(rows), 3)
        self.assertEqual({row["menu_order"] for row in rows}, {"fixed", "reversed", "shuffled"})

    def test_unknown_menu_order_is_rejected(self):
        case = {"goal": "MU", "kind": "impossible", "reference_steps": None}
        with self.assertRaisesRegex(ValueError, "Unknown menu order"):
            run_trial(case, "model", 5, 2, 32, 4, "ollama", "nimble", menu_order="rotated")

    def test_wrong_hint_arm_annotates_only_diverging_self_loops(self):
        term, _ = next(pair for pair in benchmark.lambda_terms() if pair[1] == "trap")
        case = {
            "term": term, "goal": "λy.y", "kind": "trap",
            "reference_steps": 2, "witness": [],
        }
        captured = []

        def fake_choose(provider, model, policy, current, goal, history, moves,
                        max_length, system="miu", hints=True):
            captured.append(moves)
            return {"move": moves[0], "rounds": [], "provider_calls": 0,
                    "override_count": 0}

        with patch("benchmark.choose_move", side_effect=fake_choose):
            trial = run_trial(case, "model", 1, 1, 512, 4, "ollama", "nimble",
                              system="lambda", wrong_hint=True)

        self.assertTrue(trial["wrong_hint"])
        entry = trial["evidence"][0]
        current = entry["current"]
        annotated = [move for move in captured[0] if move["result"] == current]
        self.assertEqual(len(annotated), 1)
        self.assertTrue(annotated[0]["label"].endswith("· recommended"))
        self.assertEqual(annotated[0]["detail"], benchmark.WRONG_HINT_RECOMMENDATION)
        self.assertEqual(entry["wrong_hint"], [annotated[0]["id"]])
        others = [move for move in captured[0] if move["result"] != current]
        self.assertEqual(len(others), 1)
        self.assertNotIn("recommended", others[0]["label"])
        self.assertNotIn("recommend", others[0]["detail"])

    def test_wrong_hint_is_a_lambda_only_flag(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "results.json"
            rejected = subprocess.run(
                [sys.executable, str(Path(__file__).with_name("benchmark.py")),
                 "--wrong-hint", "--output", str(output)],
                capture_output=True, text=True, timeout=60,
            )
            process = subprocess.run(
                [sys.executable, str(Path(__file__).with_name("benchmark.py")),
                 "--system", "lambda", "--targets", "3", "--repeats", "1",
                 "--wrong-hint", "--output", str(output)],
                capture_output=True, text=True, timeout=60, check=True,
            )
            report = json.loads(output.read_text(encoding="utf-8"))
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("--wrong-hint", rejected.stderr)
        self.assertTrue(report["configuration"]["wrong_hint"])
        self.assertEqual(
            {row["strategy"] for row in report["trials"]}, {"random", "heuristic"},
        )

    def test_cli_records_menu_order_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "results.json"
            subprocess.run(
                [sys.executable, str(Path(__file__).with_name("benchmark.py")),
                 "--targets", "2", "--repeats", "1", "--menu-order", "shuffled",
                 "--output", str(output)],
                capture_output=True, text=True, timeout=20, check=True,
            )
            report = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(report["configuration"]["menu_order"], "shuffled")
        self.assertTrue(all(row["menu_order"] == "fixed" for row in report["trials"]))
        self.assertTrue(all(row["menu_order"] == "fixed" for row in report["summary"]))

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


    def test_cli_produces_complete_keyless_lambda_comparison(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "results.json"
            process = subprocess.run(
                [sys.executable, str(Path(__file__).with_name("benchmark.py")),
                 "--system", "lambda", "--targets", "3", "--repeats", "1",
                 "--output", str(output)],
                capture_output=True, text=True, timeout=60, check=True,
            )
            report = json.loads(output.read_text(encoding="utf-8"))
        self.assertIn("Results saved", process.stdout)
        self.assertTrue(report["completed"])
        self.assertEqual(report["system"], "lambda")
        self.assertIn("lambda_calc.py", report["source_sha256"])
        self.assertEqual(report["configuration"]["max_length"], 512)
        self.assertEqual(len(report["trials"]), 8)
        self.assertTrue(all(row["provider_calls"] == 0 for row in report["trials"]))
        self.assertEqual(report["summary"], summarize(report["trials"]))


if __name__ == "__main__":
    unittest.main()
