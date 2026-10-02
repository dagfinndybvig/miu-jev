import http.client
import io
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from app import (
    MAX_MIU_LENGTH,
    RequestHandler,
    choose_move,
    contraction_opportunities,
    decision_request,
    heuristic_score,
    is_growth_only_trap,
    legal_moves,
    parse_version,
    require_compatible_ollama,
    rewrite_opportunities,
    select_move,
    validate_miu,
)


class LegalMovesTests(unittest.TestCase):
    def test_ollama_version_parsing(self):
        self.assertEqual(parse_version("0.35.0"), (0, 35, 0))
        self.assertEqual(parse_version("0.35.1-rc1"), (0, 35, 1))
        self.assertIsNone(parse_version("development"))

    @patch(
        "app.ollama_status",
        return_value={
            "available": True,
            "compatible": False,
            "version": "0.34.2",
            "error": "Ollama 0.35.0 or later is required",
        },
    )
    def test_old_ollama_is_rejected(self, _status):
        with self.assertRaisesRegex(RuntimeError, "0.35.0 or later"):
            require_compatible_ollama()

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
                64,
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
            lambda provider, model, policy, current, goal, history, candidates, max_length: (
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
            64,
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
            64,
        )
        self.assertEqual(selected["id"], productive["id"])

    def test_model_policy_preserves_model_choice(self):
        current = "MIII"
        moves = legal_moves(current)
        growth = next(move for move in moves if move["rule"] == 2)
        selected = select_move(
            "model", current, "MU", [current], moves, growth, {}, 64
        )
        self.assertEqual(selected["id"], growth["id"])

    def test_guided_policy_respects_length_budget(self):
        current = "M" + ("I" * 8)
        moves = legal_moves(current)
        oversized = next(move for move in moves if move["rule"] == 2)
        bounded = next(move for move in moves if move["rule"] == 3)
        selected = select_move(
            "guided",
            current,
            "MUI",
            [current],
            moves,
            oversized,
            {oversized["id"]: 0.99, bounded["id"]: 0.01},
            10,
        )
        self.assertEqual(selected["id"], bounded["id"])


class ProviderResponseTests(unittest.TestCase):
    def decide(self, payload, provider="ollama"):
        response = io.BytesIO(json.dumps(payload).encode("utf-8"))
        with (
            patch("app.require_compatible_ollama"),
            patch.dict("os.environ", {"TYPESAFE_API_KEY": "test-placeholder"}),
            patch("app.urllib.request.urlopen", return_value=response),
        ):
            return decision_request(
                provider, "test-model", "model", "MI", "MU", ["MI"],
                legal_moves("MI"), 64,
            )

    def test_valid_probability_mapping_for_both_providers(self):
        for provider, keys in (
            ("ollama", ("A", "B")),
            ("typesafe", ("move_0", "move_1")),
        ):
            with self.subTest(provider=provider):
                move, probabilities = self.decide(
                    {"answers": {"next_move": {
                        "choice": keys[1],
                        "probabilities": {keys[0]: 0.25, keys[1]: "0.75"},
                    }}},
                    provider,
                )
                self.assertEqual(move["result"], "MII")
                self.assertEqual(probabilities, {"move-0": 0.25, "move-1": 0.75})
                json.dumps(probabilities, allow_nan=False)

    def test_invalid_probabilities_are_upstream_errors(self):
        invalid_values = (
            "NaN", "Infinity", "-Infinity", float("nan"), float("inf"),
            -0.1, 1.1, True, None, [], {}, "not-a-number", 10 ** 400,
        )
        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaisesRegex(RuntimeError, "invalid probability"):
                    self.decide({"answers": {"next_move": {
                        "choice": "A", "probabilities": {"A": value},
                    }}})

    def test_malformed_response_shapes_are_upstream_errors(self):
        for payload in (
            [], None, {}, {"answers": []}, {"answers": {"next_move": []}},
            {"answers": {"next_move": {"choice": []}}},
            {"answers": {"next_move": {"choice": "A", "probabilities": []}}},
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(RuntimeError):
                    self.decide(payload)

    def test_probability_boundaries_and_missing_probabilities(self):
        for probabilities in ({}, {"A": 0, "B": 1}):
            _, mapped = self.decide({"answers": {"next_move": {
                "choice": "A", "probabilities": probabilities,
            }}})
            self.assertEqual(len(mapped), len(probabilities))
        _, mapped = self.decide({"answers": {"next_move": {"choice": "A"}}})
        self.assertEqual(mapped, {})

    def test_invalid_json_is_an_upstream_error(self):
        with (
            patch("app.require_compatible_ollama"),
            patch("app.urllib.request.urlopen", return_value=io.BytesIO(b"not JSON")),
        ):
            with self.assertRaisesRegex(RuntimeError, "returned invalid JSON"):
                decision_request(
                    "ollama", "test-model", "model", "MI", "MU", ["MI"],
                    legal_moves("MI"), 64,
                )


class HttpApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), RequestHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, method, path, body=None):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        try:
            connection.request(
                method, path, body=json.dumps(body) if body is not None else None,
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_health_never_automatically_selects_hosted_provider(self):
        for compatible in (True, False):
            for configured in (True, False):
                with (
                    self.subTest(compatible=compatible, configured=configured),
                    patch.dict("os.environ", {
                        "TYPESAFE_API_KEY": "test-placeholder" if configured else "",
                    }),
                    patch("app.ollama_status", return_value={
                        "compatible": compatible,
                        "version": "0.35.0" if compatible else "0.34.2",
                        "error": None if compatible else "Ollama 0.35.0 or later is required",
                    }),
                ):
                    status, payload = self.request("GET", "/api/health")
                    self.assertEqual(status, 200)
                    self.assertEqual(payload["default_provider"], "ollama")
                    self.assertEqual(payload["providers"]["ollama"]["available"], compatible)
                    self.assertEqual(payload["providers"]["typesafe"]["available"], configured)
                    self.assertNotIn("test-placeholder", json.dumps(payload))

    @patch("app.decision_request")
    def test_invalid_provider_types_return_bad_request(self, decide):
        for provider in ([], {}, None, True, 42, "unknown"):
            with self.subTest(provider=provider):
                status, payload = self.request(
                    "POST", "/api/choose", {"current": "MI", "provider": provider},
                )
                self.assertEqual(status, 400)
                self.assertEqual(payload["error"], "provider must be ollama or typesafe")
        decide.assert_not_called()

    def test_invalid_upstream_probability_returns_bad_gateway(self):
        response = io.BytesIO(json.dumps({"answers": {"next_move": {
            "choice": "A", "probabilities": {"A": "NaN"},
        }}}).encode("utf-8"))
        with (
            patch("app.require_compatible_ollama"),
            patch("app.urllib.request.urlopen", return_value=response),
        ):
            status, payload = self.request("POST", "/api/choose", {"current": "MI"})
        self.assertEqual(status, 502)
        self.assertEqual(payload["error"], "Ollama returned an invalid probability")

    def test_choose_recomputes_legal_menu(self):
        response = io.BytesIO(json.dumps({"answers": {"next_move": {
            "choice": "B", "probabilities": {"A": 0, "B": 1},
        }}}).encode("utf-8"))
        with (
            patch("app.require_compatible_ollama"),
            patch("app.urllib.request.urlopen", return_value=response),
        ):
            status, payload = self.request("POST", "/api/choose", {
                "current": "MI", "policy": "model",
                "moves": [{"id": "move-1", "result": "MU"}],
            })
        self.assertEqual(status, 200)
        self.assertEqual(payload["move"]["result"], "MII")
        self.assertEqual(payload["moves"], legal_moves("MI"))


if __name__ == "__main__":
    unittest.main()
