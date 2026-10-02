import unittest
from unittest.mock import patch

from app import choose_move, decision_request, legal_moves, validate_miu


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


class SelectionTests(unittest.TestCase):
    @patch.dict("os.environ", {"TYPESAFE_API_KEY": ""})
    def test_typesafe_requires_server_side_key(self):
        with self.assertRaisesRegex(RuntimeError, "TYPESAFE_API_KEY"):
            decision_request(
                "typesafe",
                "jev-latest",
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
            lambda provider, model, current, goal, history, candidates: (
                candidates[-1],
                {
                    candidate["id"]: 1 / len(candidates)
                    for candidate in candidates
                },
            )
        )
        result = choose_move("ollama", "nimble", "MI", "MU", ["MI"], moves)
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
        result = choose_move("typesafe", "jev-latest", "MI", "MU", ["MI"], moves)
        self.assertEqual(result["move"]["id"], "move-29")
        decide.assert_called_once()


if __name__ == "__main__":
    unittest.main()
