# AGENTS.md

Guidance for coding agents and contributors working on Formalism × Jev.

## Project in one paragraph

Formalism × Jev is a dependency-free Python web app with a shared menu for four
formal systems: exact single-variable algebra, untyped lambda-calculus beta
reduction, bottom-up parsing of a toy English grammar fragment, and
Hofstadter's MIU system. The Python engines generate all
MIU rewrites, a finite declared algebra vocabulary, every lambda beta redex
at every position, or every legal reduction of adjacent constituents.
A decision provider—local Ollama 0.35.0+/Nimble by default, or hosted
TypeSafe/Jev when configured—may choose only from that generated menu. The
model supplies strategy; deterministic code supplies validity.

**Ollama 0.35.0 or later is mandatory for the local provider.** Earlier
versions do not expose the System One decision endpoint used by this project.

## Commands

```powershell
# Verify local-provider requirement (must be 0.35.0 or later)
ollama --version

# Run
python app.py

# Test
python -m unittest -v

# Syntax checks
python -m py_compile app.py algebra.py lambda_calc.py grammar.py test_app.py test_algebra.py test_lambda_calc.py test_grammar.py benchmark.py test_benchmark.py
node --check web\app.js
node --test test_web.js
```

The app listens at <http://127.0.0.1:8765> by default. It intentionally has no
Python package dependencies and no frontend build step.

## File map

```text
app.py          MIU rules, system routing, provider clients, HTTP API, static file server
algebra.py      exact linear-equation parser, rewrite menu, and guidance
lambda_calc.py exact lambda-term parser, beta redex menus, and guidance
grammar.py     toy-fragment forest parser, reduction menus, chart, and guidance
test_algebra.py exact equivalence, limits, policies, and shared-provider tests
test_lambda_calc.py lambda substitution, menus, limits, and policy tests
test_grammar.py grammar menus, yields, ambiguity, dead ends, and policies
test_app.py     unit tests for rules, provider limits, and configuration
test_web.js     browser-state regression tests using Node.js built-ins
benchmark.py    controlled baseline/provider comparisons and reference paths
test_benchmark.py benchmark witness, budget, and metric tests
benchmark-results.json measured MIU sample with per-trial evidence
benchmark-results-lambda.json measured lambda hint-ablation sample
web/index.html  page structure and settings
web/styles.css  responsive presentation
web/app.js      browser state, API calls, controls, and rendering
README.md       user documentation, provenance, and setup
.env.example    optional TypeSafe configuration template
```

## Core invariants

Preserve these properties in every change:

1. **The server owns legality.** Never accept a client-supplied move list as
   authoritative. Recompute legal moves from `current` in `app.py`.
2. **The model only selects.** A provider must never generate the next string,
   equation, or term directly. Map its selected option back to a
   server-generated move.
3. **Every derivation step is inspectable.** Keep rule, position, result, and
   history visible enough to audit.
4. **Manual and model moves use the same menu.** Do not create a privileged AI
   path that bypasses validation.
5. **Ollama 0.35.0+ remains the default.** TypeSafe is an optional secondary
   provider; the project must still work without an API key.
6. **Safety budgets are not formal rules.** Auto-run may stop for length,
   steps, or cycles, but the legal menu must still show every MIU rewrite.
7. **Guidance is strategy, not legality.** The MIU guided policy may rank
   or prefer legal moves, but it must never synthesize a move outside the
   selected system's server-generated menu.

## MIU rule gotchas

The axiom is `MI`, and strings contain only `M`, `I`, and `U`.

| Rule | Rewrite |
|---|---|
| 1 | If the string ends in `I`, append `U`. |
| 2 | For `Mx`, produce `Mxx`. |
| 3 | Replace any occurrence of `III` with `U`. |
| 4 | Delete any occurrence of `UU`. |

Important details:

- Rule 2 duplicates everything after the first `M`; it does not duplicate the
  `M`.
- Rules 3 and 4 apply at a specific position. Different positions are
  different legal moves even when they happen to produce the same result.
- Pattern discovery must allow overlapping occurrences. For example, `MIIII`
  contains `III` starting at positions 2 and 3 in one-based notation.
- A legal rewrite may produce just `M`, as when Rule 4 changes `MUU` to `M`.
- Do not add semantic restrictions based on the target. The invariant explains
  why `MU` is unreachable from `MI`, but it must not suppress legal moves.
- The number of `I` symbols modulo 3 is a teaching aid, not a move validator.

## Algebra invariants

- Use exact `Fraction` arithmetic and the bounded syntax-tree parser in
  `algebra.py`; never `eval`, floating point, or a provider-generated equation.
- Support linear equations over rationals with one variable, `x`. Reject
  nonlinear products, variable denominators, zero division, and unsupported
  notation explicitly.
- The seven rule families are finite vocabulary, not all possible algebra.
  Every offered rewrite must preserve the exact solution set and round-trip
  through formatting/parsing without changing its syntax tree.
- Algebra limits are 512 characters, 128 nodes, depth below 24, and 128-bit
  numerators/denominators. Candidate construction belongs inside the
  limit-catching path: count omitted unrepresentable moves without discarding
  the valid remainder of the menu. Do not conflate these bounds with the
  separate execution-length budget.
- Goal recognition is server-owned: `x = rational`, or a numeric equality
  classifying an identity/contradiction. Do not apply MIU's invariant.
- Algebra guidance prefers in-budget, solved, then unvisited results where
  available, followed by structural-cost scoring and model probabilities.
  The raw model-only policy must remain available.
- Use the same provider transport, tournaments, and evidence format as MIU,
  but domain-specific prompts and selection heuristics.

## Lambda invariants

- Use the bounded syntax-tree parser in `lambda_calc.py`; never `eval`,
  floating point, or a provider-generated term. Syntax is variables a-z,
  `λ` or `\`, `.`, and parentheses; application is juxtaposition.
- A move's result is the contraction spliced back into the whole term at its
  marked position. Never return the bare contraction, which silently drops
  the surrounding context.
- The default example is Church addition, 1 + 2:
  `(\m.\n.\f.\x. m f (n f x)) (\f.\x. f x) (\f.\x. f (f x))`, which guided
  mode reduces to `λf.λx.f (f (f x))` in six steps.
- Every offered move is a single capture-avoiding beta contraction at a
  server-marked position. The server performs substitution; the provider only
  names a redex.
- Goal recognition is server-owned: a beta normal form, meaning no redex
  remains anywhere in the term. Normalization is undecidable in general, so
  budget stops must stay labeled inconclusive, never impossible.
- Lambda limits are 512 characters, 256 syntax nodes, and depth at most 96.
  Count omitted unrepresentable contractions without discarding the menu
  remainder, exactly as algebra does.
- Lambda guidance prefers in-budget, solved, then unvisited results, then
  scores structural progress, duplication cost, and outer position with model
  probabilities. The model-only policy must remain available.
- Use the same provider transport, tournaments, and evidence format as MIU and
  algebra, with lambda-specific prompts and selection heuristics.

## Grammar invariants

- Use the bounded forest parser in `grammar.py`; never `eval` or a
  provider-generated tree. States are bracketed parse forests
  (`[Det the] [N man]`, `[NP [Det the] [N man]]`) over a fixed toy lexicon;
  a plain starting sentence is also accepted and expands to leaf constituents.
  Sentences are at most 16 words; forests are bounded by 512 characters,
  256 syntax nodes, and depth 96.
- A move's result is the combined constituent spliced back into the whole
  forest at its marked position. Never return the bare combination.
- The word sequence (yield) never changes. Every offered move must preserve
  the yield exactly and round-trip through parsing/formatting.
- Every offered move is one grammar production applied to adjacent
  constituents at a server-marked position. Different positions are different
  legal moves even when they produce the same result. The server performs the
  splice; the provider only names a reduction.
- Goal recognition is server-owned: a single complete parse, meaning the whole
  forest is one `S` constituent. A state with no moves and no complete parse is
  a dead end of that derivation line (undo recovers); it is not a proof about
  the sentence.
- Ambiguity is reported, not resolved: `describe` chart-counts the complete
  parses of the sentence (`parse_count`, capped at 999). Two parses of the same
  sentence are both solved states.
- Candidate construction belongs inside the limit-catching path: count omitted
  unrepresentable reductions without discarding the valid remainder of the menu.
- Grammar guidance prefers in-budget, a completed parse, unvisited results,
  then chart-completable reductions, then fewer constituents, with model
  probabilities. `reference_parse` is the chart-guided witness. The
  model-only policy must remain available and can dead-end; that contrast is
  the experiment.
- Use the same provider transport, tournaments, and evidence format as the
  other systems, with grammar-specific prompts and selection heuristics.

## Provider contract

Both providers receive the same state:

- current state;
- target string or algebra goal;
- recent derivation;
- the candidate legal moves; and
- domain context: MIU's modulo-three invariant or algebra solution preservation.

They return a choice and probabilities. Keep provider-specific behavior behind
`decision_request`.

Decision evidence must retain raw provider choices separately from guided
winners. Keep probabilities scoped to each tournament group and round; never
merge them into a global distribution. Explanations describe actual policy
filters and scores, not inferred model reasoning. Singleton groups make no
provider call and must not invent a model probability.

The MIU `guided` policy is intentionally reduction-first. **Model only is the
default selection policy**; the guided policy must remain available. If a group has
any shortening moves, `select_move` must choose within that subset. Otherwise
it combines provider probabilities with novelty, contraction-opportunity, and
growth heuristics. It must also avoid a growth-only trap when a productive
alternative exists. `MIU` is the canonical trap: only Rule 2 applies, and
duplicating its alternating `IU` tail can never create `III` or `UU`. The
`model` policy must preserve the provider's raw choice for comparison.

### Ollama 0.35.0+ / Nimble

- Minimum Ollama version: **0.35.0**
- Endpoint: `http://127.0.0.1:11434/v1/systemone`
- Default model: `nimble:latest`
- Choice limit: 26
- Local and keyless
- Supports `keep_alive`; TypeSafe does not

Do not remove or weaken the runtime version check. `/api/health` must mark the
local provider unavailable when Ollama is older than 0.35.0, and
`decision_request` must fail explicitly rather than relying on an endpoint
404. When changing version parsing, cover stable and prerelease-style strings.

### TypeSafe / Jev

- Endpoint: `https://api.typesafe.ai/v1/systemone`
- Default model: `jev-latest`
- Choice limit: 255
- Requires `TYPESAFE_API_KEY`
- Authentication uses `Authorization: Bearer <key>`

When the move count exceeds a provider's choice limit, `choose_move` runs a
tournament. Every original legal move must remain eligible. A provider with a
larger limit should not be forced through the 26-choice Ollama 0.35.0+
grouping.

## Secrets and environment

Never print, return, commit, or send the TypeSafe key to the browser.

Configuration precedence is:

1. existing process environment;
2. project `.env`;
3. `~/.copilot/.env`.

`load_env_file` must not overwrite an existing environment variable. `.env`
and `.env.*` are ignored except for `.env.example`.

`GET /api/health` may report whether TypeSafe is configured, but must never
include the key or any fragment of it. Error messages must not echo request
headers.

## HTTP API

- `GET /api/health` returns provider metadata safe for the browser.
- `POST /api/moves` accepts `current` and returns server-generated legal moves.
- `POST /api/choose` accepts `current`, `goal`, `provider`, `model`, `policy`
  (defaulting to `model`), and
  `history`; it recomputes moves before asking the provider.
- Both POST endpoints accept `system` (`miu` by default, `algebra`,
  `lambda`, or `grammar`).
  Algebra returns normalized equations and server analysis. Its only goal is
  `Isolate x`, and its `max_length` range is 8–512. Lambda returns normalized
  terms with redex counts; its only goal is `Normal form`, with the same range.
  Grammar returns normalized parse forests with chart-counted `parse_count`;
  its only goal is `Complete parse`, with the same range.
  Preserve omitted-system MIU
  compatibility.

Validate all public inputs. MIU strings must be non-empty and contain only
`M`, `I`, and `U`. Provider names are restricted to `ollama` and `typesafe`.
Surface provider and validation failures explicitly; do not silently fall back
from TypeSafe to Ollama 0.35.0+ or vice versa.

## Frontend gotchas

- The app opens on a landing page offering Algebra × Jev (the main feature),
  Lambda × Jev, Grammar × Jev, and MIU × Jev (the historical inspiration).
  Launching uses the same loadExample
  path as the example selector; the launch buttons and example switching stay
  disabled while a launch or decision is pending, and the app views stay
  hidden until a launch succeeds. The header Menu button and Choose application
  return to the landing
  without discarding the derivation; Continue the current derivation resumes
  it. All are disabled during decisions and auto-run; the header button stays
  hidden while the landing is shown. A header Settings button opens the
  settings panel.
- The example selector starts a new derivation while retaining provider/model
  settings and the shared journal. Validate a new equation before replacing
  the active state. Algebra reset uses the loaded initial equation.
- Bind asynchronous menus and decisions to system as well as revision/current.
  Disable example switching and equation loading during decisions and auto-run.
- Algebra and lambda use server solved/progress metadata, not edit distance or
  modulo three. Keep identities and contradictions distinct from failure.
- Grammar uses server solved/parse-count metadata. An empty menu on an
  unsolved grammar state is a dead end: show the stuck notice, keep undo
  available, and never describe it as a proof about the sentence. Grammar
  parse forests run long; warn users to raise the length budget for
  auto-run rather than silently failing every model move.
- Provider availability comes from `/api/health`.
- Keep Ollama selected by default even when unavailable; hosted requests
  require an explicit provider switch.
- Selecting a provider updates its default model.
- Keep the header status indicator synchronized with the selected provider and
  editable model value.
- Disable TypeSafe in the selector when the server has no key.
- The UI is intentionally framework-free. Do not introduce a build tool for a
  small change.
- Auto-run must remain stoppable and must stop on an API error, no legal moves,
  reaching the target, exhausting its step budget, selecting an over-limit
  next string, selecting an already visited state, or exhausting its
  no-progress budget.
- MIU auto-run must preflight the modulo-three invariant. Exploratory override is
  enabled by default so the `MI → MU` experiment runs out of the box; show a
  clear impossibility warning and rely on safety budgets. When the user
  disables the override, refuse a provably unreachable target.
- The default model-move length budget is 64 characters. Pass it to
  `/api/choose` as `max_length`; guided selection should prefer an in-budget
  move whenever one exists.
- Auto-run safety limits apply before a move is committed. Manual selection
  remains available for every legal move within the server's absolute
  8,192-character MIU input bound or algebra's representation limits.
- Bind every provider response to the current string used for its request.
  Disable manual moves while a decision or auto-run is active, and discard a
  delayed response if the current string changed before it can be applied.
- Keep manual selection, undo, reset, probabilities, and derivation history
  working for both providers.
- Avoid putting secrets or provider authorization logic in `web/app.js`.
- Retain decision evidence across moves, undo/reset, and reload in the local
  journal. Export includes rejected decisions and stop reasons; storage
  failures must be visible and must not disable in-memory export.

## Testing expectations

Add or update tests when changing:

- any MIU rule or occurrence-scanning behavior;
- algebra parsing, rewrite equivalence, representation limits, or goal detection;
- lambda parsing, capture-avoiding substitution, redex menus, or normal-form detection;
- grammar parsing, yield preservation, reduction menus, dead ends, or parse counting;
- launching from, returning to, or resuming out of the landing page;
- switching examples, loading equations, or cross-example journal behavior;
- provider selection or limits;
- guided or model-only selection policy;
- heuristic scoring and reduction-first behavior;
- tournament grouping;
- TypeSafe credential requirements;
- request or response mapping; or
- input validation.
- lambda benchmark pools, normal-order witnesses, or hint-ablation arms.

At minimum, run:

```powershell
python -m unittest -v
python -m py_compile app.py algebra.py lambda_calc.py grammar.py test_app.py test_algebra.py test_lambda_calc.py test_grammar.py benchmark.py test_benchmark.py
node --check web\app.js
node --test test_web.js
```

For provider changes, also perform one live `/api/choose` request for each
configured provider, covering each system's example when shared routing changes.
Use harmless MIU states, sample algebra equations, or toy-fragment sentences
only. Never place a real key in a
command, test fixture, source file, log, or commit.

`python benchmark.py --output baseline-results.json` runs MIU-only keyless baselines.
`--system lambda` runs the curated lambda pool (Church arithmetic, traps,
growth, Omega) with normal-order reference paths; `--hint-ablation` adds
provider arms whose menus carry no precomputed annotations.
Model comparisons require explicit `--providers ollama` or
`--providers ollama typesafe`. Apply the same execution budgets to every
strategy, keep impossible-target exploration out of reachable success rates,
and retain failures and negative results. Source hashes in a published report
must match the implementation that produced it; do not relabel old measurements.

## Documentation

Keep `README.md` accurate when changing provider setup, privacy behavior, the
UI, endpoints, or commands. Preserve the distinction among:

- TypeSafe's hosted **Jev** model;
- Bespoke Labs' open **Nimble** model; and
- Ollama **0.35.0+** and its local **System One API** used to run Nimble.

Do not imply that schema-constrained output guarantees a good decision. It
guarantees an allowed answer shape; the chosen legal move can still be
strategically poor.
