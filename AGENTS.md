# AGENTS.md

Guidance for coding agents and contributors working on MIU × Jev.

## Project in one paragraph

MIU × Jev is a dependency-free Python web app with a shared menu for Hofstadter's
MIU system and exact single-variable algebra. The Python engines generate
all MIU rewrites or a finite declared algebra rewrite vocabulary.
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
python -m py_compile app.py algebra.py test_app.py test_algebra.py benchmark.py test_benchmark.py
node --check web\app.js
node --test test_web.js
```

The app listens at <http://127.0.0.1:8765> by default. It intentionally has no
Python package dependencies and no frontend build step.

## File map

```text
app.py          MIU rules, provider clients, HTTP API, static file server
algebra.py      exact linear-equation parser, rewrite menu, and guidance
test_algebra.py exact equivalence, limits, policies, and shared-provider tests
test_app.py     unit tests for rules, provider limits, and configuration
test_web.js     browser-state regression tests using Node.js built-ins
benchmark.py    controlled baseline/provider comparisons and bounded BFS
test_benchmark.py benchmark witness, budget, and metric tests
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
2. **The model only selects.** A provider must never generate the next string
   or equation directly. Map its selected option back to a server-generated move.
3. **Every derivation step is inspectable.** Keep rule, position, result, and
   history visible enough to audit.
4. **Manual and model moves use the same menu.** Do not create a privileged AI
   path that bypasses validation.
5. **Ollama 0.35.0+ remains the default.** TypeSafe is an optional secondary
   provider; the project must still work without an API key.
6. **Safety budgets are not formal rules.** Auto-run may stop for length,
   steps, or cycles, but the legal menu must still show every MIU rewrite.
7. **Guidance is strategy, not legality.** The default guided policy may rank
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

The default MIU `guided` policy is intentionally reduction-first. If a group has
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
- `POST /api/choose` accepts `current`, `goal`, `provider`, `model`, and
  `history`; it recomputes moves before asking the provider.
- Both POST endpoints accept `system` (`miu` by default, or `algebra`).
  Algebra returns normalized equations and server analysis. Its only goal is
  `Isolate x`, and its `max_length` range is 8–512. Preserve omitted-system MIU
  compatibility.

Validate all public inputs. MIU strings must be non-empty and contain only
`M`, `I`, and `U`. Provider names are restricted to `ollama` and `typesafe`.
Surface provider and validation failures explicitly; do not silently fall back
from TypeSafe to Ollama 0.35.0+ or vice versa.

## Frontend gotchas

- The example selector starts a new derivation while retaining provider/model
  settings and the shared journal. Validate a new equation before replacing
  the active state. Algebra reset uses the loaded initial equation.
- Bind asynchronous menus and decisions to system as well as revision/current.
  Disable example switching and equation loading during decisions and auto-run.
- Algebra uses server solved/progress metadata, not edit distance or modulo
  three. Keep identities and contradictions distinct from failure.
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
- switching examples, loading equations, or cross-example journal behavior;
- provider selection or limits;
- guided or model-only selection policy;
- heuristic scoring and reduction-first behavior;
- tournament grouping;
- TypeSafe credential requirements;
- request or response mapping; or
- input validation.

At minimum, run:

```powershell
python -m unittest -v
python -m py_compile app.py algebra.py test_app.py test_algebra.py benchmark.py test_benchmark.py
node --check web\app.js
node --test test_web.js
```

For provider changes, also perform one live `/api/choose` request for each
configured provider, covering both examples when shared routing changes.
Use harmless MIU states or sample algebra equations only. Never place a real key in a
command, test fixture, source file, log, or commit.

`python benchmark.py --output baseline-results.json` runs MIU-only keyless baselines.
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
