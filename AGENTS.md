# AGENTS.md

Guidance for coding agents and contributors working on MIU × Jev.

## Project in one paragraph

MIU × Jev is a dependency-free Python web app for Hofstadter's MIU formal
system. The Python engine enumerates every legal rewrite from the current
string. A decision provider—local Ollama/Nimble by default, or hosted
TypeSafe/Jev when configured—may choose only from that generated menu. The
model supplies strategy; deterministic code supplies validity.

## Commands

```powershell
# Run
python app.py

# Test
python -m unittest -v

# Syntax checks
python -m py_compile app.py test_app.py
node --check web\app.js
```

The app listens at <http://127.0.0.1:8765> by default. It intentionally has no
Python package dependencies and no frontend build step.

## File map

```text
app.py          MIU rules, provider clients, HTTP API, static file server
test_app.py     unit tests for rules, provider limits, and configuration
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
5. **Ollama remains the default.** TypeSafe is an optional secondary provider;
   the project must still work without an API key.

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

### Ollama / Nimble

- Endpoint: `http://127.0.0.1:11434/v1/systemone`
- Default model: `nimble:latest`
- Choice limit: 26
- Local and keyless
- Supports `keep_alive`; TypeSafe does not

### TypeSafe / Jev

- Endpoint: `https://api.typesafe.ai/v1/systemone`
- Default model: `jev-latest`
- Choice limit: 255
- Requires `TYPESAFE_API_KEY`
- Authentication uses `Authorization: Bearer <key>`

When the move count exceeds a provider's choice limit, `choose_move` runs a
tournament. Every original legal move must remain eligible. A provider with a
larger limit should not be forced through the 26-choice Ollama grouping.

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
from TypeSafe to Ollama or vice versa.

## Frontend gotchas

- Provider availability comes from `/api/health`.
- Selecting a provider updates its default model.
- Disable TypeSafe in the selector when the server has no key.
- The UI is intentionally framework-free. Do not introduce a build tool for a
  small change.
- Auto-run must remain stoppable and must stop on an API error, no legal moves,
  or reaching the target.
- Keep manual selection, undo, reset, probabilities, and derivation history
  working for both providers.
- Avoid putting secrets or provider authorization logic in `web/app.js`.

## Testing expectations

Add or update tests when changing:

- any MIU rule or occurrence-scanning behavior;
- provider selection or limits;
- tournament grouping;
- TypeSafe credential requirements;
- request or response mapping; or
- input validation.

At minimum, run:

```powershell
python -m unittest -v
python -m py_compile app.py test_app.py
node --check web\app.js
```

For provider changes, also perform one live `/api/choose` request for each
configured provider. Use harmless MIU state only. Never place a real key in a
command, test fixture, source file, log, or commit.

## Documentation

Keep `README.md` accurate when changing provider setup, privacy behavior, the
UI, endpoints, or commands. Preserve the distinction among:

- TypeSafe's hosted **Jev** model;
- Bespoke Labs' open **Nimble** model; and
- Ollama's local **System One API** used to run Nimble.

Do not imply that schema-constrained output guarantees a good decision. It
guarantees an allowed answer shape; the chosen legal move can still be
strategically poor.
