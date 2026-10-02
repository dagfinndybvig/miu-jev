<img width="658" height="1000" alt="geb2" src="https://github.com/user-attachments/assets/5a434868-854f-44a4-b2e5-bc93a3014b0a" />

# MIU × Jev

**MIU × Jev** is an experiment in constrained machine choice. A formal engine
generates every move permitted by the MIU system, and a decision model chooses
one move from that menu. Local **Ollama 0.35.0 or later** with Nimble is the
default; TypeSafe's hosted Jev API is an optional secondary provider. In either
mode, the model may decide *which* legal path to follow, but it can never
invent a rule, alter a string directly, or make an illegal move.

The result is a small, inspectable example of an AI operating inside hard
symbolic boundaries:

> The formal system determines what is possible. Jev determines what to try.

## Quick start

Clone the repository and enter it:

```powershell
git clone https://github.com/dagfinndybvig/miu-jev.git
Set-Location miu-jev
```

Choose one decision provider:

| Provider | Best for | Configuration | Data path |
|---|---|---|---|
| **Ollama 0.35.0+ + Nimble** | Private, offline-capable local exploration | Install Ollama 0.35.0 or later and `nimble:latest` | Decision inputs remain local |
| **TypeSafe + Jev** | Using the original hosted Jev model | Set `TYPESAFE_API_KEY` | Decision inputs are sent to TypeSafe |

The default local path is:

```powershell
ollama --version
ollama pull nimble
python app.py
```

The reported Ollama version must be **0.35.0 or later**. This minimum is
required because the local System One `/v1/systemone` endpoint is not available
in earlier releases.

For hosted Jev instead:

```powershell
$env:TYPESAFE_API_KEY = "your-key"
python app.py
```

Open <http://127.0.0.1:8765>. Use **Settings & rules** to switch providers.
The browser never receives either provider's credentials.

## Provenance: *Gödel, Escher, Bach*

The MIU system comes from Douglas R. Hofstadter's 1979 book
[*Gödel, Escher, Bach: An Eternal Golden Braid*][geb]. Hofstadter introduces it
near the beginning of the book as a deliberately tiny formal system. Its
symbols have no required meaning; they are manipulated according to explicit
typographical rules.

This simplicity is the point. MIU lets the reader experience the difference
between:

- working **inside** a formal system by applying its rules;
- reasoning **about** the system from outside it; and
- confusing a long, unsuccessful search with a proof of impossibility.

Those distinctions prepare the ground for the book's larger subjects:
self-reference, proof, meaning, recursion, and Gödel's incompleteness
theorems. MIU is not itself an incompleteness theorem, but it is a compact
model of the shift from mechanical symbol manipulation to metamathematical
reasoning.

[geb]: https://en.wikipedia.org/wiki/G%C3%B6del,_Escher,_Bach

## Douglas Hofstadter

[Douglas Richard Hofstadter][hofstadter-iu] (born 1945) is an American
cognitive scientist, physicist, and writer whose work moves freely among
mathematics, computer science, philosophy, language, music, and art. He studied
mathematics at Stanford and earned a doctorate in physics from the University
of Oregon. At Indiana University Bloomington he became a professor of cognitive
science and comparative literature and founded the
[Center for Research on Concepts and Cognition][crcc].

Hofstadter's central question is how mind and meaning can emerge from processes
that, at a lower level, appear mechanical and meaningless. Several ideas recur
throughout his research and writing:

- **self-reference and strange loops**—systems whose levels turn back upon and
  affect themselves;
- **analogy-making** as a fundamental mechanism of thought rather than an
  occasional rhetorical device;
- **fluid concepts**, whose boundaries and relevance shift with context;
- the relationship between formal symbols and the meanings a mind perceives in
  them; and
- the possibility—and difficulty—of modeling human cognition in software.

His best-known work, *Gödel, Escher, Bach*, received the 1980 Pulitzer Prize
for General Nonfiction. Its unusual structure alternates expository chapters
with fictional dialogues inspired in part by Lewis Carroll. Across logic,
Bach's music, Escher's images, formal systems, genetics, Zen, and artificial
intelligence, the book develops an account of how self-reference and layered
symbol systems may be connected to minds.

Hofstadter's other major writings extend these themes:

- ***The Mind's I* (1981)**, co-edited with philosopher Daniel Dennett, collects
  fiction and essays about personal identity, consciousness, and the self.
- ***Metamagical Themas* (1985)** gathers his *Scientific American* columns on
  patterns, language, creativity, mathematics, and mind. Its title is an
  anagrammatic homage to Martin Gardner's “Mathematical Games.”
- ***Fluid Concepts and Creative Analogies* (1995)** presents research from
  Hofstadter's group on computer models of perception and analogy-making,
  including programs such as Copycat.
- ***Le Ton beau de Marot* (1997)** uses many translations of a short French
  poem to investigate translation, style, constraint, creativity, and the
  preservation of meaning.
- ***I Am a Strange Loop* (2007)** revisits the account of consciousness
  sketched in *GEB*, concentrating more directly on the self as a
  self-referential symbolic pattern.
- ***Surfaces and Essences* (2013)**, written with Emmanuel Sander, argues that
  analogy is the core of categorization and everyday thinking.

MIU is characteristic of Hofstadter's method: begin with a game that is easy to
state, invite the reader to manipulate symbols personally, and then use the
experience to expose a deeper distinction. Here that distinction is between
obeying rules within a system and recognizing a pattern about the system as a
whole. MIU × Jev places a contemporary decision model into that same
experimental tradition.

[hofstadter-iu]: https://cogs.indiana.edu/directory/affilate/hofstadter-douglas.html
[crcc]: https://crcc.indiana.edu/

## What is the MIU system?

MIU has three symbols:

```text
M  I  U
```

It begins with one axiom:

```text
MI
```

From a current string, a new string may be produced using exactly one of four
rules. Here `x` and `y` stand for arbitrary, possibly empty, strings.

| Rule | Form | Meaning | Example |
|---|---|---|---|
| 1 | `xI → xIU` | If the string ends in `I`, append `U`. | `MI → MIU` |
| 2 | `Mx → Mxx` | Duplicate everything after the initial `M`. | `MIU → MIUIU` |
| 3 | `xIIIy → xUy` | Replace any occurrence of `III` with `U`. | `MIIII → MUI` |
| 4 | `xUUy → xy` | Delete any occurrence of `UU`. | `MIUU → MI` |

Rule applications are local and mechanical. When a pattern occurs in multiple
positions, each position is a separate legal application. A **derivation** is
any sequence of strings beginning with `MI` in which every step follows one of
these rules.

## The MU puzzle

Hofstadter asks whether it is possible to derive:

```text
MU
```

from:

```text
MI
```

Trying rules produces a rapidly branching search tree. Some paths grow,
contract, loop, or appear promising, but none reaches `MU`. Search alone,
however, does not explain whether `MU` is impossible or merely difficult to
find.

The decisive observation is an **invariant** involving the number of `I`
symbols:

1. `MI` starts with one `I`.
2. Rule 1 does not change the number of `I`s.
3. Rule 2 doubles the number of `I`s.
4. Rule 3 subtracts three `I`s.
5. Rule 4 does not change the number of `I`s.

Starting from a count that is not divisible by three, doubling it or
subtracting three can never make it divisible by three. Every theorem derived
from `MI` therefore has a number of `I`s congruent to either 1 or 2 modulo 3.

`MU` contains zero `I`s. Zero is divisible by three, so `MU` cannot be derived.

This proof occurs at the **meta-level**: it says something about every possible
derivation without enumerating them. That is why the puzzle matters. A machine
can follow the rules forever, while a suitable external description can prove
in a few lines that the requested destination is unreachable.

## Algorithmic considerations for problem solving

MIU can be treated as a graph-search problem:

- a **state** is a valid MIU string;
- a directed **edge** is one legal rule application at one specific position;
- the axiom `MI` is the start node; and
- a requested theorem, such as `MUI` or `MU`, is a goal node.

This graph is infinite. Rule 2 can repeatedly double a string, rules may lead
back to previously seen strings, and the number of possible states grows
quickly. The fact that every individual move is easy to compute does not make
global reachability easy to decide by search.

### Prove cheap necessary conditions before searching

The most valuable algorithmic step is often a meta-level precheck. Every string
derived from `MI` has at least these properties:

- it begins with exactly one `M`;
- no rule introduces another `M`; and
- its number of `I` symbols is never divisible by three.

These are **necessary**, not generally sufficient, conditions. They can reject
some targets immediately, but passing them does not automatically provide a
derivation.

For `MU`, the modulo-three test settles the problem without search: zero `I`
symbols is impossible. For `MUI`, the test allows search because one `I` is in
a reachable residue class, and a short derivation exists:

```text
MI → MII → MIIII → MUI
     R2     R2       R3
```

This suggests a general workflow:

1. validate the target's syntax;
2. apply known invariants and reject impossible targets;
3. search only when the target survives those checks; and
4. retain the derivation as a verifiable witness when search succeeds.

Failure to find a path within a budget is not a proof of impossibility. A
failed search and an invariant proof are different kinds of result.

### Why naive search performs badly

Different standard search methods encounter different problems:

| Method | Advantage | MIU difficulty |
|---|---|---|
| Depth-first search | Very small memory use | Can disappear forever down a Rule 2 growth branch. |
| Breadth-first search | Finds a shortest derivation under unit edge cost | The frontier and stored strings grow rapidly. |
| Iterative deepening | Bounded memory with increasing depth | Repeats work and still needs a practical length bound. |
| Beam search | Keeps only the most promising states | Fast, but can discard the only productive growth path. |
| A* search | Can prioritize states with a heuristic | A useful admissible distance-to-goal heuristic is not obvious. |

Backward search is not automatically easier. Reversing Rule 3 means replacing
a `U` with `III`; reversing Rule 4 means inserting `UU` at possible positions.
These inverse operations create many possible predecessors, including longer
ones, so an unrestricted reverse graph also expands quickly.

### Productive growth versus blind growth

“Always choose the shortest result” is not a sufficient strategy. Some growth
is required to create patterns that later rules can contract. The derivation
of `MUI` demonstrates this:

- `MI → MII → MIIII` grows the string;
- that growth creates an `III`; and
- Rule 3 then contracts `MIIII → MUI`.

The useful distinction is therefore not simply **shorter versus longer**, but
**productive growth versus blind growth**.

The canonical blind-growth trap is:

```text
MIU → MIUIU → MIUIUIUIU → …
```

Once the tail is the alternating pattern `IU`, Rule 2 is the only applicable
rule. Duplicating that tail preserves the pattern, so no `III` or `UU` can ever
appear. The strings grow forever without opening a contraction.

A productive growth move, by contrast, creates or approaches one of the
patterns needed by Rules 3 and 4. For example, duplicating `MII` produces
`MIIII`, which immediately exposes two occurrences of `III`.

### The algorithm used by MIU × Jev

The app is an **online guided graph walk**, not an exhaustive theorem prover.
At each step it:

```text
legal = enumerate_every_legal_application(current)
probabilities = decision_model(current, target, history, legal)
chosen = apply_policy(probabilities, legal, history)
current = apply(chosen)
```

The default guided policy applies the following priorities:

1. choose the target immediately if it is a legal successor;
2. if a shortening move exists, choose among shortening moves;
3. avoid already visited states when a novel candidate exists;
4. reward states containing `III` or `UU`, because they permit contraction;
5. penalize doubling that creates no concrete rewrite opportunity;
6. reject known growth-only traps when a productive alternative exists; and
7. combine those heuristic scores with the model's probabilities.

This division of labor is deliberate:

- the deterministic engine guarantees **soundness**—every applied edge belongs
  to the MIU graph;
- the decision model contributes contextual ranking among legal alternatives;
  and
- the heuristics provide search control the model may not infer reliably from
  a local menu.

The guided policy is not complete. It may miss a derivation that requires a
temporarily unattractive state, and its reduction-first preference is not an
admissible shortest-path heuristic. The **Model only** mode is even less
controlled: it is useful for observing the provider, not for claiming a
systematic solver.

### Budgets, cycles, and resource bounds

Any practical traversal needs limits because the formal graph is unbounded.
The app tracks visited states and places budgets on:

- the number of automatic steps;
- the length of the next string; and
- the absolute string size accepted by the server.

These limits protect memory, rendering, request size, and model context. They
do not change which rewrites are formally legal. A budget-exhausted run means
“not found under these resources,” never “mathematically impossible.”

For a more complete bounded solver, a natural next step would be breadth-first
or iterative-deepening graph search with:

- a visited-state set;
- explicit maximum depth and string length;
- invariant-based pruning before expansion;
- parent pointers for reconstructing a proof; and
- separate outcomes for **found**, **excluded by invariant**, and
  **not found within bounds**.

That distinction—between a derivation, a proof of impossibility, and an
inconclusive bounded search—is the central algorithmic lesson of the MIU
puzzle.

## Why add Jev?

System One decision models such as Jev and Nimble do not need to generate
free-form text for this task. They select one option from a typed set of
choices and return probabilities for the alternatives. That fits the MIU
system naturally:

1. The symbolic engine receives the current string.
2. It enumerates **all and only** formally legal rule applications.
3. It sends those moves to the selected provider as a choice question.
4. The model selects the move it considers most promising.
5. The engine applies the selected move and records the derivation.

The model is the strategy, not the referee. Correctness does not depend on the
model knowing the MIU rules or reliably reproducing them. Even a surprising or
poor strategic choice remains a valid formal step because the deterministic
engine controls the action space.

This separation illustrates a useful architecture for AI systems beyond this
toy problem:

- use conventional code to enforce permissions, invariants, and state
  transitions;
- use a model for judgment among explicitly permitted alternatives; and
- retain a complete trace that a person can inspect and override.

In the default `MI → MU` experiment, Jev cannot win—the invariant forbids it.
What the app reveals instead is the model's behavior inside an impossible
search: whether it favors growth, contraction, novelty, repeated states, or
apparently goal-like strings.

## Where Jev came from: TypeSafe AI and TypeScript

The starting point for this project was [Jev][jev], the System One decision
model released by **TypeSafe AI** in September 2026. Jev is designed for a
different software role than a conversational language model. Instead of
generating prose, it evaluates some supplied state against explicitly typed
questions and returns answers constrained to the declared schema.

Jev exposes three main decision primitives:

- **choice** selects one key from a finite set and returns a probability
  distribution across all allowed keys;
- **score** evaluates the state against an ordered rubric and returns a
  probability-weighted score; and
- **noul** returns the probability that a stated condition is true; some
  integrations expose the same primitive as **boolean**.

This style is especially natural in TypeScript. Through the official
[`@typesafe-ai/sdk`][typesafe-sdk], or through
[Vercel AI SDK's evaluation interface][vercel-jev], the keys in a choice schema
become a TypeScript union in the answer. If an application declares:

```typescript
const result = await evaluate({
  model: "typesafe-ai/jev",
  state: currentMiuState,
  questions: {
    nextMove: {
      type: "choice",
      instructions: "Which legal rewrite should be applied next?",
      criteria: {
        rule1AtEnd: "Append U because the string ends in I",
        rule2: "Duplicate the tail after M",
      },
    },
  },
});
```

then `result.answers.nextMove.choice` is constrained to
`"rule1AtEnd" | "rule2"`. The model cannot answer with an undeclared third
action or an arbitrary sentence. The schema becomes the boundary between
probabilistic judgment and ordinary application code.

That was the conceptual beginning of MIU × Jev. The MIU engine already has a
perfectly defined, finite action schema at every step: the complete set of
legal rewrites. A typed decision model can therefore choose among those
actions without being entrusted with constructing them. It is a particularly
literal demonstration of TypeSafe AI's core pattern:

> Put the state and permitted outcomes in code; ask the model only for the
> judgment between them.

### Jev, Nimble, and this implementation

The names are related but not interchangeable:

| Component | Role |
|---|---|
| **Jev** | TypeSafe AI's hosted System One decision model and the original inspiration for this experiment. |
| **TypeScript SDK** | A type-safe way for JavaScript and TypeScript applications to define Jev questions and consume constrained answers. |
| **Nimble** | [Bespoke Labs' open decision model][nimble], trained for the same broad class of schema-bound judgments. |
| **Ollama 0.35.0+ System One** | The local API used here to run `nimble:latest` and obtain typed choices and probabilities. |

MIU × Jev defaults to **Nimble locally through Ollama 0.35.0+**, making the
experiment self-contained and keeping every derivation on the user's machine.
It can also
call the hosted TypeSafe Jev service when the user deliberately selects that
provider and supplies a `TYPESAFE_API_KEY`. The UI keeps the name “Jev” because
the project began with the Jev interaction pattern: present state plus a typed
menu, receive a probabilistic decision, and leave execution to deterministic
code.

Jev's structural guarantees should not be confused with semantic infallibility.
A typed decision model cannot return a malformed answer or an option outside
the menu, but it can confidently select a poor option inside the menu. In this
project that distinction is visible by design: the formal engine guarantees
that every selected move is legal, while the derivation history reveals
whether the model's strategy is useful.

[jev]: https://docs.typesafe.ai/
[typesafe-sdk]: https://www.npmjs.com/package/@typesafe-ai/sdk
[vercel-jev]: https://vercel.com/kb/guide/typesafe-jev-and-ai-sdk
[nimble]: https://github.com/bespokelabsai/nimble

## User interface

The browser UI provides:

- **Ask Jev for one move** to request one decision from the selected provider;
- **Auto-run** to continue choosing until stopped, stuck, or at the target;
- configurable auto-run step and string-length budgets;
- invariant preflight before automatic search;
- stagnation detection based on edit distance to the target;
- automatic stopping before cycles or over-limit growth;
- locked manual move controls while a model decision or auto-run is active;
- a provider switch between local Ollama 0.35.0+/Nimble and hosted TypeSafe/Jev;
- a **guided** reduction-first policy and a **model only** comparison mode;
- the complete menu of legal rewrites at every step;
- manual selection of any legal move;
- decision probabilities when available;
- undo, reset, and a complete derivation history;
- live string length, legal-move count, and `I` count modulo three; and
- editable target, model, and auto-run speed settings.

The choice API in Ollama 0.35.0+ allows at most 26 options, while TypeSafe
accepts up to 255. If a state exceeds the selected provider's limit, the
server uses successive groups and a final round so that every legal move
remains eligible.

## Architecture

The project intentionally has no package dependencies or frontend build step.

```text
app.py          HTTP server, MIU engine, validation, provider clients
web/
  index.html    application structure
  styles.css    responsive interface
  app.js        client state and interaction
test_app.py     rule-engine and selection tests
```

The Python server is stateless with respect to a run. The browser sends the
current string and derivation history when requesting a decision. The server
recomputes the legal moves rather than trusting a client-supplied menu.

The provider boundary is also server-side:

```text
browser
   │ current state + provider name
   ▼
Python MIU engine
   │ enumerates and validates legal moves
   ├──► Ollama 0.35.0+ /v1/systemone ──► local Nimble
   └──► TypeSafe /v1/systemone ► hosted Jev
```

Both providers receive the same semantic state and choice descriptions. Their
different option limits are handled by the server, so the browser and MIU rule
engine do not need provider-specific logic.

### Runaway-search protection

The default `MI → MU` target is formally impossible, so no move-selection
strategy can make auto-run succeed. Rule 2 can also double a string
exponentially. Auto-run therefore has three guardrails:

- a step budget, defaulting to 40 moves;
- a maximum next-string length, defaulting to 64 characters;
- a stagnation budget, defaulting to 10 steps without getting closer to the
  target;
- cycle detection that stops before revisiting an earlier string.

These are execution safeguards, not new MIU rules. The complete legal menu
remains visible, and a person may still apply any legal move manually. The
server additionally rejects MIU strings over 8,192 characters to bound request
and rendering costs.

While a provider decision is pending, manual move controls are temporarily
disabled. The browser also records the string used for each request and
discards the response if that source string changes before the decision can be
applied. This prevents a delayed provider response from adding a move that was
legal for an earlier state but not for the current derivation.

Before auto-run begins, the app applies the modulo-three invariant. A target
such as `MU`, with zero `I` symbols, is marked as unreachable because no search
can reach it from `MI`. Exploratory auto-run is enabled by default because
observing model behavior inside that impossible search is a central purpose of
the project. The UI warns that the target cannot be reached, then relies on the
step, length, cycle, and stagnation budgets to stop safely. Users may disable
the exploratory override when they want impossible targets rejected outright.

### Guided selection heuristics

Prompting alone does not reliably teach a decision model how to control an
open-ended symbolic search. The default **Guided · reductions first** policy
therefore combines the provider's probability distribution with deterministic
search heuristics:

1. take the target immediately when available;
2. when any legal move shortens the string, choose among shortening moves;
3. prefer novel states over already visited states;
4. reward results that expose `III` or `UU` contractions; and
5. penalize Rule 2 doubling when it creates no concrete contraction;
6. avoid **growth-only traps** such as `MIU → MIUIU → MIUIUIUIU → …`, where
   Rule 2 remains the only move and no `III` or `UU` can ever appear.

The provider still evaluates the legal menu, and every applied move remains a
formal MIU rewrite. The heuristic layer controls search strategy, not legality.
For experiments with unmodified model behavior, select **Model only ·
experimental** in **Settings & rules**.

In the default mode, the model is called through the local
[`POST /v1/systemone` decision endpoint][systemone] provided by Ollama 0.35.0
or later. No prompts, strings, or derivations leave the machine in that mode.

When TypeSafe is selected, the server sends the current string, target, recent
history, and legal move descriptions to
the hosted [`POST /v1/systemone` endpoint][typesafe-api]. The API key is read
only by the Python
server and is sent in the required Bearer authorization header. It is never
returned by `/api/health`, included in browser JavaScript, or written to the
derivation history.

[systemone]: https://docs.ollama.com/api/systemone
[typesafe-api]: https://docs.typesafe.ai/api

## Requirements

- Python 3.10 or later
- at least one decision provider:
  - **default:** Ollama **0.35.0 or later** with a local decision model such as
    `nimble:latest`; or
  - **optional:** a TypeSafe API key with access to `jev-latest`.

### Option A: local Ollama 0.35.0+/Nimble (default)

The local provider requires **Ollama 0.35.0 or later**. Check before starting:

```powershell
ollama --version
```

Confirm that the model is installed:

```powershell
ollama list
```

If necessary, install it:

```powershell
ollama pull nimble
```

No API key is needed. This remains the recommended path for local exploration.

### Option B: hosted TypeSafe/Jev

Set `TYPESAFE_API_KEY` in the process environment before starting the server.
On PowerShell:

```powershell
$env:TYPESAFE_API_KEY = "your-key"
python app.py
```

Alternatively, copy `.env.example` to `.env` and fill in the value:

```dotenv
TYPESAFE_API_KEY=your-key
```

For compatibility with GitHub Copilot CLI setups, the server also reads
`~/.copilot/.env` when present. Existing process environment variables always
take precedence over values in either file.

The repository ignores `.env` and `.env.*` files except `.env.example`. Never
commit an API key. Once configured, open **Settings & rules** in the UI and
select **TypeSafe API / Jev**. The model changes to `jev-latest` automatically.

## Run

From the project directory:

```powershell
python app.py
```

Then open <http://127.0.0.1:8765>.

The server listens only on localhost by default. A different host or port may
be selected explicitly:

```powershell
python app.py --host 127.0.0.1 --port 9000
```

## Test

```powershell
python -m unittest -v
```

The tests cover all four rewrite rules, overlapping pattern positions, input
validation, required TypeSafe credential handling, the Ollama 0.35.0+
requirement and 26-choice tournament behavior, and TypeSafe's larger choice
window.

## Scope

This is an MVP and an exploratory instrument, not a general theorem prover.
Jev has no persistent learned strategy, exhaustive search, or proof-producing
planner. Its choices are local decisions informed by the current state, target,
recent derivation, and move descriptions.

That limitation is deliberate: the project contrasts a model's step-by-step
judgment with a formal invariant that settles the entire infinite search space.
