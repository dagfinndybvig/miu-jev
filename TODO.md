# TODO

Open threads from the lambda benchmark work (2 October 2026) and the grammar
work (5 October 2026), highest value first.

## Benchmark experiments

1. **Menu-order control as a report arm.** The reversed-menu probe (both models
   avoided the Ω redex even when it was listed first) was ad-hoc and is not part
   of the checked-in evidence. Add a `--menu-order` arm (shuffled or reversed)
   so position bias is controlled reproducibly inside reports, not by hand.
2. **Wrong-hint curriculum.** Annotate the Ω redex as recommended in hint-on
   menus. A model that follows the bad hint is deferring to the teacher; one
   that overrides it is exercising judgment. This is the sharpest test of the
   textbook-versus-exercises distinction.
3. **Menus that stress tournaments.** Every current lambda menu has at most
   three options, so the 26-choice tournament path is untested for lambda.
   Generate terms with dozens of redexes and majority-losing menus (many
   diverging options, few good ones) so strategy is stressed, not sampled.
4. **Novel-term generator.** Canonical Church arithmetic is plausibly verbatim
   in training corpora, so those cases may measure recall. Add seeded
   compositions from the grammar that no textbook contains, so the exercises
   stay ahead of the curriculum the models already read.

## Lower priority

5. **Algebra and grammar benchmark modes.** `--system` supports miu and lambda;
   algebra and grammar have no controlled comparison yet.
6. **Stateless-model caveat.** The models never learn within a session; keep
   this stated wherever results are interpreted (the "child who already
   learned" limitation).

## Grammar experiments

7. **Attachment-preference probe.** Ambiguous sentences have several complete
   parses and every one is a solved state; which one a model steers toward is
   a semantics preference, not a syntax requirement. Measure whether the
   choice between VP and NP attachment is consistent across sentences, menu
   orders, and providers.
   Ad-hoc live probe, 5 October 2026 (not checked-in evidence): on
   `the man saw the dog with the telescope`, both Nimble (local) and Jev
   (hosted) chose VP attachment in every trial, under both model-only and
   guided policies. Nimble was bit-identical across trials and chose
   `VP → V NP` over `NP → NP PP` at 0.93; Jev sampled slightly and committed
   earlier at 0.50–0.94, sometimes before the PP was even built. Both match
   the corpus default for instrument PPs, but the sentence is verbatim in
   every linguistics textbook, so this may measure recall (see item 4).
   Run it on novel sentences before drawing conclusions.
8. **Dead-end avoidance.** Curate sentences whose greedy-looking first
   reduction strands a modifier (the `VP → V NP` then `S → NP VP` trap) and
   measure model-only dead-end rates against the chart-completable guided
   policy and `reference_parse`. Large coordination sentences would also give
   menus big enough to stress the 26-choice tournament path.
