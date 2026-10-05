"""Exact, bounded constituency parsing of a toy English fragment.

The formal system is bottom-up reduction: a state is a forest of parse trees
over a fixed lexicon, and a legal move combines adjacent constituents with
one grammar production, spliced back into the whole forest. The word
sequence (yield) never changes, so every state is a partial parse of the
same sentence. A complete parse is a single S constituent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import re


DEFAULT_SENTENCE = "the man saw the dog with the telescope"
GOAL = "Complete parse"
MAX_CHARS = 512
MAX_NODES = 256
MAX_DEPTH = 96
MAX_WORDS = 16
MAX_PARSE_COUNT = 999

LEXICON = {
    "Det": ("the", "a"),
    "N": ("man", "woman", "dog", "pizza", "park", "telescope"),
    "V": ("saw", "found", "chased", "ate"),
    "P": ("with", "in", "near", "under"),
    "Conj": ("and",),
}
PRODUCTIONS = (
    ("S", ("NP", "VP")),
    ("NP", ("Det", "N")),
    ("NP", ("NP", "PP")),
    ("NP", ("NP", "Conj", "NP")),
    ("VP", ("V", "NP")),
    ("VP", ("VP", "PP")),
    ("PP", ("P", "NP")),
)
RULES = ["1: Combine adjacent constituents with one grammar production"]

WORD_CATS: dict[str, tuple[str, ...]] = {}
for _category, _words in LEXICON.items():
    for _word in _words:
        WORD_CATS.setdefault(_word, tuple())
        WORD_CATS[_word] = WORD_CATS[_word] + (_category,)
CATEGORIES = frozenset(LEXICON) | {lhs for lhs, _ in PRODUCTIONS}
PRODUCTION_SET = frozenset((lhs, rhs) for lhs, rhs in PRODUCTIONS)
TOKEN = re.compile(r"\[|\]|[A-Za-z]+")


class GrammarLimitError(ValueError):
    pass


@dataclass(frozen=True)
class Tree:
    cat: str
    word: str | None = None
    children: tuple[Tree, ...] = ()


def size(tree: Tree) -> int:
    return 1 + sum(size(child) for child in tree.children)


def depth(tree: Tree) -> int:
    return 1 + max((depth(child) for child in tree.children), default=0)


def yield_words(forest: tuple[Tree, ...]) -> tuple[str, ...]:
    words: list[str] = []

    def walk(tree: Tree) -> None:
        if tree.word is not None:
            words.append(tree.word)
        for child in tree.children:
            walk(child)

    for tree in forest:
        walk(tree)
    return tuple(words)


def format_tree(tree: Tree) -> str:
    if tree.word is not None:
        return f"[{tree.cat} {tree.word}]"
    return f"[{tree.cat} {' '.join(format_tree(child) for child in tree.children)}]"


def format_forest(forest: tuple[Tree, ...]) -> str:
    return " ".join(format_tree(tree) for tree in forest)


def is_solved(forest: tuple[Tree, ...]) -> bool:
    return len(forest) == 1 and forest[0].cat == "S"


def validate_limits(forest: tuple[Tree, ...]) -> None:
    nodes = sum(size(tree) for tree in forest)
    if nodes > MAX_NODES:
        raise GrammarLimitError(f"Parse forests must not exceed {MAX_NODES} syntax nodes")
    if max(depth(tree) for tree in forest) > MAX_DEPTH:
        raise GrammarLimitError(f"Parse forests must be at most {MAX_DEPTH} levels deep")
    if len(format_forest(forest)) > MAX_CHARS:
        raise GrammarLimitError(f"The formatted parse forest exceeds {MAX_CHARS} characters")


class Parser:
    def __init__(self, text: str) -> None:
        self.tokens: list[str] = []
        offset = 0
        for match in TOKEN.finditer(text):
            if text[offset:match.start()].strip():
                raise ValueError("Use only category names, lexicon words, and brackets")
            self.tokens.append(match.group())
            offset = match.end()
        if text[offset:].strip():
            raise ValueError("Use only category names, lexicon words, and brackets")
        if not self.tokens:
            raise ValueError("current must be a non-empty parse forest")
        self.index = 0

    def peek(self) -> str:
        return self.tokens[self.index] if self.index < len(self.tokens) else ""

    def take(self, token: str) -> bool:
        if self.peek() == token:
            self.index += 1
            return True
        return False

    def forest(self) -> tuple[Tree, ...]:
        trees = []
        while self.peek():
            trees.append(self.tree())
        return tuple(trees)

    def tree(self) -> Tree:
        if not self.take("["):
            raise ValueError("Expected [ to open a constituent")
        category = self.peek()
        if category not in CATEGORIES:
            raise ValueError(f"Unknown category: {category or 'none'}")
        self.index += 1
        if self.peek() == "[":
            children = []
            while self.peek() == "[":
                children.append(self.tree())
            if not self.take("]"):
                raise ValueError("Missing ] after the children")
            if (category, tuple(child.cat for child in children)) not in PRODUCTION_SET:
                raise ValueError(f"{category} has no production combining those children")
            return Tree(category, children=tuple(children))
        if self.peek() == "]":
            raise ValueError("A constituent must contain a word or at least one child")
        word = self.peek()
        if word not in WORD_CATS:
            raise ValueError(f"Unknown word: {word or 'none'}")
        if category not in WORD_CATS[word]:
            raise ValueError(f"'{word}' cannot be tagged {category} in this lexicon")
        self.index += 1
        if not self.take("]"):
            raise ValueError("Missing ] after the word")
        return Tree(category, word=word)


def parse_sentence(value: Any) -> tuple[Tree, ...]:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("current must be a non-empty sentence")
    if "[" in value or "]" in value:
        raise ValueError("Enter plain words for a starting sentence; brackets denote parse forests")
    words = value.split()
    if len(words) > MAX_WORDS:
        raise GrammarLimitError(f"Sentences must not exceed {MAX_WORDS} words")
    for word in words:
        if word not in WORD_CATS:
            raise ValueError(
                f"Unknown word: {word}. Use only words from the toy fragment's lexicon."
            )
    forest = tuple(Tree(cat, word=word) for word in words for cat in WORD_CATS[word])
    validate_limits(forest)
    return forest


def parse_state(value: Any) -> tuple[Tree, ...]:
    """Parse a state: a plain starting sentence or a bracketed parse forest."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("current must be a non-empty sentence or parse forest")
    if "[" in value:
        forest = Parser(value).forest()
        validate_limits(forest)
        return forest
    return parse_sentence(value)


def _derivable(cats: tuple[str, ...]) -> set[str]:
    """Categories that can span each subsequence when each item is a leaf."""
    n = len(cats)
    if n == 0:
        return set()
    table: list[list[set[str]]] = [[set() for _ in range(n + 1)] for _ in range(n + 1)]
    for i, cat in enumerate(cats):
        table[i][i + 1].add(cat)
    for length in range(2, n + 1):
        for start in range(n - length + 1):
            end = start + length
            cell = table[start][end]
            for lhs, rhs in PRODUCTIONS:
                if len(rhs) == 2:
                    for split in range(start + 1, end):
                        if rhs[0] in table[start][split] and rhs[1] in table[split][end]:
                            cell.add(lhs)
                else:
                    for first in range(start + 1, end - 1):
                        for second in range(first + 1, end):
                            if (
                                rhs[0] in table[start][first]
                                and rhs[1] in table[first][second]
                                and rhs[2] in table[second][end]
                            ):
                                cell.add(lhs)
    return table[0][n]


def completable(forest: tuple[Tree, ...]) -> bool:
    """Whether the forest can still reduce to a single complete S parse."""
    return "S" in _derivable(tuple(tree.cat for tree in forest))


def count_parses(words: tuple[str, ...]) -> tuple[int, bool]:
    """Number of distinct complete parses of the word sequence, chart-counted."""
    n = len(words)
    if n == 0:
        return 0, False
    capped = False
    table: list[list[dict[str, int]]] = [[{} for _ in range(n + 1)] for _ in range(n + 1)]
    for i, word in enumerate(words):
        for cat in WORD_CATS.get(word, ()):
            table[i][i + 1][cat] = table[i][i + 1].get(cat, 0) + 1
    for length in range(2, n + 1):
        for start in range(n - length + 1):
            end = start + length
            cell = table[start][end]
            for lhs, rhs in PRODUCTIONS:
                total = 0
                if len(rhs) == 2:
                    for split in range(start + 1, end):
                        total += (
                            table[start][split].get(rhs[0], 0)
                            * table[split][end].get(rhs[1], 0)
                        )
                else:
                    for first in range(start + 1, end - 1):
                        for second in range(first + 1, end):
                            total += (
                                table[start][first].get(rhs[0], 0)
                                * table[first][second].get(rhs[1], 0)
                                * table[second][end].get(rhs[2], 0)
                            )
                if total:
                    cell[lhs] = min(cell.get(lhs, 0) + total, MAX_PARSE_COUNT)
                    if cell[lhs] >= MAX_PARSE_COUNT:
                        capped = True
    return table[0][n].get("S", 0), capped


def describe(value: str) -> dict[str, Any]:
    forest = parse_state(value)
    words = yield_words(forest)
    parse_count, capped = count_parses(words)
    moves: list[dict[str, Any]] = []
    omitted = 0

    def add(index: int, lhs: str, rhs: tuple[str, ...]) -> None:
        nonlocal omitted
        arity = len(rhs)
        group = forest[index:index + arity]
        candidate = forest[:index] + (Tree(lhs, children=group),) + forest[index + arity:]
        try:
            validate_limits(candidate)
            text = format_forest(candidate)
            if parse_state(text) != candidate:
                raise RuntimeError("Grammar formatting changed the tree")
            if yield_words(candidate) != words:
                raise RuntimeError("Grammar reduction changed the word sequence")
        except GrammarLimitError:
            omitted += 1
            return
        moves.append({
            "id": f"move-{len(moves)}", "rule": 1, "position": index,
            "label": f"Reduce at {index}: {lhs} → {' '.join(rhs)}",
            "detail": (
                f"Combine {' and '.join(' '.join(yield_words((tree,))) for tree in group)} "
                f"into one {lhs} constituent by {lhs} → {' '.join(rhs)}."
            ),
            "result": text, "solved": is_solved(candidate),
            "progress": len(candidate), "completable": completable(candidate),
        })

    for index in range(len(forest)):
        for lhs, rhs in PRODUCTIONS:
            arity = len(rhs)
            if index + arity > len(forest):
                continue
            if tuple(tree.cat for tree in forest[index:index + arity]) != rhs:
                continue
            add(index, lhs, rhs)

    solved = is_solved(forest)
    return {
        "system": "grammar", "current": format_forest(forest), "moves": moves,
        "solved": solved, "progress": len(forest),
        "parse_count": parse_count, "parse_count_capped": capped,
        "solution_kind": "parsed" if solved else "incomplete",
        "omitted_for_limits": omitted,
        "rules": RULES,
        "limits": {"characters": MAX_CHARS, "nodes": MAX_NODES,
                   "depth": MAX_DEPTH, "words": MAX_WORDS},
    }


def reference_parse(value: str, max_steps: int = 100) -> tuple[list[dict[str, Any]], str | None]:
    """Chart-guided witness: repeatedly take the first menu reduction that
    keeps a complete parse reachable. Greedy-safe because a completable
    reduction always leaves another completable reduction available until
    the parse completes. Returns the applied path and the final forest
    (None if the budget ran out or no completable reduction exists)."""
    path: list[dict[str, Any]] = []
    state = describe(value)
    while not state["solved"] and len(path) < max_steps:
        move = next((m for m in state["moves"] if m["completable"]), None)
        if move is None:
            break
        path.append({"current": state["current"], "move": move})
        state = describe(move["result"])
    return path, (state["current"] if state["solved"] else None)


def select_move(
    policy: str, current: str, goal: str, history: list[str],
    candidates: list[dict[str, Any]], model_choice: dict[str, Any],
    probabilities: dict[str, float], max_length: int,
    explanation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    evidence: dict[str, Any] = {"filters": [], "scores": {}}
    if explanation is not None:
        explanation.update(evidence)
    if policy == "model":
        if explanation is not None:
            explanation["reason"] = "Provider choice preserved; execution limits still apply."
        return model_choice
    if policy != "guided":
        raise ValueError("policy must be guided or model")
    pool = candidates
    for reason, predicate in (
        ("Prefer moves within the length budget.", lambda move: len(move["result"]) <= max_length),
        ("Prefer a completed parse.", lambda move: move["solved"]),
        ("Prefer unvisited parse states.", lambda move: move["result"] not in history),
        ("Prefer reductions that keep a complete parse reachable.", lambda move: move["completable"]),
    ):
        retained = [move for move in pool if predicate(move)]
        if retained:
            pool = retained
            evidence["filters"].append({"reason": reason, "eligible": [move["id"] for move in pool]})
    for move in pool:
        heuristic = -float(move["progress"])
        adjustment = 5.0 * probabilities.get(move["id"], 0.0)
        evidence["scores"][move["id"]] = {
            "heuristic": heuristic, "probability_adjustment": adjustment,
            "total": heuristic + adjustment,
        }
    if explanation is not None:
        explanation["reason"] = (
            "Prefer chart-verified reductions that keep a complete parse reachable and shrink "
            "the constituent count; add group-local model probability. Ties use probability, "
            "then menu order."
        )
    return max(pool, key=lambda move: (
        evidence["scores"][move["id"]]["total"], probabilities.get(move["id"], 0.0),
    ))
