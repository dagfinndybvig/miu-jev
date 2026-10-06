# TODO

Open threads from the lambda benchmark work (2 October 2026) and the grammar
work (5 October 2026), highest value first.

## Benchmark experiments

1. **Menu-order control as a report arm.** Implemented 6 October 2026:
   `--menu-order fixed|reversed|shuffled` presents provider-facing menus
   reversed or in a per-state seeded shuffle, records the presented order in
   trial evidence, and keeps baselines on the fixed server order. The ad-hoc
   reversed-menu probe (both models avoided the Ω redex even when it was
   listed first) is now measured as checked-in evidence: the 6 October 2026
   fixed and shuffled lambda reports (72 trials each, both providers,
   targets 5, repeats 2). Success was identical under both orders; raw
   first-position picks fell from 68/84 (fixed) to 30/85 (shuffled), near
   chance for menus of two to three options, and applied move sequences
   matched across orders in 6/6 reachable trials for Jev and 4-6/6 for
   Nimble, without changing any outcome. Both providers choose by redex
   identity, not slot position. The arm stays blunt until item 3 lands.
2. **Wrong-hint curriculum.** Implemented and measured 6 October 2026:
   `--wrong-hint` adds provider arms whose hint-on menus annotate the
   diverging Ω self-loop contraction as recommended (descriptive text
   only; legality stays server-owned). Measured in the checked-in
   wrong-hint report (lambda, shuffled menus, both providers, repeats 3):
   zero deference — neither Nimble nor Jev, model-only or guided, followed
   the recommended self-loop in any trap-state decision, even when it was
   presented first; every trap trial still found the normal form. Both
   models exercise judgment over the teacher here, so the
   textbook-versus-exercises distinction stands on recall, not deference.
   Caveat: one trap shape, one bad hint; a curriculum of wrong hints over
   novel terms (item 4's generator) would sharpen it further.
3. **Menus that stress tournaments.** Implemented and measured 6 October
   2026: `--tournament-terms N` adds hand-crafted majority-losing cases —
   27-move menus holding one 2-step outer discard plus 18 instant-cycle Ω
   self-loops (hard) or 26 budget-wasting identities (soft). Measured in
   the checked-in fixed and shuffled tournament reports (both providers,
   repeats 3): Jev chose the discard in 12/12 trials per run under both
   policies, in exactly the two reference steps, and under shuffled order
   the discard was never the first presented slot — content, not position.
   Ollama failed explicitly on all tournament trials (HTTP 400/413): a
   26-move group needs at least ~17KB even with compact criteria, while
   ~11KB was accepted, so the 26-choice tournament path is unreachable in
   practice on the local provider — a provider ceiling worth stating
   wherever tournaments are interpreted. The hosted endpoint accepted
   ~75KB and rejected ~117KB during pool calibration, which sized the
   compact soft term. Remaining: an algebra or grammar analog (items 5
   and 8) if those menus can stress grouping under smaller request bodies.
4. **Novel-term generator.** Implemented 6 October 2026: `--novel-terms N`
   replaces up to targets - 2 curated reachable slots with seeded
   compositions — random operand order, nested operator trees, identity
   applications, constant wrappers — each verified to normalize within the
   reference-step bound and distinct from the curated pool. Canonical Church
   arithmetic is plausibly verbatim in training corpora, so curated cases may
   measure recall. Remaining: run the novel pool against both providers and
   compare against the curated reachable success rates.

## Lower priority

5. **Algebra and grammar benchmark modes.** Implemented and measured 6
   October 2026: `--system algebra` and `--system grammar` run the shared
   comparison protocol with greedy-guided and chart-guided reference
   witnesses (benchmark-results-algebra.json and -grammar.json, both
   providers). Algebra: every arm solved every equation, identity, and
   contradiction at reference-optimal steps; random exposed the traps
   (cycles, step budgets). Grammar: every arm completed every parseable
   sentence; unparseable sentences dead-end everywhere and stay out of
   success denominators.
6. **Stateless-model caveat.** Done 6 October 2026: the caveat is stated
   in the README's controlled-comparisons intro and its measured-sample
   sections — providers never learn within or across sessions, so every
   result is fresh selection, not learning.
   The child-who-already-learned limitation is stated wherever results are
   interpreted; it is a caveat, not something a benchmark can measure away.

## Grammar experiments

7. **Attachment-preference probe.** Measured 6 October 2026 on novel
   sentences (checked-in fixed and shuffled attachment reports, both
   providers, repeats 3, four seeded ambiguous compositions no textbook
   contains): both Nimble and Jev chose VP attachment in 12/12 trials per
   arm — model-only and guided — across all sentences and both menu orders,
   while the seeded random baseline split 4/12 VP vs 8/12 NP, near chance
   for two parses. Ambiguous sentences have several complete parses and
   every one is a solved state, so this is a semantics preference, not a
   syntax requirement. The 5 October ad-hoc probe on the verbatim textbook
   sentence agreed (VP in every trial), so the preference survives the
   recall objection. Nuance: the compositions reuse the toy lexicon, so a
   general instrumental-PP prior cannot be excluded — a semantics claim
   this experiment cannot and need not settle. The menu-order control
   confirms the choice is content-driven, not positional.
8. **Dead-end avoidance.** Measured 6 October 2026 (checked-in grammar
   report): the curated dead-end sentence `the man saw the dog and the
   telescope` is fully parseable, but the greedy-looking VP-then-S path
   strands the coordination with no legal move left. Model-only dead-end
   rates were 0/3 for both Nimble and Jev — both avoided the trap under
   model-only and guided at reference steps — while the seeded random
   baseline dead-ended 1/3. Dead ends are recorded as outcomes, never
   proofs about the sentence. Note: toy-fragment menus stay small (at most
   about seven moves at leaf states for sentences of at most 16 words), so
   grammar cannot stress the 26-choice tournament path; that stress stays
   lambda-only (see item 3).
