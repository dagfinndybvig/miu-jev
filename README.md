<img width="1253" height="670" alt="Formalism × Jev application screenshot" src="https://github.com/user-attachments/assets/aadd6d09-1450-43f9-95a0-f46e7548ead8" />

# Formalism × Jev

**Formalism × Jev** is an experiment in constrained machine choice. A formal
engine generates the complete menu of legal moves, a decision model evaluates
that menu, and deterministic code executes the selection and records every
step. The same provider, controls, and decision log drive four formal
systems:
**Algebra × Jev**, exact single-variable linear algebra over the rationals,
**Lambda × Jev**, beta reduction of untyped lambda terms,
**Grammar × Jev**, bottom-up parsing of a toy English fragment, and
and **MIU × Jev**, Hofstadter's MU puzzle - the latter mostly included for historical inspiration. **Guided** mode uses heuristics with
model-assisted ranking; **Model only** (the default) preserves the provider's choice,
subject to execution limits. Local **Ollama 0.35.0 or later** with Nimble is
the default; TypeSafe's hosted Jev API is an optional secondary provider. In
either mode, the selected policy determines *which* legal path to follow, but
it can never invent a rule, alter a state directly, or make an illegal move.

The result is a small, inspectable example of an AI operating inside hard
symbolic boundaries:

> The formal system determines what is legal. The selected policy determines
> how model advice is used.

That is the whole philosophy. Any formal system with a computable, finite menu
of legal moves admits the same division of labor: deterministic code owns
soundness, the model contributes judgment among legal alternatives, and a
complete trace keeps the boundary inspectable. Algebra is where this pattern
does real work, lambda is where model choice finally becomes strategy, grammar
is where several legal answers exist and choosing among them is semantics,
and MIU is where it began.

A first measured result, in plain terms: when we ran the same experiment on
lambda calculus — the tiny formal system underneath programming languages —
the decision models dodged every infinite-loop trap we set, and they kept
doing it even after we removed every hint we normally compute for them.
They seem to read the candidates themselves. It is early evidence from small
menus; the measured lambda sample near the end carries the numbers and the
caveats.

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

Open <http://127.0.0.1:8765>. The app starts on its landing page: choose
**Algebra × Jev** (the simple example), **Lambda × Jev** (the strategy test),
**Grammar × Jev** (ambiguity and dead ends), or
**MIU × Jev** (the historical inspiration). Use **Settings & rules** to switch providers.
The browser never receives either provider's credentials.
Ollama remains selected even when it is unavailable and a TypeSafe key is
configured. Hosted decisions require an explicit switch to TypeSafe; there is
no automatic local-to-hosted fallback. Without an available provider, manual
exploration still works.

## Algebra × Jev

Algebra is the practical half of the experiment: solve single-variable linear
equations over the rational numbers using exact arithmetic and a finite,
declared rewrite vocabulary. The engine uses exact `Fraction` arithmetic and a
bounded syntax-tree parser—never `eval`, floating point, or a
provider-generated equation.

The supported language has one variable, `x`, integers, fractions, ASCII
`+ - * /`, parentheses, and implicit multiplication such as `2x` or `2(x+3)`.
Multiplication and division have equal precedence and associate left to
right; use parentheses to group a denominator. Decimals, powers, functions,
other variables, variable denominators, and products of two
variable-containing expressions are rejected.

The menu offers transformations from seven rule families:

| Rule | Offered transformation |
|---|---|
| 1 | Simplify arithmetic and identities within a subtree. |
| 2 | Distribute a numeric factor over a sum or difference. |
| 3 | Expand and collect one side into `a*x + b`. |
| 4 | Subtract a visible top-level term from both sides. |
| 5 | Divide both sides by a visible nonzero numeric coefficient. |
| 6 | Multiply both sides by the LCM of numeric denominators, then collect to clear fractions. |
| 7 | Swap the two sides. |

This is a declared vocabulary, **not every possible algebraic transformation**.
Every offered move is checked against the original exact solution set, and its
displayed expression is parsed back to verify the syntax tree. Move positions
identify syntax-tree locations rather than MIU character offsets.

The default example shows the shape of a derivation:

```text
2 * (x + 3) = 14
x + 3 = 7          divide both sides by 2
x = 4              subtract 3 from both sides
```

Distribution is also offered as a valid alternative, so the model chooses
between different derivations of the same solution.

The goal is fixed and server-owned: isolate `x` on the left with a rational
number on the right, or reduce an identity/contradiction to a numeric
equality. For example, `x - x = 0` can become `0 = 0` (all rational values),
and `x - x = 1` can become `0 = 1` (no solution). These are successful
classifications, not failed searches; MIU's modulo-three test does not apply.

Guidance prefers in-budget, solved, and unvisited results when available,
then scores `-10 * structural_cost + 5 * group_probability`. Structural cost
is syntax-node count, plus six per right-side `x`, four for a nonzero left
constant, and three for a left `x` coefficient other than one; solved states
cost zero. This strongly heuristic policy may override the model. **Model
only** preserves the raw provider choice; neither policy is guaranteed to find
a short derivation before a safety budget stops it.

Representation limits are 512 characters (including normalized output), 128
syntax nodes, expression depth below 24, and 128-bit numerators and
denominators, including computed coefficients and solutions. Oversized
inputs are rejected. Generated transformations exceeding these bounds are
omitted and counted in the UI; this is a representation restriction, not
mathematical invalidity. The separate model-move length budget still defaults
to 64 characters.

The deterministic engine already knows how to classify linear equations. The
experiment is about choosing inspectable intermediate steps, not a claim that
AI is needed to solve them.

## Lambda × Jev

Lambda is where the menu finally gets big enough that choosing is real work.

### What it is

The lambda calculus was introduced by **Alonzo Church** in the early 1930s as
a formal system for effective computability, before digital computers existed.
It has three constructs and nothing else:

- **variables**: `x`, `y`, `z`, ...;
- **abstraction**: `λx.M`, the function that binds `x` and returns `M`; and
- **application**: `M N`, written by juxtaposition.

A single rewrite rule drives everything: **beta reduction**,

```text
(λx.M) N  →  M[x := N]
```

substituting `N` for every free occurrence of `x` in `M`, renaming bound
variables when needed to avoid capture. A term with no remaining redex is a
**normal form**. Church encoded numbers, booleans, pairs, and recursion in
this tiny language, and LISP grew out of it a generation later (McCarthy,
1958).

Two classical results shape the strategy:

- **Church-Rosser**: reduction order cannot change the destination. Every
  term has at most one normal form, up to renaming of bound variables.
- **Standardization**: reducing the leftmost-outermost redex first — normal
  order — reaches a normal form whenever any order does. Reducing inner
  redexes first can diverge on terms that normal order reduces fine:
  `(λx.λy.y) Ω`, where `Ω = (λx. x x) (λx. x x)`, reduces to `λy.y` under
  normal order and loops forever if Ω is contracted first.

And one hard limit: **normalization is undecidable**. Deciding whether an
arbitrary term has a normal form would decide the halting problem. This is
the same honest three-way split MIU draws between a derivation, an invariant
proof, and an inconclusive search — except here "provably impossible" is not
generally available either.

**Church-Turing**: Church's lambda-definable functions and Turing's machines
(1936-37) compute exactly the same class of functions, and Turing proved the
equivalence. The Church-Turing thesis is the claim that this shared class
captures what "effectively computable" means. Lambda × Jev runs a
contemporary decision model inside the oldest formal model of computation.

### What the app does

- The engine parses terms into bounded syntax trees — variables `a`-`z`,
  `λ` or `\`, `.`, and parentheses — never `eval`.
- The menu lists **every beta redex at every position**; the model only names
  one. Capture-avoiding substitution is performed by the server, so a
  misremembered rule cannot produce variable capture or a malformed term.
- The goal is server-owned: a beta **normal form**. A term can be a normal
  form while still containing lambdas, so long as no application of a lambda
  remains anywhere.
- **Guided** mode prefers in-budget, normal-form-producing, unvisited
  results, then scores structural progress, duplication cost (how much work
  the substitution copies), and outer position, with the model's group
  probability added. Normal order is the honest default heuristic; the
  policy is not complete.
- **Model only** preserves the provider's raw choice. On `(λx.λy.y) Ω` the
  guided policy escapes the Ω trap; model-only behavior is the experiment.
- Ω reduces to itself forever. Auto-run stops on cycle and budget rules, and
  the journal records that as exploration, not failure: normalization is
  undecidable, so budget stops are inconclusive rather than proofs.
- Representation limits are 512 characters, 256 syntax nodes, and depth at
  most 96. Contractions exceeding the bounds are omitted and counted; the
  separate model-move length budget still defaults to 64 characters.

## Grammar × Jev

Grammar is the first system in the app with several equally-legal answers.

### What it is

A small, fixed toy fragment of English syntax. The lexicon contains
`the, a, man, woman, dog, pizza, park, telescope, saw, found, chased, ate,
with, in, near, under, and`; the grammar has seven productions:

```text
S  → NP VP          NP → Det N         NP → NP PP
NP → NP Conj NP     VP → V NP          VP → VP PP
PP → P NP
```

A state is a **parse forest**: a sequence of bracketed trees whose leaves are
the sentence's words, so `the man saw the dog with the telescope` starts as

```text
[Det the] [N man] [V saw] [Det the] [N dog] [P with] [Det the] [N telescope]
```

A legal move combines adjacent constituents with one production, spliced back
into the whole forest at its position, for example

```text
[Det the] [N man] ...      →  [NP [Det the] [N man]] ...
[VP ...] [PP ...]          →  [VP [VP ...] [PP ...]]
```

For readability the browser displays states without lexical tags —
`[NP [Det the] [N man]] [V saw]` renders as `[NP the man] saw` — keeping only
the phrase-level brackets. The tagged forest remains the canonical format in
the API, the derivation history sent to the server, and the exported journal.

The word sequence never changes, so every state is a partial parse of the same
sentence. The goal is a single complete parse: one `S` tree spanning the
sentence, such as

```text
[S [NP [Det the] [N man]] [VP [V saw] [NP [NP [Det the] [N dog]] [PP [P with] [NP [Det the] [N telescope]]]]]]]
```

### Why it is different from the other systems

- **Ambiguity.** MIU has one target, algebra one solution set, lambda a unique
  normal form. *The man saw the dog with the telescope* has **two** complete
  parses: the PP can attach to the VP (the man used the telescope) or to the
  object NP (the dog had it). Both are legal; only semantics can choose. The
  server chart-counts complete parses and reports the total. A model's
  preference between equally-legal parses is the purest judgment call the app
  offers.
- **Dead ends.** Legality is local, so a greedy reduction can strand a
  modifier: reduce `VP → V NP` and then `S → NP VP` while the PP is still
  dangling and no production applies. The menu becomes empty with the goal
  unreached. The reference witness (`reference_parse`) always takes a
  chart-verified completable reduction, so it reaches a parse whenever one
  exists; **guided** mode applies the same chart filter, while **model only**
  keeps the raw choice and can dead-end — that contrast is the experiment.
- **Server-owned trees.** The provider never sees or builds a string it can
  alter: it only names a reduction from the menu, and the engine splices the
  new tree. Every move round-trips through the forest parser and preserves
  the yield exactly.

### Limits

Sentences are at most 16 words; forests are bounded by 512 characters, 256
syntax nodes, and depth 96. Because a parse forest is longer than the plain
sentence, loading the grammar example raises the model-move length budget to
its 512-character limit automatically; lower it deliberately if you want
tighter budgets. Parsing is decidable, so unlike lambda, a stuck derivation is
a dead end of that line, not an undecidability result — undo and take a
different reduction.

## MIU × Jev

MIU was the inspiration for this project. An
honest admission comes with it: MIU is a bit too simple to benefit much from
this approach. The engine already enumerates every legal rewrite, and the
modulo-three invariant settles the interesting question without any search,
so the strategic work left for a decision model is modest. MIU is retained
here because of its place in AI lore: it is where this project began,
and its origin in Hofstadter's *Gödel, Escher, Bach* makes it a compact,
familiar stage for constrained machine choice.

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
decision = decision_model(current, target, history, legal)
chosen = apply_policy(decision, legal, history)
current = apply(chosen)
```

The guided policy applies the following priorities:

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

The model contributes strategy; it is not the referee. In guided mode,
deterministic preferences can override its choice, and the log records that
override. Correctness does not depend on the
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

That was the conceptual beginning of this project. The MIU engine already has a
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

Formalism × Jev defaults to **Nimble locally through Ollama 0.35.0+**, making the
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

- a **landing page** that opens on launch and offers **Algebra × Jev** as the
  simple example, **Lambda × Jev** as the strategy test, **Grammar × Jev**
  as the ambiguity and dead-end test, and **MIU × Jev** as
  the historical inspiration, with highlights from this README; a launch
  starts the selected example, and the Example menu
  switches between them at any time. The header **Menu** button and the
  **Choose application** control
  returns to the landing without discarding the active derivation, and
  **Continue the current derivation** resumes it; choosing a card starts that
  example fresh. A **Settings** button sits beside the Menu button and opens
  the settings panel;
- an **Example** menu for MIU, linear equations, lambda terms, and sentences;
- editable starting equations, lambda terms, and sentences, with
  **Load equation** / **Load term** / **Load sentence**;
- **Request one decision** to evaluate the current menu using the selected policy;
- **Auto-run** to continue choosing until stopped, stuck, or at the target;
- configurable auto-run step and state-length budgets;
- MIU invariant preflight before automatic search;
- stagnation detection using MIU target distance or algebra structural cost;
- automatic stopping before cycles or over-limit growth;
- locked manual move controls while a model decision or auto-run is active;
- a header indicator that tracks the selected provider, model, and reported
  availability, including local-provider errors;
- a provider switch between local Ollama 0.35.0+/Nimble and hosted TypeSafe/Jev;
- a default **model only** policy with domain-specific **guided** policies
  one click away;
- the generated menu of legal rewrites at every step;
- manual selection of any legal move;
- decision probabilities when available;
- expandable decision records alongside history, including raw choices and
  deterministic guidance overrides;
- group- and round-specific tournament evidence, never a merged global
  probability distribution;
- a locally saved event log and JSON export, including rejected decisions,
  errors, manual moves, undo/reset, and run stop reasons;
- undo, reset, and a complete derivation history;
- live state length, legal-move count, and a domain-specific progress metric; and
- editable MIU target, model, and auto-run speed settings.

Changing examples starts a new derivation but keeps provider/model settings
and the shared decision log. Algebra reset returns to the last loaded equation,
lambda to the loaded term, grammar to the loaded sentence;
MIU reset returns to `MI`. Switching and loading are disabled during a decision
or auto-run. Invalid equations leave the active derivation unchanged.

The choice API in Ollama 0.35.0+ allows at most 26 options, while TypeSafe
accepts up to 255. If a state exceeds the selected provider's limit, the
server uses successive groups and a final round so that every legal move
remains eligible.

### Algebra example

Select **Algebra · solve a linear equation**. The system, its rule families,
guidance, and representation limits are described in
[Algebra × Jev](#algebra--jev). Use the same local Nimble or hosted Jev
settings as for MIU; no second model setup is needed, and manual moves work
without either provider.

Enter a starting equation and use **Load equation**. Try `3x + 2 = x + 10`,
`x/2 + 1 = 3`, `-2(x - 3) = 8`, or `(1/2)x + 1/3 = 5/6`. Numeric-only
arithmetic is normalized on load and during rewrites; the log retains the
entered and normalized starting equations. Variable rearrangements remain
explicit steps, and an invalid equation leaves the active derivation
unchanged.

### Lambda example

Select **Lambda · beta-reduce a term**. The system and its guidance are
described in [Lambda × Jev](#lambda--jev). The default example is Church
addition, 1 + 2, which guided mode reduces to the numeral three in six steps:

```text
(λm.λn.λf.λx.m f (n f x)) (λf.λx.f x) (λf.λx.f (f x))
(λn.λf.λx.(λf.λx.f x) f (n f x)) (λf.λx.f (f x))    beta at f
λf.λx.(λf.λx.f x) f ((λf.λx.f (f x)) f x)          beta at root
λf.λx.f (f (f x))                                  normal form: three
```

Enter any term with **Load term**. Try the normal-order classic
`(λx.λy.y) ((λx. x x) (λx. x x))`, successor applied to two with
`(λn.λf.λx. f (n f x)) (λf.λx. f (f x))`, or Ω itself,
`(λx. x x) (λx. x x)`, which reduces to itself forever and is stopped only
by budgets. Manual moves work without either provider.

### Grammar example

Select **Grammar · parse a sentence**. The fragment, its productions, and its
guidance are described in [Grammar × Jev](#grammar--jev). The default example
is the attachment-ambiguity classic, `the man saw the dog with the
telescope`, which has exactly two complete parses; the notice line reports
the chart-counted total. Enter any sentence of up to 16 lexicon words with
**Load sentence**; try `the man and the dog saw the pizza` for coordination,
`the dog chased the man in the park` for another attachment pair, or
`the man saw` to watch a derivation dead-end with no legal reduction left.
Undo recovers, and guided mode keeps every step chart-completable. Loading the
example raises the model-move length budget to 512 automatically, so
auto-run works out of the box. Manual moves work without either provider.

## Architecture

The project intentionally has no package dependencies or frontend build step.

```text
app.py          HTTP server, MIU engine, system routing, validation, provider clients
algebra.py      exact linear-equation parser, rewrites, and guidance
lambda_calc.py exact lambda-term parser, beta redex menus, and guidance
grammar.py     toy-fragment forest parser, reduction menus, chart, and guidance
web/
  index.html    application structure
  styles.css    responsive interface
  app.js        client state and interaction
test_app.py     rule-engine and selection tests
test_algebra.py algebra equivalence, limits, policies, and provider tests
test_lambda_calc.py lambda substitution, menus, limits, and policy tests
test_grammar.py grammar menus, yields, ambiguity, dead ends, and policies
test_web.js     browser-state regression tests (Node.js built-ins)
benchmark.py    controlled comparisons with bounded reference paths
test_benchmark.py benchmark generation, safety, and measurement tests
benchmark-results.json measured sample with per-trial evidence
benchmark-results-lambda.json measured lambda hint-ablation sample
benchmark-results-lambda-order-fixed.json measured lambda position-bias reference (fixed order)
benchmark-results-lambda-order-shuffled.json measured lambda position-bias sample (shuffled menus)
```

The Python server is stateless with respect to a run. The browser sends the
current state, example identifier, and derivation history when requesting a decision. The server
recomputes the legal moves rather than trusting a client-supplied menu.

The provider boundary is also server-side:

```text
browser
   │ current state + provider name
   ▼
Python formal engines
   │ enumerates and validates legal moves
   ├──► Ollama 0.35.0+ /v1/systemone ──► local Nimble
   └──► TypeSafe /v1/systemone ► hosted Jev
```

Both providers receive the same semantic state and choice descriptions. Their
different option limits are handled by the server, so neither formal engine
needs provider-specific logic. Algebra prompts describe equations and
solution-set preservation; MIU prompts retain their own rules and invariant;
grammar prompts state that every candidate is a server-validated reduction of
the same sentence.
Provider responses must select a supplied move and contain finite probabilities
between zero and one when probabilities are supplied. Malformed responses are
reported as upstream errors rather than forwarded as invalid JSON.

### HTTP example selection

`POST /api/moves` and `POST /api/choose` accept `system: "miu"`, `system: "algebra"`,
`system: "lambda"`, or `system: "grammar"`. Omission defaults to MIU for existing callers. Both
recompute moves from `current`; a client-supplied menu is never authoritative.

For example, `/api/moves` accepts:

```json
{"system": "algebra", "current": "2(x + 3) = 14"}
```

It returns normalized `current`, `moves`, `solved`, `progress`, `solution_kind`,
`omitted_for_limits`, `rules`, and `limits`. `/api/choose` uses the same
`provider`, `model`, `policy` (defaulting to `model`), `history`, and `max_length` fields as MIU.
The algebra `goal` must be `"Isolate x"` or omitted. Its `max_length` range
is 8–512. The lambda `goal` must be `"Normal form"` or omitted, with the
same 8–512 range; its analysis adds `redexes` counts and per-move duplication
costs. The grammar `goal` must be `"Complete parse"` or omitted, with the
same 8–512 range; its analysis adds the chart-counted `parse_count` (and
`parse_count_capped`) for the sentence, and each move reports whether it
keeps a complete parse reachable. Decision responses include `system` and an `analysis` object describing
the input equation, term, or sentence. Each algebra move also reports its result's `solved` and
`progress` values. `/api/health` remains shared provider metadata.

### Decision records and local persistence

`POST /api/choose` returns the example identifier, current state, target, provider/model, policy,
history, length budget, legal menu, selected move, timings, and provider-call
and override counts. Each tournament round contains separate `groups`, each
with candidate IDs, raw provider choice, advancing winner, probabilities, and
the actual filters and scores used by guidance. The old merged round-level
`probabilities` field is replaced by `rounds[].groups[].probabilities`.
An override means a group's winner differs from that group's raw choice;
there is no single raw choice over the original menu in a multi-round tournament.
Singleton groups advance without a provider call, raw choice, or fabricated
100% model confidence. Upstream failures include partial decision evidence
when available; provider response bodies and authorization headers are not logged.

The browser links applied decisions to derivation entries and keeps rejected
decisions separately. Expand a record to inspect candidates and per-group
probabilities. Filter explanations describe deterministic code, not an inferred
explanation of the model's internal reasoning.

The journal is saved in this browser's `localStorage` for the app's origin.
It survives undo, reset, and page reload. A reload returns to the landing
page rather than resuming an interrupted run; launching an application
starts a fresh derivation. Pending decisions are
marked interrupted and unfinished runs receive a `page_interrupted` stop
event. Use one active app tab per origin for this local journal. **Export JSON**
saves a portable snapshot of the active
derivation and journal; **Clear saved log** removes saved evidence without
changing the active derivation. The `formal-decision-log.json` export labels each
example; older records without an identifier are treated as MIU. Logs contain
MIU states, algebra equations, lambda terms, and provider/model
names, never provider credentials. On shared browsers, clear the log when done.
Changing the server port changes the browser origin and its saved log.

Browser storage is finite. If saving fails or stored data is unreadable, an
explicit warning remains visible. New records remain in memory and can be
exported; unreadable saved data is not silently overwritten. Export before
closing the page. The Python server does not persist browser journals.

### MIU runaway-search protection

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

While a provider decision or a replacement legal-menu request is pending,
manual move controls are temporarily disabled. Each menu and decision is bound
to a specific derivation revision; obsolete responses cannot replace the
current menu or add a move from an earlier state. A failed menu refresh leaves
no stale moves enabled and displays an error; reset or undo can recover.

Stopping or resetting auto-run invalidates that run's pending work. Restarting
creates a separate run, so an earlier run's timer cannot advance or stop it.
Undo is disabled during auto-run; stop the run before undoing a move.

Before auto-run begins, the app applies the modulo-three invariant. A target
such as `MU`, with zero `I` symbols, is marked as unreachable because no search
can reach it from `MI`. Exploratory auto-run is enabled by default because
observing model behavior inside that impossible search is a central purpose of
the project. The UI warns that the target cannot be reached, then relies on the
step, length, cycle, and stagnation budgets to stop safely. Users may disable
the exploratory override when they want impossible targets rejected outright.

### MIU guided selection heuristics

Prompting alone does not reliably teach a decision model how to control an
open-ended symbolic search. The **Guided · heuristics + model ranking** policy
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
Unmodified model behavior is the default: **Model only · provider choice,
safety limits** in **Settings & rules** preserves the provider's raw choice.

With Ollama selected, the model is called through the local
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
python -m py_compile app.py algebra.py lambda_calc.py grammar.py test_app.py test_algebra.py test_lambda_calc.py test_grammar.py benchmark.py test_benchmark.py
node --check web\app.js
node --test test_web.js
```

The tests cover all four rewrite rules, overlapping pattern positions, input
validation, required TypeSafe credential handling, the Ollama 0.35.0+
requirement and 26-choice tournament behavior, and TypeSafe's larger choice
window. They also cover HTTP validation, malformed provider responses, explicit
hosted-provider selection, stale menus, auto-run cancellation, and provider
status, decision journals, tournament evidence, export, and benchmark metrics.
Algebra coverage includes exact rational parsing, solution-set preservation,
representation limits, solved-state recognition, shared tournaments, custom
equations, example switching, and cross-example response isolation. Lambda
coverage includes exact parsing, capture-avoiding substitution, redex menus,
representation limits, normal-form recognition, and guided versus model-only
selection.
Browser-state tests use Node.js 18 or later with no npm dependencies;
Node.js is not required to run the app.

## Controlled strategy comparisons

The benchmark runner defaults to **MIU**; its measurements do not evaluate
algebra or grammar strategies. `--system lambda` selects a lambda pool instead.

Run the random and heuristic-only baselines without any model calls:

```powershell
python benchmark.py --output baseline-results.json
```

To include both model-only and guided policies for a provider, opt in explicitly:

```powershell
python benchmark.py --providers ollama --output local-results.json
python benchmark.py --providers ollama typesafe --output comparison-results.json
python benchmark.py --system lambda --output lambda-baseline.json
python benchmark.py --system lambda --providers ollama typesafe --hint-ablation --output lambda-results.json
python benchmark.py --system lambda --providers ollama --menu-order shuffled --output lambda-shuffled.json
python benchmark.py --system lambda --novel-terms 3 --providers ollama --output lambda-novel.json
```

The TypeSafe command sends only generated MIU benchmark inputs to the hosted
service and requires a configured key. Provider failures are reported as failed
trials, never replaced with a baseline or another provider. The runner performs
real inference and may incur hosted usage charges. Default model aliases can be
overridden with `--ollama-model` and `--typesafe-model`.

The lambda mode samples a curated pool: Church-arithmetic terms with
normal-order reference paths, strategy traps that only outer-first reduction
escapes, duplication-heavy growth terms, and Ω as deliberate
impossible-target exploration. `--novel-terms N` replaces up to targets - 2 reachable slots with seeded compositions no textbook contains — random operand order, nested operator trees, identity applications, and constant wrappers — each verified to normalize within the reference-step bound. Reference steps are normal-order paths, which
reach a normal form whenever one exists. `--hint-ablation` adds model and
guided arms whose provider menus carry **no precomputed annotations** — no
solved flags, duplication costs, or search guidance — so raw model judgment
can be compared directly against hint-assisted selection. `--menu-order reversed` or
`--menu-order shuffled` controls position bias reproducibly: the provider-facing
menu is presented reversed, or in a per-state seeded shuffle, while baselines
always use the fixed server order. Move ids stay server-owned, so trial
evidence records the presented order and remains auditable. Without this
control, leftmost-outermost is always the first menu entry, so a model that
always picks the first option and a model following normal order are
indistinguishable until the order changes.

All strategies start at `MI` with the same step, length, cycle, and edit-distance
stagnation limits. Random selects uniformly over legal applications; the
heuristic baseline uses the guided filters and scores with zero model
probability contribution, on the full menu without provider tournaments.
Model-only and random choices can be rejected by execution budgets; guided
selection prefers in-budget moves. Baselines make no provider calls.

Targets are sampled reproducibly from a bounded breadth-first traversal, with
legal witness derivations and a spread of reference depths, not chosen based
on which strategy wins. BFS distances are shortest **within its length bound**,
not claims about unbounded optimality. The report records depth/state limits
and whether the state cap truncated enumeration; the depth bound always
applies. `MU` is evaluated separately as
deliberate impossible-target exploration and is excluded from reachable-target
success rates.

Each report retains trial order, seeds, budgets, source hashes, witnesses,
paths, decision evidence, stop outcomes, timings, provider calls, and group-level
overrides. Provider-call counts measure attempted group decisions, including
failed attempts; singleton advances do not count. Summaries include success rates, steps, successful path overhead
relative to bounded BFS, and latency. Failed attempts remain in the denominator.
Seeds control target generation, trial order, and the random baseline; they do
not control provider sampling. Provider model aliases may change over time.
Latency includes version checks and inference, but not browser animation or
auto-run delays. Reports are checkpointed after each trial; inspect `completed`
before treating one as a complete comparison.

### Measured sample: 2 October 2026

The checked-in [raw report](benchmark-results.json) contains 60 trials: four
reachable targets at reference depths 3, 4, 5, and 6, plus separate `MU`
exploration, repeated twice for each of six configurations. It was produced
by the current implementation—the algebra-capable `app.py` checked in
here—so its recorded source hashes match this repository. Recorded source
hashes identify that Windows working tree (CRLF line endings), not Git's
LF-normalized blobs. Reproduce its setup:

```powershell
python benchmark.py --providers ollama typesafe --targets 4 --repeats 2 --max-steps 10 --max-length 32 --stagnation-limit 4 --bfs-depth 7 --bfs-states 10000 --seed 20261002 --output comparison-results.json
```

Reachable-target results only (eight attempts per configuration):

| Strategy | Successes | Mean applied steps, all attempts | Mean latency per attempt | Provider calls, total | Group override rate |
|---|---:|---:|---:|---:|---:|
| Seeded random | 0/8 | 4.00 | 0.11 ms | 0 | n/a |
| Heuristic only | 2/8 | 5.25 | 0.15 ms | 0 | n/a |
| Nimble model-only | 2/8 | 5.00 | 643 ms | 28 | 0% |
| Nimble guided | 2/8 | 5.25 | 767 ms | 36 | 38.9% |
| Jev model-only | 4/8 | 5.25 | 1,275 ms | 36 | 0% |
| Jev guided | 2/8 | 5.25 | 1,292 ms | 36 | 50.0% |

Heuristic-only and both guided policies solved `MUI`. Nimble model-only
solved `MIIIIIIIIU` in both attempts; Jev model-only solved `MIIIIIIIIU` and
`MIUUIIIIU` once each. None solved `MIIIIIUIIIIUI` under these budgets. Every
successful path matched its bounded-BFS reference length. All twelve separate
`MU` trials stopped on stagnation; their inability to reach `MU` is explained
by the invariant, not a model-quality score.

**This sample does not show a success-rate improvement from adding a model to
the heuristic policy**: both guided configurations matched the heuristic
baseline while adding latency and provider calls. Jev model-only reached 4/8
against the heuristic baseline's 2/8, but two repetitions per configuration
cannot establish an advantage. Different raw choices were often overridden.
This is a small, exploratory sample with only two repetitions, changing model
aliases, and machine/network-dependent timings: it is not evidence of
statistical superiority or equivalence. Broader target sets and repeated
measurements are necessary before making stronger claims.

### Measured lambda sample: 2 October 2026

The checked-in [lambda ablation report](benchmark-results-lambda.json)
contains 120 trials: five sampled cases (three Church-arithmetic terms, one
trap, one growth term) plus Ω, repeated twice for each of ten strategies —
random and heuristic baselines, and model/guided arms for both providers with
and without hints. It was produced by the current implementation; recorded
source hashes match this repository. Reproduce its setup:

```powershell
python benchmark.py --system lambda --providers ollama typesafe --hint-ablation --targets 5 --repeats 2 --max-steps 12 --output lambda-results.json
```

Every arm solved every reachable, trap, and growth case (100%), with mean
steps matching the normal-order references (6.0 reachable, 2.0 trap, 4.0
growth); all Ω trials stopped on cycle. **Hint ablation made no measurable
difference**: identical success, steps, and raw-choice distributions with and
without annotations, consistent with models reading the candidate results
themselves rather than the computed hints. Guided arms occasionally overrode
the model toward a cheaper inner contraction without changing step counts.

Two caveats keep this honest: menus never exceeded three options, so
tournaments are untested; and on these terms the winning redex is always the
first menu entry, so first-option bias cannot be excluded from the report
alone. A separate ad-hoc live probe that reversed the menu order — presenting
the Ω redex first — had both models pick the trap-escaping contraction every
time, but that probe is not part of this checked-in evidence.

### Measured menu-order sample: 6 October 2026

The checked-in position-bias pair — the [fixed-order
report](benchmark-results-lambda-order-fixed.json) and the [shuffled-order
report](benchmark-results-lambda-order-shuffled.json) — holds 72 trials each:
the same lambda pool, seed, providers, and budgets, differing only in
`--menu-order`. Reproduce either side:

```powershell
python benchmark.py --system lambda --providers ollama typesafe --targets 5 --repeats 2 --max-steps 12 --menu-order fixed --output lambda-order-fixed.json
python benchmark.py --system lambda --providers ollama typesafe --targets 5 --repeats 2 --max-steps 12 --menu-order shuffled --output lambda-order-shuffled.json
```

Success was identical under both orders: every reachable, trap, and growth
case was found by both providers under both policies (mean steps 6.0 / 2.0 /
4.0), and all Ω trials stopped on cycle. **Choices track redex identity, not
slot position.** Raw first-position picks fell from 68/84 under the fixed
order (where the leftmost-outermost redex is always first) to 30/85 under the
shuffled order — near chance for menus of two to three options — and Jev's
applied move sequences were identical across orders in 6/6 reachable trials
for both policies; Nimble diverged in 1/6 guided and 2/6 model-only trials
without changing any outcome. The earlier ad-hoc reversed-menu probe is now
reproduced by checked-in evidence. Menus still never exceed three options, so
the arm stays blunt until tournament-stressing terms land (TODO item 3).

## Scope

This is an MVP and an exploratory instrument, not a general theorem prover.
The app does not train or adapt the provider across runs and has no exhaustive
interactive search or proof-producing planner. Its choices are local decisions
informed by the current state, target,
recent derivation, and move descriptions.

For MIU, the project contrasts step-by-step model judgment with an invariant
that settles the impossible `MU` target. Algebra and lambda supply reachable
problems with different valid reductions; grammar adds problems with several
equally-legal answers and local moves that can dead-end. All four are experiments in constrained
step selection, not evidence that a model improves on deterministic methods.
