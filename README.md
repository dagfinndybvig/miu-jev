# MIU × Jev

**MIU × Jev** is a local experiment in constrained machine choice. A formal
engine generates every move permitted by the MIU system, and an Ollama decision
model chooses one move from that menu. The model may decide *which* legal path
to follow, but it can never invent a rule, alter a string directly, or make an
illegal move.

The result is a small, inspectable example of an AI operating inside hard
symbolic boundaries:

> The formal system determines what is possible. Jev determines what to try.

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

## Why add Jev?

Ollama's System One decision models, such as `nimble`, do not need to generate
free-form text for this task. They can select one option from a typed set of
choices and return probabilities for the alternatives. That fits the MIU
system naturally:

1. The symbolic engine receives the current string.
2. It enumerates **all and only** formally legal rule applications.
3. It sends those moves to `nimble` as a choice question.
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

## User interface

The browser UI provides:

- **Ask Jev for one move** to request a single `nimble` decision;
- **Auto-run** to continue choosing until stopped, stuck, or at the target;
- the complete menu of legal rewrites at every step;
- manual selection of any legal move;
- local decision probabilities when available;
- undo, reset, and a complete derivation history;
- live string length, legal-move count, and `I` count modulo three; and
- editable target, model, and auto-run speed settings.

Ollama's choice questions allow at most 26 options. If a state has more than 26
legal applications, the server uses successive groups and a final round so
that every legal move remains eligible for selection.

## Architecture

The project intentionally has no package dependencies or frontend build step.

```text
app.py          HTTP server, MIU engine, validation, Ollama client
web/
  index.html    application structure
  styles.css    responsive interface
  app.js        client state and interaction
test_app.py     rule-engine and selection tests
```

The Python server is stateless with respect to a run. The browser sends the
current string and derivation history when requesting a decision. The server
recomputes the legal moves rather than trusting a client-supplied menu.

The model is called through Ollama's local
[`POST /v1/systemone` decision endpoint][systemone]. No prompts, strings, or
derivations leave the machine through this application.

[systemone]: https://docs.ollama.com/api/systemone

## Requirements

- Python 3.10 or later
- Ollama 0.35 or later
- A local decision model, by default `nimble:latest`

Confirm that the model is installed:

```powershell
ollama list
```

If necessary, install it:

```powershell
ollama pull nimble
```

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
validation, and selection across more than 26 legal moves.

## Scope

This is an MVP and an exploratory instrument, not a general theorem prover.
Jev has no persistent learned strategy, exhaustive search, or proof-producing
planner. Its choices are local decisions informed by the current state, target,
recent derivation, and move descriptions.

That limitation is deliberate: the project contrasts a model's step-by-step
judgment with a formal invariant that settles the entire infinite search space.
