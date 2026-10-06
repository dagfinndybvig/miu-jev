"""Exact, bounded rewrites of single-variable linear equations over rationals."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from math import lcm
import re
from typing import Any, Callable, Iterator, Literal


DEFAULT_EQUATION = "2 * (x + 3) = 14"
GOAL = "Isolate x"
MAX_LENGTH = 512
MAX_NODES = 128
MAX_DEPTH = 24
MAX_NUMBER_BITS = 128
RULES = [
    "1: Simplify arithmetic and identities in a subtree",
    "2: Distribute a numeric factor over a sum or difference",
    "3: Expand and collect one side into a*x + b",
    "4: Subtract a visible top-level term from both sides",
    "5: Divide both sides by a visible nonzero numeric coefficient",
    "6: Multiply both sides by the LCM of numeric denominators",
    "7: Swap the two sides",
]


class AlgebraLimitError(ValueError):
    pass


@dataclass(frozen=True)
class Expr:
    op: Literal["number", "x", "+", "-", "*", "/"]
    args: tuple[Expr, ...] = ()
    value: Fraction = Fraction(0)


@dataclass(frozen=True)
class Equation:
    left: Expr
    right: Expr


X = Expr("x")
ZERO = Expr("number")
ONE = Expr("number", value=Fraction(1))


def number(value: Fraction | int) -> Expr:
    value = Fraction(value)
    if max(abs(value.numerator).bit_length(), value.denominator.bit_length()) > MAX_NUMBER_BITS:
        raise AlgebraLimitError("Algebra numbers must fit within 128-bit numerators and denominators")
    return Expr("number", value=value)


def binary(op: Literal["+", "-", "*", "/"], left: Expr, right: Expr) -> Expr:
    if left.op == right.op == "number":
        a, b = left.value, right.value
        if op == "+":
            return number(a + b)
        if op == "-":
            return number(a - b)
        if op == "*":
            return number(a * b)
        if not b:
            raise ValueError("Division by zero is not defined")
        return number(a / b)
    return Expr(op, (left, right))


def contains_x(expr: Expr) -> bool:
    return expr.op == "x" or any(contains_x(child) for child in expr.args)


def linear(expr: Expr) -> tuple[Fraction, Fraction]:
    if expr.op == "number":
        return Fraction(0), expr.value
    if expr.op == "x":
        return Fraction(1), Fraction(0)
    left, right = expr.args
    a, b = linear(left)
    c, d = linear(right)
    if expr.op == "+":
        result = a + c, b + d
    elif expr.op == "-":
        result = a - c, b - d
    elif expr.op == "*":
        if contains_x(left) and contains_x(right):
            raise ValueError("Only linear equations are supported; do not multiply variable expressions")
        result = a * d + b * c, b * d
    else:
        if contains_x(right):
            raise ValueError("Variable denominators are not supported")
        if not d:
            raise ValueError("Division by zero is not defined")
        result = a / d, b / d
    for value in result:
        number(value)
    return result


def walk(expr: Expr, path: tuple[int, ...] = ()) -> Iterator[tuple[tuple[int, ...], Expr]]:
    yield path, expr
    for index, child in enumerate(expr.args):
        yield from walk(child, path + (index,))


def validate_tree(equation: Equation) -> None:
    nodes = [(path, expr) for side in (equation.left, equation.right) for path, expr in walk(side)]
    if len(nodes) > MAX_NODES:
        raise AlgebraLimitError(f"Algebra equations must not exceed {MAX_NODES} syntax nodes")
    if any(len(path) >= MAX_DEPTH for path, _ in nodes):
        raise AlgebraLimitError(f"Algebra expressions must be less than {MAX_DEPTH} levels deep")
    linear(equation.left)
    linear(equation.right)


class Parser:
    def __init__(self, text: str) -> None:
        self.tokens: list[str] = []
        offset = 0
        for match in re.finditer(r"[0-9]+|x|[()+*/=-]", text):
            if text[offset:match.start()].strip():
                raise ValueError("Use only x, integers, +, -, *, /, parentheses, and one =")
            self.tokens.append(match.group())
            offset = match.end()
        if text[offset:].strip():
            raise ValueError("Use only x, integers, +, -, *, /, parentheses, and one =")
        if len(self.tokens) > MAX_NODES * 2:
            raise AlgebraLimitError("Too many algebra tokens")
        self.index = 0

    def peek(self) -> str:
        return self.tokens[self.index] if self.index < len(self.tokens) else ""

    def take(self, token: str) -> bool:
        if self.peek() == token:
            self.index += 1
            return True
        return False

    def expression(self, depth: int = 0) -> Expr:
        result = self.product(depth)
        while self.peek() in ("+", "-"):
            op = self.peek()
            self.index += 1
            right = self.product(depth)
            result = binary("+" if op == "+" else "-", result, right)
        return result

    def product(self, depth: int) -> Expr:
        result = self.factor(depth)
        while self.peek() in ("*", "/", "x", "("):
            op = "/" if self.take("/") else "*"
            if op == "*":
                self.take("*")
            result = binary(op, result, self.factor(depth))
        return result

    def factor(self, depth: int) -> Expr:
        if depth >= MAX_DEPTH:
            raise AlgebraLimitError(f"Algebra expressions must be less than {MAX_DEPTH} levels deep")
        if self.take("+"):
            return self.factor(depth + 1)
        if self.take("-"):
            return binary("*", number(-1), self.factor(depth + 1))
        if self.take("("):
            result = self.expression(depth + 1)
            if not self.take(")"):
                raise ValueError("Missing closing parenthesis")
            return result
        if self.take("x"):
            return X
        token = self.peek()
        if token.isdigit():
            self.index += 1
            if len(token) > 39:
                raise AlgebraLimitError("Algebra integer literals must not exceed 39 digits")
            return number(int(token))
        raise ValueError("Expected x, a number, or a parenthesized expression")


def parse_equation(value: Any) -> Equation:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("current must be a non-empty linear equation")
    if len(value) > MAX_LENGTH:
        raise AlgebraLimitError(f"Algebra equations must not exceed {MAX_LENGTH} characters")
    parser = Parser(value)
    left = parser.expression()
    if not parser.take("="):
        raise ValueError("An equation must contain exactly one =")
    right = parser.expression()
    if parser.peek():
        raise ValueError("Unexpected token after the equation")
    equation = Equation(left, right)
    validate_tree(equation)
    if len(format_equation(equation)) > MAX_LENGTH:
        raise AlgebraLimitError(f"The formatted equation exceeds {MAX_LENGTH} characters")
    return equation


def format_expr(expr: Expr, parent: int = 0, right_child: bool = False) -> str:
    if expr.op == "x":
        return "x"
    if expr.op == "number":
        text = str(expr.value)
        precedence = 2 if expr.value.denominator != 1 else 3
    else:
        precedence = 1 if expr.op in ("+", "-") else 2
        left, right = expr.args
        text = f"{format_expr(left, precedence)} {expr.op} {format_expr(right, precedence, True)}"
    if precedence < parent or (right_child and precedence == parent):
        return f"({text})"
    return text


def format_equation(equation: Equation) -> str:
    return f"{format_expr(equation.left)} = {format_expr(equation.right)}"


def solution(equation: Equation) -> tuple[str, Fraction | None]:
    a, b = linear(equation.left)
    c, d = linear(equation.right)
    if a == c:
        return ("all", None) if b == d else ("none", None)
    value = (d - b) / (a - c)
    number(value)
    return "unique", value


def is_solved(equation: Equation) -> bool:
    return (
        equation.left == X and equation.right.op == "number"
    ) or equation.left.op == equation.right.op == "number"


def progress(equation: Equation) -> int:
    if is_solved(equation):
        return 0
    a, b = linear(equation.left)
    nodes = sum(1 for side in (equation.left, equation.right) for _ in walk(side))
    right_variables = sum(node.op == "x" for _, node in walk(equation.right))
    return nodes + 6 * right_variables + 4 * bool(b) + 3 * (a != 1)


def simplify(expr: Expr) -> Expr:
    if not expr.args:
        return expr
    left, right = (simplify(child) for child in expr.args)
    if expr.op == "+":
        if left == ZERO:
            return right
        if right == ZERO:
            return left
    elif expr.op == "-":
        if right == ZERO:
            return left
        if left == right:
            return ZERO
    elif expr.op == "*":
        if left == ZERO or right == ZERO:
            return ZERO
        if left == ONE:
            return right
        if right == ONE:
            return left
    elif expr.op == "/":
        if right == ONE:
            return left
        if left == ZERO:
            return ZERO
        if left.op == "*":
            for index in (0, 1):
                if left.args[index] == right:
                    return left.args[1 - index]
    return binary(expr.op, left, right)


def canonical(a: Fraction, b: Fraction) -> Expr:
    variable = ZERO if not a else X if a == 1 else binary("*", number(a), X)
    if not a:
        return number(b)
    if not b:
        return variable
    return binary("+" if b > 0 else "-", variable, number(abs(b)))


def replace(expr: Expr, path: tuple[int, ...], replacement: Expr) -> Expr:
    if not path:
        return replacement
    index = path[0]
    args = list(expr.args)
    args[index] = replace(args[index], path[1:], replacement)
    return binary(expr.op, args[0], args[1])


def terms(expr: Expr, sign: int = 1) -> list[Expr]:
    if expr.op == "+":
        return terms(expr.args[0], sign) + terms(expr.args[1], sign)
    if expr.op == "-":
        return terms(expr.args[0], sign) + terms(expr.args[1], -sign)
    return [expr if sign == 1 else simplify(binary("*", number(-1), expr))]


def subtract_term(expr: Expr, term: Expr) -> Expr:
    parts = terms(expr)
    if term in parts:
        parts.remove(term)
        result = ZERO
        for part in parts:
            result = simplify(binary("+", result, part))
        return result
    return simplify(binary("-", expr, term))


def describe(value: str) -> dict[str, Any]:
    equation = parse_equation(value)
    signature = solution(equation)
    moves: list[dict[str, Any]] = []
    omitted = 0

    def add(
        rule: int, position: str, label: str, detail: str,
        build: Callable[[], Equation],
    ) -> None:
        nonlocal omitted
        try:
            candidate = build()
            if candidate == equation:
                return
            validate_tree(candidate)
            text = format_equation(candidate)
            if len(text) > MAX_LENGTH:
                raise AlgebraLimitError("Result exceeds the equation character bound")
            if solution(candidate) != signature:
                raise RuntimeError("Algebra rewrite changed the solution set")
            if parse_equation(text) != candidate:
                raise RuntimeError("Algebra formatting changed the expression tree")
        except AlgebraLimitError:
            omitted += 1
            return
        moves.append({
            "id": f"move-{len(moves)}", "rule": rule, "position": position,
            "label": label, "detail": detail, "result": text,
            "solved": is_solved(candidate), "progress": progress(candidate),
        })

    for side_name, expr in (("left", equation.left), ("right", equation.right)):
        def on_side(updated: Expr) -> Equation:
            return Equation(updated, equation.right) if side_name == "left" else Equation(equation.left, updated)

        for path, node in walk(expr):
            position = side_name + "".join(f".{index}" for index in path)
            reduced = simplify(node)
            if reduced != node:
                add(1, position, f"Simplify at {position}",
                    "Fold exact arithmetic and remove additive/multiplicative identities in this subtree.",
                    lambda: on_side(replace(expr, path, reduced)))
            if node.op == "*":
                for index in (0, 1):
                    scalar, other = node.args[index], node.args[1 - index]
                    if scalar.op == "number" and other.op in ("+", "-"):
                        add(2, position, f"Distribute at {position}",
                            f"Distribute the constant {scalar.value} over both terms, using exact arithmetic.",
                            lambda: on_side(replace(expr, path, binary(
                                other.op, binary("*", scalar, other.args[0]),
                                binary("*", scalar, other.args[1]),
                            ))))
        collected = canonical(*linear(expr))
        add(3, side_name, f"Expand and collect the {side_name} side",
            "Expand this linear expression and combine its x coefficients and constants exactly.",
            lambda: on_side(collected))

    for term in dict.fromkeys(terms(equation.left) + terms(equation.right)):
        if term != ZERO:
            add(4, "both", f"Subtract {format_expr(term)} from both sides",
                "Subtract the same visible top-level term from both sides and cancel matching terms.",
                lambda: Equation(subtract_term(equation.left, term), subtract_term(equation.right, term)))

    divisors: set[Fraction] = set()
    denominator = 1
    for side in (equation.left, equation.right):
        for _, node in walk(side):
            if node.op == "number":
                denominator = lcm(denominator, node.value.denominator)
            if node.op == "/" and node.args[1].op == "number":
                denominator = lcm(denominator, abs(node.args[1].value.numerator))
            if node.op == "*":
                for index in (0, 1):
                    scalar, other = node.args[index], node.args[1 - index]
                    if scalar.op == "number" and contains_x(other) and scalar.value not in (0, 1):
                        divisors.add(scalar.value)
    for divisor in sorted(divisors):
        add(5, "both", f"Divide both sides by {divisor}",
            f"The explicit numeric coefficient {divisor} is nonzero, so division preserves solutions.",
            lambda: Equation(
                simplify(binary("/", equation.left, number(divisor))),
                simplify(binary("/", equation.right, number(divisor))),
            ))
    if denominator > 1:
        add(6, "both", f"Multiply both sides by {denominator}",
            "Use the positive least common multiple of numeric denominators; collect terms to clear fractions.",
            lambda: Equation(
                binary("*", number(denominator), equation.left),
                binary("*", number(denominator), equation.right),
            ))
    add(7, "both", "Swap the two sides", "Equality is symmetric.",
        lambda: Equation(equation.right, equation.left))

    return {
        "system": "algebra", "current": format_equation(equation), "moves": moves,
        "solved": is_solved(equation), "progress": progress(equation),
        "solution_kind": signature[0], "omitted_for_limits": omitted,
        "rules": RULES,
        "limits": {"characters": MAX_LENGTH, "nodes": MAX_NODES, "depth": MAX_DEPTH,
                   "number_bits": MAX_NUMBER_BITS},
    }


def reference_solution(
    value: str, max_steps: int = 100,
) -> tuple[list[dict[str, Any]], str | None]:
    """Greedy guided witness: repeatedly apply the guided policy with zero
    provider probability until the equation is solved (an isolated x, or a
    numeric identity/contradiction). Returns the applied path and the solved
    equation (None if the budget ran out, meaning the finite vocabulary did
    not admit a guided solution in budget, not that none exists)."""
    path: list[dict[str, Any]] = []
    state = describe(value)
    history = [state["current"]]
    while not state["solved"] and len(path) < max_steps:
        moves = state["moves"]
        if not moves:
            break
        move = select_move(
            "guided", state["current"], GOAL, history, moves, moves[0],
            {}, MAX_LENGTH,
        )
        path.append({"current": state["current"], "move": move})
        state = describe(move["result"])
        history.append(state["current"])
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
        ("Prefer solved equations.", lambda move: move["solved"]),
        ("Prefer unvisited equations.", lambda move: move["result"] not in history),
    ):
        retained = [move for move in pool if predicate(move)]
        if retained:
            pool = retained
            evidence["filters"].append({"reason": reason, "eligible": [move["id"] for move in pool]})
    for move in pool:
        heuristic = -10.0 * move["progress"]
        adjustment = 5.0 * probabilities.get(move["id"], 0.0)
        evidence["scores"][move["id"]] = {
            "heuristic": heuristic, "probability_adjustment": adjustment,
            "total": heuristic + adjustment,
        }
    if explanation is not None:
        explanation["reason"] = (
            "Prefer lower structural complexity, fewer right-side x terms, and an isolated left-side x; "
            "add group-local model probability. Ties use probability, then menu order."
        )
    return max(pool, key=lambda move: (
        evidence["scores"][move["id"]]["total"], probabilities.get(move["id"], 0.0),
    ))
