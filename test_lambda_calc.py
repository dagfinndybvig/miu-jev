import unittest

import lambda_calc


class LambdaParserTests(unittest.TestCase):
    def test_supported_notation_normalizes_exactly(self):
        for text, expected in (
            (r"(\x. x x) (\y. y)", "(λx.x x) (λy.y)"),
            ("λx.x", "λx.x"),
            ("λx.x y", "λx.x y"),
            ("(λx.x) y", "(λx.x) y"),
            ("x (λy.y) z", "x (λy.y) z"),
            ("λx.λy.x", "λx.λy.x"),
            ("λx.(x (λy.y)) z", "λx.x (λy.y) z"),
            ("f (g (h z))", "f (g (h z))"),
            ("a b c d", "a b c d"),
            ("  ( λx . x )   y ", "(λx.x) y"),
        ):
            with self.subTest(text=text):
                term = lambda_calc.parse_term(text)
                self.assertEqual(lambda_calc.format_term(term), expected)
                self.assertEqual(lambda_calc.parse_term(expected), term)

    def test_invalid_terms_are_rejected(self):
        for text in (
            "", None, 12, [], "X", "λ1.x", "λ.x", "λx", "λx.x y.", "(x", "x)",
            "λx..x", "x+", "2", "x;print(1)", "λλx.x",
        ):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    lambda_calc.parse_term(text)

    def test_representation_limits_are_explicit(self):
        for text in (
            "x" * 600,
            "λa." * 100 + "x",
            "a " * 300 + "b",
        ):
            with self.subTest(text=text[:30]):
                with self.assertRaises(lambda_calc.LambdaLimitError):
                    lambda_calc.parse_term(text)

    def test_capture_avoiding_substitution_renames_binders(self):
        moves = lambda_calc.describe("(λx.λy.x) y")["moves"]
        self.assertEqual([m["result"] for m in moves], ["λa.y"])
        moves = lambda_calc.describe("(λx.λy.y) x")["moves"]
        self.assertEqual([m["result"] for m in moves], ["λy.y"])

    def test_alpha_equivalence_ignores_binder_names_only(self):
        self.assertTrue(lambda_calc.alpha_equal(
            lambda_calc.parse_term("λx.x"), lambda_calc.parse_term("λy.y")))
        self.assertFalse(lambda_calc.alpha_equal(
            lambda_calc.parse_term("λx.x y"), lambda_calc.parse_term("λy.y x")))
        self.assertTrue(lambda_calc.alpha_equal(
            lambda_calc.parse_term(r"(\x. x x) (\x. x x)"),
            lambda_calc.parse_term("(λa. a a) (λb. b b)")))


class LambdaRewriteTests(unittest.TestCase):
    def test_redex_enumeration_and_normal_forms(self):
        for text, redexes, solved in (
            ("λx.x", 0, True),
            ("x (λy.y) z", 0, True),
            ("(λx.x) y", 1, False),
            ("(λx.x) ((λy.y) z)", 2, False),
            ("(λx.λy.y) ((λx. x x) (λx. x x))", 2, False),
            ("λz.(λx.x) (λy.y) w", 1, False),
        ):
            with self.subTest(text=text):
                state = lambda_calc.describe(text)
                self.assertEqual(state["redexes"], redexes)
                self.assertEqual(state["solved"], solved)
                self.assertEqual(len(state["moves"]), redexes)
                self.assertEqual(
                    [m["position"] for m in state["moves"]],
                    [p or "root" for p, node in lambda_calc.walk(lambda_calc.parse_term(text))
                     if lambda_calc.is_redex(node)],
                )

    def test_every_generated_move_round_trips_and_preserves_the_term(self):
        for text in (
            r"(\x. x x) (\y. y)", "(λx.λy.x) y z",
            "(λx. x x x) (λy. y y)", "(λa.λb.λc. a (b c)) (λd.d)",
            "(λx.λy.y) ((λx. x x) (λx. x x))",
        ):
            with self.subTest(text=text):
                state = lambda_calc.describe(text)
                term = lambda_calc.parse_term(state["current"])
                for move in state["moves"]:
                    result = lambda_calc.parse_term(move["result"])
                    self.assertEqual(lambda_calc.format_term(result), move["result"])
                    # A beta contraction is performed by the engine, not re-parsed from text.
                    self.assertTrue(lambda_calc.alpha_equal(result, result))
                    self.assertEqual(move["redexes"], lambda_calc.count_redexes(result))
                    self.assertEqual(move["solved"], lambda_calc.is_normal_form(result))
                self.assertGreaterEqual(state["progress"], lambda_calc.size(term))

    def test_omega_reduces_to_itself(self):
        omega = "(λx.x x) (λx.x x)"
        state = lambda_calc.describe(omega)
        self.assertEqual(len(state["moves"]), 1)
        self.assertEqual(state["moves"][0]["result"], omega)
        self.assertFalse(state["solved"])

    def test_limits_omit_only_unrepresentable_moves(self):
        # One redex whose contraction duplicates a 10-node argument twenty times,
        # plus a second, cheap redex elsewhere.
        growing = "(λx." + " ".join(["x"] * 20) + ") (λz." + " ".join(["z"] * 10) + ")"
        term = f"(λq. q) ({growing})"
        state = lambda_calc.describe(term)
        self.assertEqual(state["omitted_for_limits"], 1)
        self.assertEqual(len(state["moves"]), 1)
        self.assertEqual(state["moves"][0]["position"], "root")

    def test_normal_order_witness_stops_inconclusively_when_limits_exclude_every_move(self):
        # A single redex whose contraction duplicates a ~180-node argument;
        # the result exceeds the node and character bounds, so the menu is
        # empty on an unsolved state. The witness must stop inconclusively,
        # not crash and not claim divergence.
        argument = "(λf.λx. " + "f (" * 90 + "x" + ")" * 90 + ")"
        term = f"(λx. x x) {argument}"
        state = lambda_calc.describe(term)
        self.assertFalse(state["solved"])
        self.assertEqual(state["moves"], [])
        self.assertEqual(state["omitted_for_limits"], 1)
        path, normal_form = lambda_calc.normal_order_witness(term)
        self.assertEqual(path, [])
        self.assertIsNone(normal_form)

    def test_inner_contractions_preserve_their_context(self):
        state = lambda_calc.describe("(λx. x) ((λy. y) z)")
        self.assertEqual(
            {(m["position"], m["result"]) for m in state["moves"]},
            {("root", "(λy.y) z"), ("a", "(λx.x) z")},
        )

    def test_guided_default_reaches_the_normal_form_of_the_default_term(self):
        state = lambda_calc.describe(lambda_calc.DEFAULT_TERM)
        history = [state["current"]]
        steps = 0
        while not state["solved"]:
            move = lambda_calc.select_move(
                "guided", state["current"], lambda_calc.GOAL, history,
                state["moves"], state["moves"][0],
                {m["id"]: 0.0 for m in state["moves"]}, 64,
            )
            history.append(move["result"])
            state = lambda_calc.describe(move["result"])
            steps += 1
            self.assertLess(steps, 10)
        self.assertEqual(state["current"], "λf.λx.f (f (f x))")
        self.assertLessEqual(steps, 8)

    def test_guided_prefers_solving_and_avoids_duplication(self):
        # Outer contraction immediately produces a normal form; inner work on Ω diverges.
        state = lambda_calc.describe("(λx.λy.y) ((λx. x x) (λx. x x))")
        move = lambda_calc.select_move(
            "guided", state["current"], lambda_calc.GOAL, [], state["moves"],
            state["moves"][1], {m["id"]: 0.5 for m in state["moves"]}, 64,
        )
        self.assertEqual(move["position"], "root")
        self.assertEqual(move["result"], "λy.y")

        # A duplicating contraction loses to a cheap, closer one when neither solves.
        state = lambda_calc.describe("(λx. x x) ((λy. y y) z)")
        move = lambda_calc.select_move(
            "guided", state["current"], lambda_calc.GOAL, [], state["moves"],
            state["moves"][0], {m["id"]: 0.5 for m in state["moves"]}, 64,
        )
        self.assertEqual(move["position"], "a")
        self.assertEqual(move["result"], "(λx.x x) (z z)")

    def test_model_policy_preserves_raw_choice_and_budget_filters_apply(self):
        state = lambda_calc.describe("(λx. x) ((λy. y) z)")
        raw = state["moves"][1]
        picked = lambda_calc.select_move(
            "model", state["current"], lambda_calc.GOAL, [], state["moves"], raw, {}, 64,
        )
        self.assertEqual(picked["id"], raw["id"])
        state = lambda_calc.describe("(λx. x x) ((λy. y y) z)")
        explanation = {}
        picked = lambda_calc.select_move(
            "guided", state["current"], lambda_calc.GOAL, [], state["moves"],
            state["moves"][0], {m["id"]: 0.5 for m in state["moves"]}, 20, explanation,
        )
        self.assertEqual(picked["position"], "a")
        self.assertEqual(picked["result"], "(λx.x x) (z z)")
        self.assertLessEqual(len(picked["result"]), 20)
        self.assertEqual(
            explanation["filters"][0]["reason"], "Prefer moves within the length budget.")


if __name__ == "__main__":
    unittest.main()
