"""Exact, bounded beta reduction of untyped lambda terms."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterator, Literal

import re


DEFAULT_TERM = "(\\x. x x) (\\y. y)"
GOAL = "Normal form"
MAX_CHARS = 512
MAX_NODES = 256
MAX_DEPTH = 96
LETTERS = "abcdefghijklmnopqrstuvwxyz"
RULES = [
    "1: Beta-reduce the redex at a marked position",
]
TOKEN = re.compile(r"[a-z]|\\|λ|[().]")

PATH_WORDS = {"f": "the function part", "a": "the argument", "b": "the abstraction body"}


class LambdaLimitError(ValueError):
    pass


@dataclass(frozen=True)
class Term:
    kind: Literal["var", "lam", "app"]
    name: str = ""
    body: "Term | None" = None
    arg: "Term | None" = None


def size(term: Term) -> int:
    if term.kind == "var":
        return 1
    if term.kind == "lam":
        return 1 + size(term.body)
    return 1 + size(term.body) + size(term.arg)


def depth(term: Term) -> int:
    if term.kind == "var":
        return 1
    if term.kind == "lam":
        return 1 + depth(term.body)
    return 1 + max(depth(term.body), depth(term.arg))


def free_vars(term: Term) -> set[str]:
    if term.kind == "var":
        return {term.name}
    if term.kind == "lam":
        return free_vars(term.body) - {term.name}
    return free_vars(term.body) | free_vars(term.arg)


def occurrences(name: str, term: Term) -> int:
    if term.kind == "var":
        return int(term.name == name)
    if term.kind == "lam":
        return 0 if term.name == name else occurrences(name, term.body)
    return occurrences(name, term.body) + occurrences(name, term.arg)


def fresh_name(used: set[str]) -> str:
    for letter in LETTERS:
        if letter not in used:
            return letter
    raise LambdaLimitError("No fresh variable name is available within a-z")


def substitute(term: Term, name: str, replacement: Term) -> Term:
    """Capture-avoiding substitution of `replacement` for free `name` in `term`."""
    if term.kind == "var":
        return replacement if term.name == name else term
    if term.kind == "lam":
        if term.name == name:
            return term
        if term.name in free_vars(replacement) and name in free_vars(term.body):
            renamed = fresh_name(free_vars(term.body) | free_vars(replacement) | {name})
            body = substitute(substitute(term.body, term.name, Term("var", renamed)), name, replacement)
            return Term("lam", name=renamed, body=body)
        return Term("lam", name=term.name, body=substitute(term.body, name, replacement))
    return Term(
        "app",
        body=substitute(term.body, name, replacement),
        arg=substitute(term.arg, name, replacement),
    )


def _de_bruijn(term: Term, scope: tuple[str, ...]) -> tuple:
    if term.kind == "var":
        if term.name in scope:
            return ("bound", scope.index(term.name))
        return ("free", term.name)
    if term.kind == "lam":
        return ("lam", _de_bruijn(term.body, (term.name,) + scope))
    return ("app", _de_bruijn(term.body, scope), _de_bruijn(term.arg, scope))


def alpha_equal(left: Term, right: Term) -> bool:
    return _de_bruijn(left, ()) == _de_bruijn(right, ())


def walk(term: Term, path: str = "") -> Iterator[tuple[str, Term]]:
    yield path, term
    if term.kind == "lam":
        yield from walk(term.body, path + "b")
    elif term.kind == "app":
        yield from walk(term.body, path + "f")
        yield from walk(term.arg, path + "a")


def replace(term: Term, path: str, replacement: Term) -> Term:
    if not path:
        return replacement
    head, rest = path[0], path[1:]
    if head == "b":
        return Term("lam", name=term.name, body=replace(term.body, rest, replacement))
    if head == "f":
        return Term("app", body=replace(term.body, rest, replacement), arg=term.arg)
    return Term("app", body=term.body, arg=replace(term.arg, rest, replacement))


def is_redex(term: Term) -> bool:
    return term.kind == "app" and term.body.kind == "lam"


def count_redexes(term: Term) -> int:
    return sum(is_redex(node) for _, node in walk(term))


def is_normal_form(term: Term) -> bool:
    return count_redexes(term) == 0


def progress(term: Term) -> int:
    return size(term) + 2 * count_redexes(term)


def contract(redex: Term) -> Term:
    abstraction, argument = redex.body, redex.arg
    return substitute(abstraction.body, abstraction.name, argument)


def describe_position(path: str) -> str:
    if not path:
        return "the outermost application"
    return "inside " + ", then inside ".join(PATH_WORDS[step] for step in path)


class Parser:
    def __init__(self, text: str) -> None:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("current must be a non-empty lambda term")
        if len(text) > MAX_CHARS:
            raise LambdaLimitError(f"Lambda terms must not exceed {MAX_CHARS} characters")
        self.tokens: list[str] = []
        offset = 0
        for match in TOKEN.finditer(text):
            if text[offset:match.start()].strip():
                raise ValueError("Use only variables a-z, λ or \\, ., and parentheses")
            self.tokens.append(match.group())
            offset = match.end()
        if text[offset:].strip():
            raise ValueError("Use only variables a-z, λ or \\, ., and parentheses")
        if not self.tokens:
            raise ValueError("current must be a non-empty lambda term")
        self.index = 0

    def peek(self) -> str:
        return self.tokens[self.index] if self.index < len(self.tokens) else ""

    def take(self, token: str) -> bool:
        if self.peek() == token:
            self.index += 1
            return True
        return False

    def parse(self) -> Term:
        term = self.application()
        if self.peek():
            raise ValueError("Unexpected token after the term")
        return term

    def application(self) -> Term:
        result = self.atom()
        while self.peek() not in ("", ")", "."):
            result = Term("app", body=result, arg=self.atom())
        return result

    def atom(self) -> Term:
        if self.take("λ") or self.take("\\"):
            name = self.peek()
            if name not in LETTERS:
                raise ValueError("An abstraction must bind a single lowercase variable")
            self.index += 1
            if not self.take("."):
                raise ValueError("An abstraction needs a . after its bound variable")
            return Term("lam", name=name, body=self.application())
        if self.take("("):
            inner = self.application()
            if not self.take(")"):
                raise ValueError("Missing closing parenthesis")
            return inner
        token = self.peek()
        if token in LETTERS:
            self.index += 1
            return Term("var", name=token)
        raise ValueError("Expected a variable, an abstraction like λx.M, or a parenthesized term")


def parse_term(value: Any) -> Term:
    term = Parser(value).parse()
    if size(term) > MAX_NODES:
        raise LambdaLimitError(f"Lambda terms must not exceed {MAX_NODES} syntax nodes")
    if depth(term) > MAX_DEPTH:
        raise LambdaLimitError(f"Lambda terms must be at most {MAX_DEPTH} levels deep")
    if len(format_term(term)) > MAX_CHARS:
        raise LambdaLimitError(f"The formatted term exceeds {MAX_CHARS} characters")
    return term


def format_term(term: Term) -> str:
    if term.kind == "var":
        return term.name
    if term.kind == "lam":
        return f"λ{term.name}.{format_term(term.body)}"
    left = format_term(term.body)
    if term.body.kind == "lam":
        left = f"({left})"
    right = format_term(term.arg)
    if term.arg.kind in ("lam", "app"):
        right = f"({right})"
    return f"{left} {right}"


def describe(value: str) -> dict[str, Any]:
    term = parse_term(value)
    moves: list[dict[str, Any]] = []
    omitted = 0

    def add(position: str, redex: Term) -> None:
        nonlocal omitted
        abstraction, argument = redex.body, redex.arg
        duplication = (occurrences(abstraction.name, abstraction.body) - 1) * size(argument)
        try:
            result = contract(redex)
            if size(result) > MAX_NODES:
                raise LambdaLimitError("Result exceeds the term node bound")
            if depth(result) > MAX_DEPTH:
                raise LambdaLimitError("Result exceeds the term depth bound")
            text = format_term(result)
            if len(text) > MAX_CHARS:
                raise LambdaLimitError("Result exceeds the term character bound")
            if not alpha_equal(parse_term(text), result):
                raise RuntimeError("Lambda formatting changed the term")
        except LambdaLimitError:
            omitted += 1
            return
        moves.append({
            "id": f"move-{len(moves)}", "rule": 1, "position": position or "root",
            "label": f"Beta at {position or 'root'}",
            "detail": f"Contract {describe_position(position)} by substituting the "
                      f"argument for the bound variable{'' if duplication == 0 else f' (duplicates {duplication} nodes of work)'}.",
            "result": text, "solved": is_normal_form(result),
            "progress": progress(result), "redexes": count_redexes(result),
            "duplication": duplication,
        })

    for position, node in list(walk(term)):
        if is_redex(node):
            add(position, node)

    return {
        "system": "lambda", "current": format_term(term), "moves": moves,
        "solved": is_normal_form(term), "progress": progress(term),
        "redexes": count_redexes(term), "solution_kind": "normal" if is_normal_form(term) else "reducible",
        "omitted_for_limits": omitted,
        "rules": RULES,
        "limits": {"characters": MAX_CHARS, "nodes": MAX_NODES, "depth": MAX_DEPTH},
    }


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
        ("Prefer results that are normal forms.", lambda move: move["solved"]),
        ("Prefer unvisited terms.", lambda move: move["result"] not in history),
    ):
        retained = [move for move in pool if predicate(move)]
        if retained:
            pool = retained
            evidence["filters"].append({"reason": reason, "eligible": [move["id"] for move in pool]})
    for move in pool:
        position_depth = 0 if move["position"] == "root" else len(move["position"])
        heuristic = -(
            move["progress"] + move["duplication"] + 3 * position_depth
        )
        adjustment = 5.0 * probabilities.get(move["id"], 0.0)
        evidence["scores"][move["id"]] = {
            "heuristic": heuristic, "probability_adjustment": adjustment,
            "total": heuristic + adjustment,
        }
    if explanation is not None:
        explanation["reason"] = (
            "Prefer outer, cheap, non-duplicating contractions toward a normal form "
            "(leftmost-outermost order always finds one when it exists); add group-local "
            "model probability. Ties use probability, then menu order."
        )
    return max(pool, key=lambda move: (
        evidence["scores"][move["id"]]["total"], probabilities.get(move["id"], 0.0),
    ))
