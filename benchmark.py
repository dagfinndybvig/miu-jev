"""Bounded, reproducible comparisons; hosted providers require explicit opt-in."""

from __future__ import annotations

import argparse
from collections import deque
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import statistics
import sys
import time
from typing import Any

import lambda_calc
from app import (
    DEFAULT_MODELS, MAX_MIU_LENGTH, DecisionError, choose_move, legal_moves,
    require_compatible_ollama, select_move,
)

OMEGA = r"(\x. x x) (\x. x x)"
OMEGA_ATOM = rf"({OMEGA})"
WRONG_HINT_RECOMMENDATION = (
    "The computed guidance recommends this contraction as the most direct "
    "progress toward the normal form."
)
LAMBDA_ADD = r"(\m.\n.\f.\x. m f (n f x))"
LAMBDA_MUL = r"(\m.\n.\f. m (n f))"
LAMBDA_SUCC = r"(\n.\f.\x. f (n f x))"


def church(n: int) -> str:
    body = "x"
    for _ in range(n):
        body = f"f ({body})"
    return rf"(\f.\x. {body})"


def _wrap_identities(inner: str, count: int) -> str:
    for _ in range(count):
        inner = rf"(\z. z) ({inner})"
    return inner


def tournament_terms() -> list[tuple[str, str]]:
    """Hand-crafted majority-losing menus that stress the tournament path.
    One cheap outer discard reaches the normal form in two steps; the rest of
    the menu is a majority of losing options — instant-cycle Ω self-loops in
    the hard term, budget-wasting identity chains in the soft one — so a
    provider must survive two-choice grouping to find the winner."""
    discard = r"(\a.\b. b)"
    omegas = " ".join([OMEGA_ATOM] * 18)
    hard = rf"{discard} ({_wrap_identities(omegas, 8)}) x"
    soft = rf"{discard} ({_wrap_identities('x', 40)}) x"
    return [(hard, "tournament"), (soft, "tournament")]


def lambda_terms() -> list[tuple[str, str]]:
    """Curated lambda terms: reachable arithmetic, strategy traps that only
    normal order escapes, and duplication-heavy growth terms."""
    terms: list[tuple[str, str]] = []
    for left in range(0, 3):
        for right in range(1, 4):
            terms.append((f"({LAMBDA_ADD}) ({church(left)}) ({church(right)})", "reachable"))
            terms.append((f"({LAMBDA_MUL}) ({church(left)}) ({church(right)})", "reachable"))
    for start in range(0, 4):
        chain = church(start)
        for _ in range(2):
            chain = f"({LAMBDA_SUCC}) ({chain})"
        terms.append((chain, "reachable"))
    terms.extend([
        (rf"(\x.\y. y) {OMEGA_ATOM}", "trap"),
        (rf"(\a. a) ((\x.\y. y) {OMEGA_ATOM})", "trap"),
        (rf"(\z. z ((\x.\y. y) {OMEGA_ATOM})) (\w. w)", "trap"),
        (r"(\x. x x) ((\y. y y) z)", "growth"),
        (r"(\x. x x x x) (\y. y)", "growth"),
        (r"(\p.\q. p q q) ((\z. z z) (\w. w))", "growth"),
    ])
    terms.extend(tournament_terms())
    return terms


NOVEL_MAX_REFERENCE_STEPS = 14
NOVEL_MIN_REFERENCE_STEPS = 3


def _novel_tree(rng: random.Random) -> str:
    """One seeded composition: Church arithmetic recombined through random
    operand order, nested operator trees, identity applications, and
    constant wrappers — shapes no textbook prints."""

    def numeral() -> str:
        return church(rng.randint(0, 3))

    def node(depth: int) -> str:
        if depth <= 0 or rng.random() < 0.3:
            return numeral()
        choice = rng.random()
        if choice < 0.5:
            operator = rng.choice((LAMBDA_ADD, LAMBDA_MUL))
            left, right = node(depth - 1), node(depth - 1)
            if rng.random() < 0.5:
                left, right = right, left
            return f"({operator} {left} {right})"
        if choice < 0.75:
            return f"({LAMBDA_SUCC} {node(depth - 1)})"
        if choice < 0.9:
            return rf"(\z. z) {node(depth - 1)}"
        return rf"(\p.\q. q) {numeral()} {node(depth - 1)}"

    return node(3)


def novel_lambda_terms(
    seed: int, count: int,
    max_reference_steps: int = NOVEL_MAX_REFERENCE_STEPS,
) -> list[tuple[str, str]]:
    """Seeded lambda compositions that stay ahead of the training curriculum.
    Every term normalizes within the reference-step bound and is distinct
    from the curated pool, so exercises are not verbatim recall."""
    rng = random.Random(seed)
    seen = {term for term, _ in lambda_terms()}
    results: list[tuple[str, str]] = []
    attempts = 0
    while len(results) < count:
        attempts += 1
        if attempts > count * 200:
            raise ValueError(
                "Novel term generation exhausted its attempt budget; "
                "lower --novel-terms or extend the composition grammar"
            )
        try:
            canonical = lambda_calc.format_term(lambda_calc.parse_term(_novel_tree(rng)))
            path, normal_form = lambda_calc.normal_order_witness(canonical, max_steps=100)
        except ValueError:
            continue
        if (
            normal_form is None
            or not NOVEL_MIN_REFERENCE_STEPS <= len(path) <= max_reference_steps
            or canonical in seen
        ):
            continue
        seen.add(canonical)
        results.append((canonical, "novel"))
    return results


def target_distance(value: str, target: str) -> int:
    previous = list(range(len(target) + 1))
    for row, character in enumerate(value, 1):
        current = [row]
        for column, other in enumerate(target, 1):
            current.append(min(
                current[-1] + 1, previous[column] + 1,
                previous[column - 1] + (character != other),
            ))
        previous = current
    return previous[-1]


def generate_cases(
    seed: int, count: int, max_length: int, max_depth: int, max_states: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    parents: dict[str, tuple[str, dict[str, Any]] | None] = {"MI": None}
    depths = {"MI": 0}
    queue = deque(["MI"])
    truncated = False
    while queue and not truncated:
        current = queue.popleft()
        if depths[current] >= max_depth:
            continue
        for move in legal_moves(current):
            successor = move["result"]
            if len(successor) > max_length or successor in parents:
                continue
            if len(parents) >= max_states:
                truncated = True
                break
            parents[successor] = (current, move)
            depths[successor] = depths[current] + 1
            queue.append(successor)

    rng = random.Random(seed)
    buckets: dict[int, list[str]] = {}
    for value in sorted(depths):
        if depths[value] >= 3 and value != "MUI":
            buckets.setdefault(depths[value], []).append(value)
    for bucket in buckets.values():
        rng.shuffle(bucket)
    selected = ["MUI"] if "MUI" in parents else []
    levels = sorted(buckets)
    # Include deeper targets before adding more depth-three examples.
    levels = [depth for depth in levels if depth > 3] + [depth for depth in levels if depth == 3]
    while len(selected) < count:
        before = len(selected)
        for depth in levels:
            if buckets[depth] and len(selected) < count:
                selected.append(buckets[depth].pop())
        if len(selected) == before:
            raise ValueError("BFS bounds produced too few targets; increase depth or state budget")

    cases = []
    for goal in selected[:count]:
        witness = []
        cursor = goal
        while parents[cursor] is not None:
            parent, move = parents[cursor]
            witness.append({"current": parent, "move": move})
            cursor = parent
        cases.append({
            "goal": goal, "kind": "reachable", "reference_steps": depths[goal],
            "witness": list(reversed(witness)),
        })
    cases.append({
        "goal": "MU", "kind": "impossible", "reference_steps": None,
        "witness": None, "proof": "The I count cannot become 0 modulo 3 from MI.",
    })
    return cases, {
        "max_length": max_length, "max_depth": max_depth, "max_states": max_states,
        "states_discovered": len(parents), "truncated": truncated,
        "scope": "Shortest paths within the stated length bound, not unbounded distances.",
    }


def generate_lambda_cases(
    seed: int, count: int, novel: int = 0, tournament: int = 0,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rng = random.Random(seed)
    pool = lambda_terms()
    reachable = [term for term, kind in pool if kind == "reachable"]
    traps = [term for term, kind in pool if kind == "trap"]
    growth = [term for term, kind in pool if kind == "growth"]
    tournaments = [term for term, kind in pool if kind == "tournament"]
    for group in (reachable, traps, growth, tournaments):
        rng.shuffle(group)
    if tournament > len(tournaments):
        raise ValueError(
            f"Lambda pool has {len(tournaments)} tournament terms; "
            "lower --tournament-terms or extend tournament_terms()"
        )
    if novel > count - 2:
        raise ValueError(
            "More novel terms requested than reachable slots; "
            "raise --targets or lower --novel-terms"
        )
    if count - 2 - novel > len(reachable):
        raise ValueError(
            f"Lambda pool has {len(reachable)} reachable terms; lower --targets or extend lambda_terms()"
        )
    novel_pairs = novel_lambda_terms(seed, novel) if novel else []
    selected = novel_pairs + list(zip(
        reachable[:count - 2 - novel], ["reachable"] * (count - 2 - novel),
    ))
    selected.append((traps[0], "trap"))
    selected.append((growth[0], "growth"))
    selected.extend(zip(tournaments[:tournament], ["tournament"] * tournament))
    rng.shuffle(selected)

    cases = []
    for term, kind in selected:
        path, normal_form = lambda_calc.normal_order_witness(term, max_steps=100)
        if normal_form is None:
            raise ValueError(f"Curated lambda term never normalizes: {term}")
        cases.append({
            "goal": normal_form, "term": term, "kind": kind,
            "reference_steps": len(path),
            "witness": [{"current": step["current"], "move": step["move"]} for step in path],
        })
    cases.append({
        "goal": None, "term": OMEGA, "kind": "impossible",
        "reference_steps": None, "witness": None,
        "proof": "Omega reduces to itself; it has no normal form.",
    })
    return cases, {
        "pool_reachable": len(reachable), "pool_trap": len(traps), "pool_growth": len(growth),
        "pool_novel": len(novel_pairs),
        "pool_tournament": len(tournaments),
        "scope": "Normal-order reference paths, which reach a normal form whenever one exists.",
    }


def present_menu(
    moves: list[dict[str, Any]], menu_order: str, seed: int, current: str,
) -> list[dict[str, Any]]:
    """Order the provider-facing menu: the fixed server order, its reverse, or
    a per-state seeded shuffle. Move ids stay server-owned, so evidence stays
    auditable while menu position becomes a controlled variable."""
    if menu_order == "fixed":
        return moves
    presented = list(moves)
    if menu_order == "reversed":
        presented.reverse()
        return presented
    if menu_order == "shuffled":
        random.Random(f"menu:{seed}:{current}").shuffle(presented)
        return presented
    raise ValueError("Unknown menu order")


def run_trial(
    case: dict[str, Any], strategy: str, seed: int, max_steps: int,
    max_length: int, stagnation_limit: int,
    provider: str | None = None, model: str | None = None,
    system: str = "miu", hints: bool = True, menu_order: str = "fixed",
    wrong_hint: bool = False,
) -> dict[str, Any]:
    if strategy not in ("random", "heuristic", "model", "guided"):
        raise ValueError("Unknown strategy")
    if menu_order not in ("fixed", "reversed", "shuffled"):
        raise ValueError("Unknown menu order")
    if strategy in ("model", "guided") and (provider not in DEFAULT_MODELS or not model):
        raise ValueError("Model strategies require an explicit provider and model")
    rng = random.Random(seed)
    goal = case["goal"] if system == "miu" else lambda_calc.GOAL
    start = lambda_calc.describe(case["term"])["current"] if system == "lambda" else "MI"
    history = [start]
    if system == "lambda":
        best_distance = lambda_calc.describe(start)["progress"]
    else:
        best_distance = target_distance("MI", case["goal"])
    stagnant_steps = 0
    calls = overrides = evaluated_groups = 0
    evidence: list[dict[str, Any]] = []
    started = time.perf_counter()
    outcome = "step_budget"
    for _ in range(max_steps):
        current = history[-1]
        if system == "lambda":
            state = lambda_calc.describe(current)
            moves, solved = state["moves"], state["solved"]
        else:
            moves, solved = legal_moves(current), current == case["goal"]
        if solved:
            outcome = "found"
            break
        if not moves:
            outcome = "no_moves"
            break
        entry: dict[str, Any] = {"current": current, "applied": False}
        evidence.append(entry)
        if strategy in ("model", "guided"):
            presented = present_menu(moves, menu_order, seed, current)
            if wrong_hint:
                recommended = []
                for move in presented:
                    if move["result"] == current:
                        recommended.append(move["id"])
                        move["label"] = f"{move['label']} · recommended"
                        move["detail"] = WRONG_HINT_RECOMMENDATION
                if recommended:
                    entry["wrong_hint"] = recommended
            entry["presented"] = [move["id"] for move in presented]
            try:
                decision = choose_move(
                    provider, model, strategy, current, goal, history, presented,
                    max_length, system=system, hints=hints,
                )
            except DecisionError as error:
                entry["decision"] = error.decision
                entry["reason"] = "provider_error"
                entry["error"] = str(error)
                calls += error.decision["provider_calls"]
                overrides += error.decision["override_count"]
                evaluated_groups += sum(
                    group["raw_choice"] is not None
                    for round_ in error.decision["rounds"] for group in round_["groups"]
                )
                outcome = "provider_error"
                break
            entry["decision"] = decision
            calls += decision["provider_calls"]
            overrides += decision["override_count"]
            evaluated_groups += sum(
                group["raw_choice"] is not None
                for round_ in decision["rounds"] for group in round_["groups"]
            )
            move = decision["move"]
        elif strategy == "random":
            move = rng.choice(moves)
            entry["selection"] = {"reason": "Seeded uniform choice over all legal moves."}
        else:
            explanation: dict[str, Any] = {}
            if system == "lambda":
                move = lambda_calc.select_move(
                    "guided", current, goal, history, moves, moves[0], {}, max_length, explanation,
                )
            else:
                move = select_move(
                    "guided", current, goal, history, moves, moves[0], {}, max_length, explanation,
                )
            entry["selection"] = explanation
        if move not in moves:
            raise RuntimeError("Strategy returned a move outside the legal menu")
        entry["move"] = move
        successor = move["result"]
        if len(successor) > max_length:
            outcome = entry["reason"] = "length_budget"
            break
        if successor in history:
            outcome = entry["reason"] = "cycle"
            break
        entry["applied"] = True
        history.append(successor)
        if successor == goal or (system == "lambda" and lambda_calc.describe(successor)["solved"]):
            outcome = "found"
            break
        if system == "lambda":
            distance = lambda_calc.describe(successor)["progress"]
        else:
            distance = target_distance(successor, case["goal"])
        if distance < best_distance:
            best_distance = distance
            stagnant_steps = 0
        else:
            stagnant_steps += 1
        if stagnant_steps >= stagnation_limit:
            outcome = "stagnation"
            break
    return {
        "goal": case["goal"], "kind": case["kind"], "strategy": strategy,
        "provider": provider, "model": model, "seed": seed,
        "system": system, "hints": hints, "menu_order": menu_order,
        "wrong_hint": wrong_hint,
        "outcome": outcome, "success": outcome == "found",
        "steps": len(history) - 1, "history": history,
        "reference_steps": case["reference_steps"],
        "provider_calls": calls, "override_count": overrides,
        "evaluated_groups": evaluated_groups,
        "elapsed_ms": (time.perf_counter() - started) * 1000,
        "evidence": evidence,
    }


def summarize(trials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str | None, str | None, str], list[dict[str, Any]]] = {}
    for trial in trials:
        key = (
            trial["kind"], trial["strategy"], trial["provider"], trial["model"],
            trial.get("menu_order", "fixed"),
        )
        groups.setdefault(key, []).append(trial)
    summaries = []
    for (kind, strategy, provider, model, menu_order), rows in groups.items():
        successes = [row for row in rows if row["success"]]
        evaluated = sum(row["evaluated_groups"] for row in rows)
        overrides = sum(row["override_count"] for row in rows)
        summaries.append({
            "kind": kind, "strategy": strategy, "provider": provider, "model": model,
            "menu_order": menu_order,
            "trials": len(rows), "successes": len(successes),
            "success_rate": len(successes) / len(rows) if kind != "impossible" else None,
            "mean_steps": statistics.mean(row["steps"] for row in rows),
            "mean_success_steps": (
                statistics.mean(row["steps"] for row in successes) if successes else None
            ),
            "mean_excess_steps_over_bounded_bfs": (
                statistics.mean(row["steps"] - row["reference_steps"] for row in successes)
                if successes and kind != "impossible" else None
            ),
            "mean_elapsed_ms": statistics.mean(row["elapsed_ms"] for row in rows),
            "provider_calls": sum(row["provider_calls"] for row in rows),
            "evaluated_groups": evaluated, "override_count": overrides,
            "override_rate": overrides / evaluated if evaluated else None,
            "outcomes": {name: sum(row["outcome"] == name for row in rows)
                         for name in sorted({row["outcome"] for row in rows})},
        })
    return summaries


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system", choices=("miu", "lambda"), default="miu")
    parser.add_argument("--providers", nargs="+", choices=tuple(DEFAULT_MODELS), default=[])
    parser.add_argument("--ollama-model", default=DEFAULT_MODELS["ollama"])
    parser.add_argument("--typesafe-model", default=DEFAULT_MODELS["typesafe"])
    parser.add_argument("--seed", type=int, default=20261002)
    parser.add_argument("--targets", type=int, default=6)
    parser.add_argument(
        "--novel-terms", type=int, default=0,
        help="lambda only: seeded compositions no textbook contains, "
             "replacing up to targets - 2 reachable slots",
    )
    parser.add_argument(
        "--tournament-terms", type=int, default=0,
        help="lambda only: adds majority-losing cases whose menus exceed the "
             "26-choice tournament path",
    )
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--max-steps", type=int, default=20)
    parser.add_argument("--max-length", type=int, default=None)
    parser.add_argument("--stagnation-limit", type=int, default=10)
    parser.add_argument("--bfs-depth", type=int, default=7)
    parser.add_argument("--bfs-states", type=int, default=10000)
    parser.add_argument("--hint-ablation", action="store_true")
    parser.add_argument(
        "--wrong-hint", action="store_true",
        help="lambda only: adds provider arms whose hint-on menus annotate "
             "diverging self-loop contractions as recommended, measuring "
             "deference to guidance versus judgment",
    )
    parser.add_argument(
        "--menu-order", choices=("fixed", "reversed", "shuffled"), default="fixed",
        help="permute provider-facing menus to control position bias; "
             "baselines always use the fixed server order",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.max_length is None:
        args.max_length = 32 if args.system == "miu" else lambda_calc.MAX_CHARS
    absolute_limit = MAX_MIU_LENGTH if args.system == "miu" else lambda_calc.MAX_CHARS
    if (
        not 8 <= args.max_length <= absolute_limit
        or min(args.targets, args.repeats, args.max_steps, args.stagnation_limit, args.bfs_states) < 1
        or args.bfs_depth < 3
    ):
        parser.error(
            "Use positive budgets, BFS depth >= 3, and max length from 8 "
            f"to {absolute_limit} for the {args.system} system"
        )
    if (
        args.novel_terms < 0
        or (args.novel_terms and args.system != "lambda")
        or (args.system == "lambda" and args.novel_terms > args.targets - 2)
    ):
        parser.error(
            "--novel-terms requires --system lambda, a non-negative count, "
            "and at most targets - 2 terms"
        )
    if (
        args.tournament_terms < 0
        or (args.tournament_terms and args.system != "lambda")
        or (args.system == "lambda" and args.tournament_terms > len(tournament_terms()))
    ):
        parser.error(
            "--tournament-terms requires --system lambda, a non-negative count, "
            "and at most the size of the tournament pool"
        )
    if args.wrong_hint and args.system != "lambda":
        parser.error("--wrong-hint requires --system lambda")
    for provider in args.providers:
        if provider == "ollama":
            require_compatible_ollama()
        elif not os.environ.get("TYPESAFE_API_KEY", "").strip():
            parser.error("TypeSafe requires TYPESAFE_API_KEY; no fallback is used")
    if args.system == "miu":
        cases, reference = generate_cases(
            args.seed, args.targets, args.max_length, args.bfs_depth, args.bfs_states,
        )
    else:
        cases, reference = generate_lambda_cases(
            args.seed, args.targets, novel=args.novel_terms,
            tournament=args.tournament_terms,
        )

    strategies: list[tuple[str, str, str | None, str | None, bool, bool]] = [
        ("random", "random", None, None, True, False),
        ("heuristic", "heuristic", None, None, True, False),
    ]
    for provider in dict.fromkeys(args.providers):
        for policy in ("model", "guided"):
            model = getattr(args, f"{provider}_model")
            strategies.append((policy, policy, provider, model, True, False))
            if args.hint_ablation:
                strategies.append((f"{policy}-nohints", policy, provider, model, False, False))
            if args.wrong_hint:
                strategies.append((f"{policy}-wronghint", policy, provider, model, True, True))

    schedule = [
        (case, repeat, label, policy, provider, model, hints, wrong_hint)
        for case in cases for repeat in range(args.repeats)
        for label, policy, provider, model, hints, wrong_hint in strategies
    ]
    random.Random(args.seed).shuffle(schedule)
    root = Path(__file__).resolve().parent
    source_files = ["app.py", "benchmark.py"] + (
        ["lambda_calc.py"] if args.system == "lambda" else []
    )
    report: dict[str, Any] = {
        "schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(), "system": args.system,
        "source_sha256": {
            name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in source_files
        },
        "configuration": {
            **{key: value for key, value in vars(args).items() if key != "output"},
            "note": "Seeds control targets, scheduling and random baseline, not provider sampling. "
                    "Omega or MU exploration is excluded from reachable success rates. "
                    "Reference steps are bounded-BFS paths for MIU and normal-order paths for lambda. "
                    "Hint-off strategies remove precomputed annotations from provider menus, "
                    "not from the deterministic guided policy. "
                    "The menu-order arm permutes provider-facing menus "
                    "(reversed, or a per-state seeded shuffle); "
                    "baselines always use the fixed server order. "
                    "Wrong-hint arms annotate diverging self-loop contractions "
                    "as recommended in hint-on menus; the annotation changes "
                    "descriptive text only, never legality. "
                    "Latency excludes UI delays and includes provider/version-check overhead.",
        },
        "reference": reference, "cases": cases, "trials": [], "summary": [],
        "completed": False,
    }
    for index, (case, repeat, label, policy, provider, model, hints, wrong_hint) in enumerate(schedule, 1):
        trial = run_trial(
            case, policy, args.seed + repeat, args.max_steps,
            args.max_length, args.stagnation_limit, provider, model,
            args.system, hints,
            args.menu_order if policy in ("model", "guided") else "fixed",
            wrong_hint if policy in ("model", "guided") else False,
        )
        trial["strategy"] = label
        trial["repeat"] = repeat + 1
        report["trials"].append(trial)
        report["summary"] = summarize(report["trials"])
        report["completed"] = index == len(schedule)
        args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        label_text = case["goal"] if args.system == "miu" else case["term"][:24]
        print(f"{index}/{len(schedule)} {label_text} {provider or 'baseline'}/{label}: "
              f"{trial['outcome']} ({trial['steps']} steps)", flush=True)
    print(f"Results saved to {args.output}")


if __name__ == "__main__":
    main()
