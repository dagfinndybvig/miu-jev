import unittest
from unittest.mock import patch

from app import (
    MAX_MIU_LENGTH,
    choose_move,
    contraction_opportunities,
    decision_request,
    heuristic_score,
    is_growth_only_trap,
    legal_moves,
    rewrite_opportunities,
    select_move,
    validate_miu,
)


class LegalMovesTests(unittest.TestCase):
    def test_axiom_moves(self):
        moves = legal_moves("MI")
        self.assertEqual(
            [(move["rule"], move["result"]) for move in moves],
            [(1, "MIU"), (2, "MII")],
        )

    def test_all_rules_and_overlapping_occurrences(self):
        moves = legal_moves("MIIIUU")
        self.assertEqual(
            [(move["rule"], move["position"], move["result"]) for move in moves],
            [
                (2, 1, "MIIIUUIIIUU"),
                (3, 1, "MUUU"),
                (4, 4, "MIII"),
            ],
        )
        overlapping = legal_moves("MIIII")
        self.assertEqual(
            [move["position"] for move in overlapping if move["rule"] == 3],
            [1, 2],
        )

    def test_rule_four_can_produce_m(self):
        moves = legal_moves("MUU")
        self.assertIn((4, "M"), [(move["rule"], move["result"]) for move in moves])

    def test_validation(self):
        self.assertEqual(validate_miu("MIU", "current"), "MIU")
        for invalid in ("", "MIX", None, 12):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    validate_miu(invalid, "current")
        with self.assertRaisesRegex(ValueError, "must not exceed"):
            validate_miu("M" + ("I" * MAX_MIU_LENGTH), "current")

    def test_rewrite_opportunity_count(self):
        self.assertEqual(rewrite_opportunities("MIIIIUU"), 3)
        self.assertEqual(contraction_opportunities("MIIIIUU"), 3)

    def test_growth_with_contraction_is_better_than_blind_doubling(self):
        current = "MII"
        moves = legal_moves(current)
        duplicate = next(move for move in moves if move["rule"] == 2)
        append = next(move for move in moves if move["rule"] == 1)
        self.assertGreater(
            heuristic_score(duplicate, current, "MU", [current]),
            heuristic_score(append, current, "MU", [current]),
        )

    def test_growth_only_trap_detection(self):
        self.assertTrue(is_growth_only_trap("MIU"))
        self.assertTrue(is_growth_only_trap("MIIU"))
        self.assertFalse(is_growth_only_trap("MUIU"))
        self.assertFalse(is_growth_only_trap("MII"))


class SelectionTests(unittest.TestCase):
    @patch.dict("os.environ", {"TYPESAFE_API_KEY": ""})
    def test_typesafe_requires_server_side_key(self):
        with self.assertRaisesRegex(RuntimeError, "TYPESAFE_API_KEY"):
            decision_request(
                "typesafe",
                "jev-latest",
                "guided",
                "MI",
                "MU",
                ["MI"],
                legal_moves("MI"),
            )

    @patch("app.decision_request")
    def test_tournament_considers_more_than_26_moves(self, decide):
        moves = [
            {
                "id": f"move-{index}",
                "rule": 3,
                "position": index,
                "result": f"M{'I' * (index + 1)}",
                "label": "test",
                "detail": "test",
            }
            for index in range(30)
        ]
        decide.side_effect = (
            lambda provider, model, policy, current, goal, history, candidates: (
                candidates[-1],
                {
                    candidate["id"]: 1 / len(candidates)
                    for candidate in candidates
                },
            )
        )
        result = choose_move(
            "ollama", "nimble", "guided", "MI", "MU", ["MI"], moves
        )
        self.assertEqual(result["move"]["id"], "move-29")
        self.assertEqual(decide.call_count, 3)
        self.assertEqual(result["rounds"][0]["contenders"], 30)
        self.assertEqual(result["rounds"][1]["contenders"], 2)

    @patch("app.decision_request")
    def test_typesafe_uses_larger_choice_limit(self, decide):
        moves = [
            {
                "id": f"move-{index}",
                "rule": 3,
                "position": index,
                "result": f"M{'I' * (index + 1)}",
                "label": "test",
                "detail": "test",
            }
            for index in range(30)
        ]
        decide.return_value = (
            moves[-1],
            {move["id"]: 1 / len(moves) for move in moves},
        )
        result = choose_move(
            "typesafe", "jev-latest", "guided", "MI", "MU", ["MI"], moves
        )
        self.assertEqual(result["move"]["id"], "move-29")
        decide.assert_called_once()

    def test_guided_policy_prefers_a_reduction(self):
        current = "MIII"
        moves = legal_moves(current)
        growth = next(move for move in moves if move["rule"] == 2)
        reduction = next(move for move in moves if move["rule"] == 3)
        selected = select_move(
            "guided",
            current,
            "MU",
            [current],
            moves,
            growth,
            {growth["id"]: 0.99, reduction["id"]: 0.01},
        )
        self.assertEqual(selected["id"], reduction["id"])

    def test_guided_policy_avoids_miu_growth_trap(self):
        current = "MI"
        moves = legal_moves(current)
        trapped = next(move for move in moves if move["result"] == "MIU")
        productive = next(move for move in moves if move["result"] == "MII")
        selected = select_move(
            "guided",
            current,
            "MU",
            [current],
            moves,
            trapped,
            {trapped["id"]: 0.999, productive["id"]: 0.001},
        )
        self.assertEqual(selected["id"], productive["id"])

    def test_model_policy_preserves_model_choice(self):
        current = "MIII"
        moves = legal_moves(current)
        growth = next(move for move in moves if move["rule"] == 2)
        selected = select_move(
            "model", current, "MU", [current], moves, growth, {}
        )
        self.assertEqual(selected["id"], growth["id"])


if __name__ == "__main__":
    unittest.main()
