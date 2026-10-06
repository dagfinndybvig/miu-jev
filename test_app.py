import http.client
import io
import json
import threading
import urllib.error
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import algebra
import grammar
import lambda_calc

from app import (
    MAX_MIU_LENGTH,
    DecisionError,
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
    validate_system,
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

    def test_system_validation_message_lists_every_system(self):
        for system in ("miu", "algebra", "lambda", "grammar"):
            self.assertEqual(validate_system(system), system)
        for invalid in ([], "unknown", None):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(
                    ValueError, "miu, algebra, lambda, or grammar"
                ):
                    validate_system(invalid)

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
            lambda provider, model, policy, current, goal, history, candidates, max_length, trace=None, system="miu", hints=True: (
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

    def test_hint_ablation_strips_annotations_from_provider_state(self):
        captured = {}
        response = io.BytesIO(json.dumps({"answers": {"next_move": {
            "choice": "A", "probabilities": {"A": 1},
        }}}).encode())

        def record(request, timeout=0):
            captured["body"] = json.loads(request.data)
            return io.BytesIO(json.dumps({"answers": {"next_move": {
                "choice": "A", "probabilities": {"A": 1},
            }}}).encode())

        with (
            patch("app.require_compatible_ollama"),
            patch("app.urllib.request.urlopen", side_effect=record),
        ):
            decision_request("ollama", "nimble:latest", "guided", "MI", "MU", ["MI"],
                             legal_moves("MI"), 64, hints=False)
        state = captured["body"]["state"]
        self.assertEqual(state["formal_system"], "A formal rewrite system")
        self.assertIn("no further annotations", state["invariant"])
        self.assertIn("Judge the candidates", state["search_guidance"])
        self.assertTrue(all(
            "length" not in text and "visited" not in text and "trap" not in text
            for text in state["candidate_moves"].values()
        ))

        with (
            patch("app.require_compatible_ollama"),
            patch("app.urllib.request.urlopen", side_effect=record),
        ):
            decision_request("ollama", "nimble:latest", "guided", "MI", "MU", ["MI"],
                             legal_moves("MI"), 64, hints=True)
        state = captured["body"]["state"]
        self.assertEqual(state["formal_system"], "MIU")
        self.assertTrue(any(
            "growth-only trap" in text for text in state["candidate_moves"].values()
        ))

    def test_hint_criteria_match_each_system(self):
        captured = {}

        def record(request, timeout=0):
            captured["body"] = json.loads(request.data)
            return io.BytesIO(json.dumps({"answers": {"next_move": {
                "choice": "A", "probabilities": {"A": 1},
            }}}).encode())

        cases = (
            ("algebra", algebra.describe("2 * (x + 3) = 14")["moves"],
             "structural progress cost", "constituents after"),
            ("lambda", lambda_calc.describe("(\\x. x x) (\\y. y)")["moves"],
             "structural progress cost", "constituents after"),
            ("grammar", grammar.describe(grammar.DEFAULT_SENTENCE)["moves"],
             "constituents after", "structural progress cost"),
        )
        for system, moves, expected, forbidden in cases:
            with self.subTest(system=system):
                with (
                    patch("app.require_compatible_ollama"),
                    patch("app.urllib.request.urlopen", side_effect=record),
                ):
                    decision_request(
                        "ollama", "test-model", "model", "state", "goal", [],
                        moves, 512, system=system,
                    )
                texts = captured["body"]["questions"]["next_move"]["criteria"].values()
                self.assertTrue(any(expected in text for text in texts))
                self.assertFalse(any(forbidden in text for text in texts))

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

    def test_choose_defaults_to_the_model_only_policy(self):
        response = io.BytesIO(json.dumps({"answers": {"next_move": {
            "choice": "A", "probabilities": {"A": 1, "B": 0},
        }}}).encode())
        with (
            patch("app.require_compatible_ollama"),
            patch("app.urllib.request.urlopen", return_value=response),
        ):
            status, payload = self.request("POST", "/api/choose", {
                "current": "MI", "goal": "MII",
                "moves": [{"id": "move-0", "result": "MII"}],
            })
        self.assertEqual(status, 200)
        self.assertEqual(payload["policy"], "model")
        self.assertEqual(payload["override_count"], 0)
        self.assertEqual(payload["move"]["result"], "MIU")

    def test_algebra_moves_normalize_and_report_goal_state(self):
        status, payload = self.request("POST", "/api/moves", {
            "system": "algebra", "current": "2(x+3)=14",
        })
        self.assertEqual(status, 200)
        self.assertEqual(payload["current"], algebra.DEFAULT_EQUATION)
        self.assertFalse(payload["solved"])
        self.assertIn("x + 3 = 7", [move["result"] for move in payload["moves"]])
        for equation, kind in (("x=4", "unique"), ("0=0", "all"), ("0=1", "none")):
            status, payload = self.request("POST", "/api/moves", {
                "system": "algebra", "current": equation,
            })
            self.assertEqual(status, 200)
            self.assertTrue(payload["solved"])
            self.assertEqual(payload["solution_kind"], kind)

    def test_algebra_choose_recomputes_equivalent_moves(self):
        response = io.BytesIO(json.dumps({"answers": {"next_move": {
            "choice": "A", "probabilities": {"A": 1},
        }}}).encode())
        with (
            patch("app.require_compatible_ollama"),
            patch("app.urllib.request.urlopen", return_value=response),
        ):
            status, payload = self.request("POST", "/api/choose", {
                "system": "algebra", "current": "2(x+3)=14",
                "moves": [{"id": "move-0", "result": "x = 999"}],
            })
        self.assertEqual(status, 200)
        self.assertEqual(payload["system"], "algebra")
        self.assertEqual(payload["goal"], algebra.GOAL)
        self.assertEqual(payload["policy"], "model")
        self.assertEqual(payload["move"]["result"], "2 * x + 6 = 14")
        self.assertFalse(payload["analysis"]["solved"])
        self.assertNotIn("x = 999", [move["result"] for move in payload["moves"]])

    def test_lambda_moves_normalize_and_report_goal_state(self):
        status, payload = self.request("POST", "/api/moves", {
            "system": "lambda", "current": "(\\x. x x) (\\y. y)",
        })
        self.assertEqual(status, 200)
        self.assertEqual(payload["system"], "lambda")
        self.assertEqual(payload["current"], "(λx.x x) (λy.y)")
        self.assertFalse(payload["solved"])
        self.assertEqual(payload["redexes"], 1)
        self.assertEqual(payload["moves"][0]["result"], "(λy.y) (λy.y)")
        self.assertEqual(payload["solution_kind"], "reducible")
        status, payload = self.request("POST", "/api/moves", {
            "system": "lambda", "current": "λx.x",
        })
        self.assertEqual(status, 200)
        self.assertTrue(payload["solved"])
        self.assertEqual(payload["solution_kind"], "normal")
        self.assertEqual(payload["moves"], [])

    def test_lambda_choose_recomputes_equivalent_moves(self):
        with patch("app.decision_request") as decide:
            status, payload = self.request("POST", "/api/choose", {
                "system": "lambda", "current": "(\\x. x x) (\\y. y)",
                "moves": [{"id": "move-0", "result": "λz.z"}],
                "history": ["(λx.x x) (λy.y)"],
            })
        self.assertEqual(status, 200)
        self.assertEqual(payload["system"], "lambda")
        self.assertEqual(payload["goal"], lambda_calc.GOAL)
        self.assertEqual(payload["move"]["result"], "(λy.y) (λy.y)")
        self.assertNotIn("λz.z", [move["result"] for move in payload["moves"]])
        self.assertFalse(payload["analysis"]["solved"])
        decide.assert_not_called()

    def test_grammar_moves_normalize_and_report_goal_state(self):
        status, payload = self.request("POST", "/api/moves", {
            "system": "grammar", "current": grammar.DEFAULT_SENTENCE,
        })
        self.assertEqual(status, 200)
        self.assertEqual(payload["system"], "grammar")
        self.assertEqual(
            payload["current"],
            "[Det the] [N man] [V saw] [Det the] [N dog] [P with] [Det the] [N telescope]",
        )
        self.assertFalse(payload["solved"])
        self.assertEqual(payload["parse_count"], 2)
        self.assertEqual(payload["solution_kind"], "incomplete")
        self.assertEqual([move["position"] for move in payload["moves"]], [0, 3, 6])
        solved = ("[S [NP [Det the] [N man]] "
                  "[VP [V saw] [NP [Det the] [N dog]]]]")
        status, payload = self.request("POST", "/api/moves", {
            "system": "grammar", "current": solved,
        })
        self.assertEqual(status, 200)
        self.assertTrue(payload["solved"])
        self.assertEqual(payload["solution_kind"], "parsed")
        self.assertEqual(payload["moves"], [])

    def test_grammar_choose_recomputes_equivalent_moves(self):
        current = "[NP [Det the] [N dog]] [V saw] [NP [Det the] [N pizza]]"
        with patch("app.decision_request") as decide:
            status, payload = self.request("POST", "/api/choose", {
                "system": "grammar", "current": current,
                "moves": [{"id": "move-0", "result": "[S nope]"}],
                "history": [current],
            })
        self.assertEqual(status, 200)
        self.assertEqual(payload["system"], "grammar")
        self.assertEqual(payload["goal"], grammar.GOAL)
        self.assertEqual(payload["policy"], "model")
        self.assertEqual(
            payload["move"]["result"],
            "[NP [Det the] [N dog]] [VP [V saw] [NP [Det the] [N pizza]]]",
        )
        self.assertNotIn("[S nope]", [move["result"] for move in payload["moves"]])
        self.assertEqual(len(payload["moves"]), 1)
        self.assertFalse(payload["analysis"]["solved"])
        decide.assert_not_called()

    @patch("app.decision_request")
    def test_invalid_systems_and_algebra_inputs_are_bad_requests(self, decide):
        for body in (
            {"system": [], "current": "MI"},
            {"system": "unknown", "current": "MI"},
            {"system": "algebra", "current": "x*x=4"},
            {"system": "algebra", "current": "x/x=1"},
            {"system": "algebra", "current": "x/0=1"},
            {"system": "algebra", "current": "2*x=4", "goal": "x = 2"},
            {"system": "algebra", "current": "2*x=4", "max_length": 513},
            {"system": "lambda", "current": "x+"},
            {"system": "lambda", "current": "λx"},
            {"system": "lambda", "current": "(λx.x) y", "goal": "x"},
            {"system": "lambda", "current": "λx.x", "history": ["λx.x", "x+1"]},
            {"system": "grammar", "current": "the man saw the unicorn"},
            {"system": "grammar", "current": "the [N dog]"},
            {"system": "grammar", "current": grammar.DEFAULT_SENTENCE, "goal": "Parse it"},
            {"system": "grammar", "current": grammar.DEFAULT_SENTENCE, "max_length": 513},
            {"system": "grammar", "current": grammar.DEFAULT_SENTENCE,
             "history": [grammar.DEFAULT_SENTENCE, "[S nope]"]},
        ):
            with self.subTest(body=body):
                status, payload = self.request("POST", "/api/choose", body)
                self.assertEqual(status, 400)
                self.assertIn("error", payload)
        decide.assert_not_called()


    @patch("app.decision_request")
    def test_choose_rejects_history_outside_the_system_grammar(self, decide):
        for body in (
            {"current": "MI", "history": ["MI", "M1I"]},
            {"current": "MI", "history": [""]},
            {"system": "algebra", "current": "2*x=4", "history": ["2*x=4", "x*x=4"]},
            {"current": "MI", "history": ["MI"] * 1025},
        ):
            with self.subTest(body=body):
                status, payload = self.request("POST", "/api/choose", body)
                self.assertEqual(status, 400)
                self.assertIn("error", payload)
        decide.assert_not_called()

    def test_static_files_are_served_with_query_strings(self):
        for path in ("/styles.css?cache=2", "/?refresh=1"):
            with self.subTest(path=path):
                connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
                try:
                    connection.request("GET", path)
                    response = connection.getresponse()
                    status = response.status
                    response.read()
                finally:
                    connection.close()
                self.assertEqual(status, 200)


class DecisionTraceTests(unittest.TestCase):
    @patch("app.require_compatible_ollama")
    def test_guidance_records_raw_choice_and_actual_filter(self, _compatible):
        response = io.BytesIO(json.dumps({"answers": {"next_move": {
            "choice": "A", "probabilities": {"A": 1, "B": 0},
        }}}).encode())
        with patch("app.urllib.request.urlopen", return_value=response):
            result = choose_move(
                "ollama", "nimble:latest", "guided", "MI", "MUI", ["MI"], legal_moves("MI"),
            )
        group = result["rounds"][0]["groups"][0]
        self.assertEqual(group["raw_choice"], "move-0")
        self.assertEqual(group["winner"], "move-1")
        self.assertTrue(group["overridden"])
        self.assertEqual(result["override_count"], 1)
        self.assertEqual(result["provider_calls"], 1)
        self.assertEqual(result["move"]["result"], "MII")
        self.assertEqual(group["probabilities"], {"move-0": 1, "move-1": 0})
        self.assertIn("growth-only traps", group["selection"]["filters"][-1]["reason"])
        self.assertEqual(group["selection"]["filters"][-1]["eligible"], ["move-1"])
        score = group["selection"]["scores"]["move-1"]
        self.assertEqual(score["total"], score["heuristic"] + score["probability_adjustment"])

    @patch("app.require_compatible_ollama")
    def test_tournament_keeps_independent_group_distributions(self, _compatible):
        def respond(request, **_kwargs):
            keys = list(json.loads(request.data)["questions"]["next_move"]["criteria"])
            return io.BytesIO(json.dumps({"answers": {"next_move": {
                "choice": keys[0],
                "probabilities": {key: 1.0 / len(keys) for key in keys},
            }}}).encode())

        moves = legal_moves("M" + "I" * 30)
        with patch("app.urllib.request.urlopen", side_effect=respond):
            result = choose_move("ollama", "nimble", "model", "M" + "I" * 30, "MU", [], moves)
        self.assertEqual(result["provider_calls"], 3)
        first_groups = result["rounds"][0]["groups"]
        self.assertEqual([len(group["candidates"]) for group in first_groups], [26, 4])
        self.assertEqual(
            [id_ for group in first_groups for id_ in group["candidates"]],
            [move["id"] for move in moves],
        )
        for round_ in result["rounds"]:
            self.assertNotIn("probabilities", round_)
            for group in round_["groups"]:
                self.assertAlmostEqual(sum(group["probabilities"].values()), 1)
                self.assertEqual(group["raw_choice"], group["winner"])
                self.assertFalse(group["overridden"])
                self.assertEqual(group["probability_scope"], "within this group only")
        self.assertEqual(result["rounds"][1]["groups"][0]["candidates"],
                         [group["winner"] for group in first_groups])

    @patch("app.decision_request")
    def test_single_candidate_has_no_fabricated_model_choice_or_probability(self, decide):
        result = choose_move("ollama", "nimble", "guided", "MIU", "MU", [], legal_moves("MIU"))
        decide.assert_not_called()
        group = result["rounds"][0]["groups"][0]
        self.assertFalse(group["requested"])
        self.assertIsNone(group["raw_choice"])
        self.assertEqual(group["probabilities"], {})
        self.assertEqual(result["provider_calls"], 0)
        self.assertEqual(group["winner"], result["move"]["id"])

    @patch("app.require_compatible_ollama")
    def test_partial_tournament_failure_preserves_completed_group_evidence(self, _compatible):
        response = io.BytesIO(json.dumps({"answers": {"next_move": {
            "choice": "A", "probabilities": {"A": 1},
        }}}).encode())
        with patch("app.urllib.request.urlopen", side_effect=[response, TimeoutError()]):
            with self.assertRaises(DecisionError) as failure:
                choose_move(
                    "ollama", "nimble", "model", "M" + "I" * 30, "MU", [],
                    legal_moves("M" + "I" * 30),
                )
        trace = failure.exception.decision
        self.assertEqual(trace["provider_calls"], 2)
        self.assertEqual(trace["rounds"][0]["groups"][0]["winner"], "move-0")
        self.assertEqual(trace["rounds"][0]["winners"], 1)
        self.assertIn("timed out", trace["rounds"][0]["groups"][1]["error"])
        self.assertNotIn("move", trace)

    @patch("app.require_compatible_ollama")
    def test_provider_error_body_is_not_copied_into_persistent_evidence(self, _compatible):
        error = urllib.error.HTTPError(
            "http://localhost/test", 401, "Unauthorized", {},
            io.BytesIO(b"sensitive-provider-response-placeholder"),
        )
        with patch("app.urllib.request.urlopen", side_effect=error):
            with self.assertRaises(DecisionError) as failure:
                choose_move("ollama", "nimble", "model", "MI", "MU", [], legal_moves("MI"))
        serialized = json.dumps(failure.exception.decision)
        self.assertNotIn("sensitive-provider-response-placeholder", serialized)
        self.assertIn("HTTP 401", serialized)

    def test_explanations_do_not_change_policy_choices(self):
        for current in ("MI", "MII", "MIII", "MIIII", "MIIIUU"):
            moves = legal_moves(current)
            for policy in ("guided", "model"):
                with self.subTest(current=current, policy=policy):
                    evidence = {}
                    args = (policy, current, "MUI", [current], moves, moves[0], {}, 64)
                    self.assertEqual(select_move(*args), select_move(*args, evidence))
                    self.assertIn("reason", evidence)


if __name__ == "__main__":
    unittest.main()
