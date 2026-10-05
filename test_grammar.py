import unittest

import grammar


def reduce_by(state, label_part):
    move = next(m for m in state["moves"] if label_part in m["label"])
    return grammar.describe(move["result"])


class GrammarParserTests(unittest.TestCase):
    def test_sentences_normalize_to_leaf_forests(self):
        for text, expected in (
            ("the man saw the dog", "[Det the] [N man] [V saw] [Det the] [N dog]"),
            ("  the   dog  ", "[Det the] [N dog]"),
            ("the", "[Det the]"),
        ):
            with self.subTest(text=text):
                state = grammar.describe(text)
                self.assertEqual(state["current"], expected)
                self.assertEqual(
                    grammar.format_forest(grammar.parse_state(expected)), expected)
                self.assertEqual(
                    grammar.parse_state(expected), grammar.parse_state(state["current"]))

    def test_solved_forests_parse_and_round_trip(self):
        text = ("[S [NP [Det the] [N man]] "
                "[VP [VP [V saw] [NP [Det the] [N dog]]] "
                "[PP [P with] [NP [Det the] [N telescope]]]]]")
        state = grammar.describe(text)
        self.assertTrue(state["solved"])
        self.assertEqual(state["solution_kind"], "parsed")
        self.assertEqual(state["current"], text)
        self.assertEqual(state["moves"], [])
        self.assertEqual(state["progress"], 1)

    def test_invalid_inputs_are_rejected(self):
        for text in (
            "", None, 12, [], "the man xyz", "[", "[NP]", "[NP [Det the]]",
            "[Det the", "[Det the] [N man", "[N the]", "[S [NP the man]]",
            "the [N dog]", "[VP]",
        ):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    grammar.parse_state(text)

    def test_representation_limits_are_explicit(self):
        with self.assertRaises(grammar.GrammarLimitError):
            grammar.parse_sentence(" ".join(["the"] * (grammar.MAX_WORDS + 1)))
        with self.assertRaises(ValueError):
            grammar.parse_sentence("the [Det the] man")
        state = grammar.describe("the man saw the dog")
        self.assertEqual(state["limits"], {
            "characters": grammar.MAX_CHARS, "nodes": grammar.MAX_NODES,
            "depth": grammar.MAX_DEPTH, "words": grammar.MAX_WORDS,
        })
        self.assertEqual(state["omitted_for_limits"], 0)


class GrammarRewriteTests(unittest.TestCase):
    def test_menu_lists_every_reduction_at_every_position(self):
        state = grammar.describe(grammar.DEFAULT_SENTENCE)
        self.assertEqual([m["position"] for m in state["moves"]], [0, 3, 6])
        self.assertTrue(all(m["label"].startswith("Reduce at") for m in state["moves"]))
        self.assertFalse(state["solved"])
        self.assertEqual(state["solution_kind"], "incomplete")
        self.assertEqual(state["progress"], 8)

        # A mid-derivation forest with several distinct legal reductions.
        state = grammar.describe(
            "[NP [Det the] [N man]] [V saw] [NP [Det the] [N dog]] "
            "[PP [P with] [NP [Det the] [N telescope]]]"
        )
        self.assertEqual(
            [m["label"] for m in state["moves"]],
            ["Reduce at 1: VP → V NP", "Reduce at 2: NP → NP PP"],
        )

    def test_every_move_preserves_the_yield_and_round_trips(self):
        for text in (
            grammar.DEFAULT_SENTENCE,
            "the man and the dog saw the pizza",
            "[NP [Det the] [N man]] [V saw] [NP [Det the] [N dog]] [P with] [Det the] [N telescope]",
        ):
            with self.subTest(text=text[:40]):
                state = grammar.describe(text)
                words = grammar.yield_words(grammar.parse_state(state["current"]))
                for move in state["moves"]:
                    result = grammar.parse_state(move["result"])
                    self.assertEqual(grammar.format_forest(result), move["result"])
                    self.assertEqual(grammar.yield_words(result), words)
                    self.assertEqual(move["progress"], len(result))
                    self.assertEqual(move["solved"], grammar.is_solved(result))
                    self.assertEqual(move["completable"], grammar.completable(result))

    def test_attachment_ambiguity_yields_two_distinct_complete_parses(self):
        state = grammar.describe(grammar.DEFAULT_SENTENCE)
        self.assertEqual(state["parse_count"], 2)
        self.assertFalse(state["parse_count_capped"])

        # VP attachment: [S [NP man] [VP [VP saw dog] [PP ...]]]
        state = reduce_by(state, "at 6")   # NP the telescope
        state = reduce_by(state, "PP")     # PP with the telescope
        state = reduce_by(state, "at 3")   # NP the dog
        state = reduce_by(state, "VP → V NP")
        state = reduce_by(reduce_by(state, "VP → VP PP"), "at 0")
        vp_parse = reduce_by(state, "S → NP VP")
        self.assertTrue(vp_parse["solved"])
        self.assertIn("[VP [VP [V saw]", vp_parse["current"])

        # NP attachment: [S [NP man] [VP [V saw] [NP [NP dog] [PP ...]]]]
        state = grammar.describe(grammar.DEFAULT_SENTENCE)
        state = reduce_by(state, "at 6")
        state = reduce_by(state, "PP")
        state = reduce_by(state, "at 3")   # NP the dog
        state = reduce_by(state, "NP → NP PP")
        state = reduce_by(reduce_by(state, "VP → V NP"), "at 0")
        np_parse = reduce_by(state, "S → NP VP")
        self.assertTrue(np_parse["solved"])
        self.assertIn("[NP [NP [Det the] [N dog]] [PP", np_parse["current"])

        self.assertNotEqual(vp_parse["current"], np_parse["current"])
        self.assertEqual(vp_parse["parse_count"], 2)

    def test_greedy_reduction_can_dead_end(self):
        state = grammar.describe(grammar.DEFAULT_SENTENCE)
        for label_part in ("at 0", "at 5", "PP", "at 2", "VP → V NP"):
            state = reduce_by(state, label_part)
        # [NP the man] [VP saw the dog] [PP with the telescope]
        dead_end = reduce_by(state, "S → NP VP")
        self.assertFalse(dead_end["solved"])
        self.assertEqual(dead_end["moves"], [])
        self.assertEqual(dead_end["parse_count"], 2)

        # The same state had a productive alternative: attach the PP into the VP.
        alternative = reduce_by(state, "VP → VP PP")
        self.assertTrue(alternative["moves"])
        witness, final = grammar.reference_parse(alternative["current"])
        self.assertTrue(final.startswith("[S "))

    def test_reference_parse_witnesses_and_rejects_unparseable_sentences(self):
        path, final = grammar.reference_parse(grammar.DEFAULT_SENTENCE)
        self.assertTrue(final.startswith("[S "))
        self.assertTrue(grammar.describe(final)["solved"])
        self.assertTrue(all(m["completable"] for step in path for m in [step["move"]]))

        path, final = grammar.reference_parse("the man saw")
        self.assertEqual((path, final), ([], None))

    def test_parse_counts_are_chart_verified(self):
        for sentence, count in (
            (grammar.DEFAULT_SENTENCE, 2),
            ("the dog saw the pizza", 1),
            ("the man saw", 0),
            ("the man and the dog saw the pizza", 1),
        ):
            with self.subTest(sentence=sentence):
                state = grammar.describe(sentence)
                self.assertEqual(state["parse_count"], count)
                self.assertEqual(state["parse_count_capped"], False)


class GrammarPolicyTests(unittest.TestCase):
    def test_model_policy_preserves_raw_choice(self):
        state = grammar.describe(grammar.DEFAULT_SENTENCE)
        raw = state["moves"][2]
        picked = grammar.select_move(
            "model", state["current"], grammar.GOAL, [],
            state["moves"], raw, {}, 512,
        )
        self.assertEqual(picked["id"], raw["id"])

    def test_guided_avoids_dead_end_reductions(self):
        state = grammar.describe(
            "[NP [Det the] [N man]] [VP [V saw] [NP [Det the] [N dog]]] "
            "[PP [P with] [NP [Det the] [N telescope]]]"
        )
        self.assertEqual([m["label"] for m in state["moves"]],
                         ["Reduce at 0: S → NP VP", "Reduce at 1: VP → VP PP"])
        self.assertEqual([m["completable"] for m in state["moves"]], [False, True])
        explanation = {}
        picked = grammar.select_move(
            "guided", state["current"], grammar.GOAL, [],
            state["moves"], state["moves"][0],
            {m["id"]: 0.9 for m in state["moves"]}, 512, explanation,
        )
        self.assertEqual(picked["label"], "Reduce at 1: VP → VP PP")
        self.assertEqual(
            explanation["filters"][-1]["reason"],
            "Prefer reductions that keep a complete parse reachable.",
        )

    def test_guided_budget_filter_records_and_applies(self):
        state = grammar.describe("the dog saw the pizza")
        explanation = {}
        picked = grammar.select_move(
            "guided", state["current"], grammar.GOAL, [],
            state["moves"], state["moves"][0],
            {m["id"]: 0.0 for m in state["moves"]}, 64, explanation,
        )
        self.assertLessEqual(len(picked["result"]), 64)
        self.assertEqual(
            explanation["filters"][0]["reason"], "Prefer moves within the length budget.")

    def test_guided_reaches_a_complete_parse_of_the_default_sentence(self):
        state = grammar.describe(grammar.DEFAULT_SENTENCE)
        history = [state["current"]]
        steps = 0
        while not state["solved"]:
            move = grammar.select_move(
                "guided", state["current"], grammar.GOAL, history,
                state["moves"], state["moves"][0],
                {m["id"]: 0.0 for m in state["moves"]}, 512,
            )
            history.append(move["result"])
            state = grammar.describe(move["result"])
            steps += 1
            self.assertLess(steps, 20)
        self.assertEqual(state["progress"], 1)
        self.assertLessEqual(steps, 12)


if __name__ == "__main__":
    unittest.main()
