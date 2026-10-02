# AGENTS.md

Guidance for coding agents and contributors working on MIU × Jev.

## Project in one paragraph

MIU × Jev is a dependency-free Python web app for Hofstadter's MIU formal
system. The Python engine enumerates every legal rewrite from the current
string. A decision provider—local Ollama 0.35.0+/Nimble by default, or hosted
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
python -m py_compile app.py test_app.py
node --check web\app.js
node --test test_web.js
```

The app listens at <http://127.0.0.1:8765> by default. It intentionally has no
Python package dependencies and no frontend build step.

## File map

```text
app.py          MIU rules, provider clients, HTTP API, static file server
test_app.py     unit tests for rules, provider limits, and configuration
test_web.js     browser-state regression tests using Node.js built-ins
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
2. **The model only selects.** A provider must never generate the next MIU
   string directly. Map its selected option back to a server-generated move.
3. **Every derivation step is inspectable.** Keep rule, position, result, and
   history visible enough to audit.
4. **Manual and model moves use the same menu.** Do not create a privileged AI
   path that bypasses validation.
5. **Ollama 0.35.0+ remains the default.** TypeSafe is an optional secondary
   provider; the project must still work without an API key.
6. **Safety budgets are not formal rules.** Auto-run may stop for length,
   steps, or cycles, but the legal menu must still show every MIU rewrite.
7. **Guidance is strategy, not legality.** The default guided policy may rank
   or prefer legal moves, but it must never synthesize or apply a non-MIU move.

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

## Provider contract

Both providers receive the same state:

- current string;
- target string;
- recent derivation;
- the candidate legal moves; and
- the modulo-three invariant as context.

They return a choice and probabilities. Keep provider-specific behavior behind
`decision_request`.

The default `guided` policy is intentionally reduction-first. If a group has
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

Validate all public inputs. MIU strings must be non-empty and contain only
`M`, `I`, and `U`. Provider names are restricted to `ollama` and `typesafe`.
Surface provider and validation failures explicitly; do not silently fall back
from TypeSafe to Ollama 0.35.0+ or vice versa.

## Frontend gotchas

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
- Auto-run must preflight the modulo-three invariant. Exploratory override is
  enabled by default so the `MI → MU` experiment runs out of the box; show a
  clear impossibility warning and rely on safety budgets. When the user
  disables the override, refuse a provably unreachable target.
- The default model-move length budget is 64 characters. Pass it to
  `/api/choose` as `max_length`; guided selection should prefer an in-budget
  move whenever one exists.
- Auto-run safety limits apply before a move is committed. Manual selection
  remains available for every legal move within the server's absolute
  8,192-character input bound.
- Bind every provider response to the current string used for its request.
  Disable manual moves while a decision or auto-run is active, and discard a
  delayed response if the current string changed before it can be applied.
- Keep manual selection, undo, reset, probabilities, and derivation history
  working for both providers.
- Avoid putting secrets or provider authorization logic in `web/app.js`.

## Testing expectations

Add or update tests when changing:

- any MIU rule or occurrence-scanning behavior;
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
python -m py_compile app.py test_app.py
node --check web\app.js
node --test test_web.js
```

For provider changes, also perform one live `/api/choose` request for each
configured provider. Use harmless MIU state only. Never place a real key in a
command, test fixture, source file, log, or commit.

## Documentation

Keep `README.md` accurate when changing provider setup, privacy behavior, the
UI, endpoints, or commands. Preserve the distinction among:

- TypeSafe's hosted **Jev** model;
- Bespoke Labs' open **Nimble** model; and
- Ollama **0.35.0+** and its local **System One API** used to run Nimble.

Do not imply that schema-constrained output guarantees a good decision. It
guarantees an allowed answer shape; the chosen legal move can still be
strategically poor.
