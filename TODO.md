# TODO

Open threads from the lambda benchmark work (2 October 2026), highest value first.

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

5. **Algebra benchmark mode.** `--system` supports miu and lambda; algebra has
   no controlled comparison yet.
6. **Stateless-model caveat.** The models never learn within a session; keep
   this stated wherever results are interpreted (the "child who already
   learned" limitation).
