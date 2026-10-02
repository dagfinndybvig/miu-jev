from fractions import Fraction
import io
import json
import random
import unittest
from unittest.mock import patch

import algebra
from app import choose_move


class AlgebraParserTests(unittest.TestCase):
    def test_supported_notation_normalizes_exactly(self):
        for text, expected in (
            ("2(x + 3)=14", "2 * (x + 3) = 14"),
            ("3x+2=x+10", "3 * x + 2 = x + 10"),
            ("x = (3+1)/6", "x = 2/3"),
            ("x/(-2)=-3/4", "x / -2 = -3/4"),
            ("-(x-2)=3", "-1 * (x - 2) = 3"),
        ):
            with self.subTest(text=text):
                equation = algebra.parse_equation(text)
                self.assertEqual(algebra.format_equation(equation), expected)
                self.assertEqual(algebra.parse_equation(expected), equation)

    def test_invalid_and_unsupported_equations_are_rejected(self):
        for text in (
            "", None, 12, [], "MI", "x", "x=1=2", "x + = 2",
            "x^2=4", "x*x=4", "(x+1)*(x-1)=0", "x/(x+1)=2",
            "x/(x-x+1)=2", "x/0=2", "1/0=x", "x/(1-1)=3",
            "x+y=2", "sin(x)=1", "x=0.5", "2 3=x", "(x+1=2",
            "__import__('os').system('echo invalid')=x", "x;print(1)=2",
        ):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    algebra.parse_equation(text)

    def test_representation_limits_are_explicit(self):
        for text in (
            " " * algebra.MAX_LENGTH + "x=1",
            "(" * 30 + "x" + ")" * 30 + "=1",
            "x+" * 70 + "x=1",
            "x=" + "9" * 40,
            "x=" + str(2**100) + "*" + str(2**100),
        ):
            with self.subTest(text=text[:40]):
                with self.assertRaises(algebra.AlgebraLimitError):
                    algebra.parse_equation(text)


class AlgebraRewriteTests(unittest.TestCase):
    def test_default_menu_offers_distribution_and_division(self):
        state = algebra.describe(algebra.DEFAULT_EQUATION)
        self.assertFalse(state["solved"])
        self.assertIn((2, "2 * x + 6 = 14"), [(m["rule"], m["result"]) for m in state["moves"]])
        self.assertIn((5, "x + 3 = 7"), [(m["rule"], m["result"]) for m in state["moves"]])
        self.assertEqual(len({m["id"] for m in state["moves"]}), len(state["moves"]))
        self.assertEqual(len(state["rules"]), 7)

    def test_guided_default_is_a_two_step_derivation(self):
        state = algebra.describe(algebra.DEFAULT_EQUATION)
        history = [state["current"]]
        for _ in range(2):
            explanation = {}
            chosen = algebra.select_move(
                "guided", state["current"], algebra.GOAL, history, state["moves"],
                state["moves"][0], {state["moves"][0]["id"]: 1}, 64, explanation,
            )
            self.assertIn("reason", explanation)
            history.append(chosen["result"])
            state = algebra.describe(chosen["result"])
        self.assertEqual(history, ["2 * (x + 3) = 14", "x + 3 = 7", "x = 4"])
        self.assertTrue(state["solved"])
        self.assertEqual(state["progress"], 0)

    def test_rational_negative_two_sided_and_degenerate_examples(self):
        for equation, expected in (
            ("3*x+2=x+10", ("unique", Fraction(4))),
            ("x/2+1=3", ("unique", Fraction(4))),
            ("-2*(x-3)=8", ("unique", Fraction(-1))),
            ("(1/2)*x+1/3=5/6", ("unique", Fraction(1))),
            ("x-x=0", ("all", None)),
            ("x-x=1", ("none", None)),
            ("4=x", ("unique", Fraction(4))),
        ):
            with self.subTest(equation=equation):
                state = algebra.describe(equation)
                history = [state["current"]]
                for _ in range(12):
                    self.assertEqual(algebra.solution(algebra.parse_equation(state["current"])), expected)
                    if state["solved"]:
                        break
                    move = algebra.select_move(
                        "guided", state["current"], algebra.GOAL, history, state["moves"],
                        state["moves"][0], {}, 64,
                    )
                    history.append(move["result"])
                    state = algebra.describe(move["result"])
                self.assertTrue(state["solved"])

    def test_every_generated_move_preserves_known_solution_sets(self):
        rng = random.Random(61)
        for _ in range(60):
            a, b, c, d = (rng.randint(-6, 6) for _ in range(4))
            text = f"{a}*(x+{b})+{c}={d}"
            expected = ("unique", Fraction(d - c, a) - b) if a else (
                ("all", None) if c == d else ("none", None)
            )
            state = algebra.describe(text)
            for move in state["moves"]:
                with self.subTest(current=text, move=move["label"]):
                    result = algebra.parse_equation(move["result"])
                    self.assertEqual(algebra.solution(result), expected)
                    self.assertEqual(move["solved"], algebra.is_solved(result))
                    self.assertEqual(move["progress"], algebra.progress(result))
                    self.assertLessEqual(len(move["result"]), algebra.MAX_LENGTH)

    def test_limits_omit_only_unrepresentable_moves_and_report_them(self):
        big = 2**127
        state = algebra.describe(f"{big} = {-big}")
        self.assertEqual(state["omitted_for_limits"], 2)
        self.assertEqual([move["rule"] for move in state["moves"]], [7])
        self.assertTrue(state["solved"])

    def test_model_policy_preserves_raw_choice_and_guided_respects_budget(self):
        state = algebra.describe(algebra.DEFAULT_EQUATION)
        raw = state["moves"][0]
        self.assertIs(algebra.select_move(
            "model", state["current"], algebra.GOAL, [], state["moves"], raw, {}, 8,
        ), raw)
        chosen = algebra.select_move(
            "guided", state["current"], algebra.GOAL, [], state["moves"], raw, {}, 9,
        )
        self.assertLessEqual(len(chosen["result"]), 9)

    def test_distribution_overflow_does_not_discard_the_remaining_menu(self):
        big = 2**127
        state = algebra.describe(f"2 * ((x - {big}) + {big}) = 0")
        self.assertGreater(state["omitted_for_limits"], 0)
        self.assertTrue(state["moves"])
        for move in state["moves"]:
            self.assertEqual(
                algebra.solution(algebra.parse_equation(move["result"])),
                ("unique", Fraction(0)),
            )


class SharedAlgebraProviderTests(unittest.TestCase):
    @patch("app.require_compatible_ollama")
    @patch.dict("os.environ", {"TYPESAFE_API_KEY": "test-placeholder"})
    def test_both_providers_receive_algebra_context_and_return_a_legal_choice(self, _compatible):
        state = algebra.describe(algebra.DEFAULT_EQUATION)
        for provider, key in (("ollama", "A"), ("typesafe", "move_0")):
            response = io.BytesIO(json.dumps({"answers": {"next_move": {
                "choice": key, "probabilities": {key: 1},
            }}}).encode())
            with self.subTest(provider=provider), patch("app.urllib.request.urlopen", return_value=response) as send:
                result = choose_move(
                    provider, "test-model", "guided", state["current"], algebra.GOAL,
                    [state["current"]], state["moves"], 64, system="algebra",
                )
            body = json.loads(send.call_args.args[0].data)
            self.assertIn("linear equations", body["state"]["formal_system"])
            self.assertEqual(body["state"]["current_equation"], state["current"])
            self.assertNotIn("modulo", json.dumps(body))
            self.assertNotIn("III", json.dumps(body))
            self.assertEqual(result["system"], "algebra")
            self.assertIn(result["move"], state["moves"])
            self.assertEqual(result["move"]["result"], "x + 3 = 7")
            group = result["rounds"][0]["groups"][0]
            self.assertEqual(group["raw_choice"], state["moves"][0]["id"])
            self.assertTrue(group["overridden"])
            self.assertEqual("keep_alive" in body, provider == "ollama")

    @patch("app.require_compatible_ollama")
    def test_algebra_uses_shared_tournaments_without_losing_candidates(self, _compatible):
        text = " + ".join(f"{i}*(x+{i})" for i in range(2, 14)) + " = 8"
        state = algebra.describe(text)
        self.assertGreater(len(state["moves"]), 26)

        def respond(request, **_kwargs):
            body = json.loads(request.data)
            self.assertIn("current_equation", body["state"])
            keys = list(body["questions"]["next_move"]["criteria"])
            return io.BytesIO(json.dumps({"answers": {"next_move": {
                "choice": keys[0], "probabilities": {key: 1 / len(keys) for key in keys},
            }}}).encode())

        with patch("app.urllib.request.urlopen", side_effect=respond):
            result = choose_move(
                "ollama", "nimble", "model", state["current"], algebra.GOAL, [],
                state["moves"], algebra.MAX_LENGTH, system="algebra",
            )
        considered = [id_ for group in result["rounds"][0]["groups"] for id_ in group["candidates"]]
        self.assertEqual(considered, [move["id"] for move in state["moves"]])
        self.assertGreater(len(result["rounds"]), 1)


if __name__ == "__main__":
    unittest.main()
