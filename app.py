from __future__ import annotations

import argparse
import json
import math
import mimetypes
import os
import re
import string
import time
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import algebra
import lambda_calc


ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "web"
OLLAMA_URL = "http://127.0.0.1:11434/v1/systemone"
OLLAMA_VERSION_URL = "http://127.0.0.1:11434/api/version"
TYPESAFE_URL = "https://api.typesafe.ai/v1/systemone"
MIN_OLLAMA_VERSION = (0, 35, 0)
MIN_OLLAMA_VERSION_TEXT = "0.35.0"
DEFAULT_PROVIDER = "ollama"
DEFAULT_MODELS = {"ollama": "nimble:latest", "typesafe": "jev-latest"}
MAX_BODY_BYTES = 1_000_000
MAX_MIU_LENGTH = 8_192
MAX_HISTORY_ENTRIES = 1_024
CHOICE_KEYS = string.ascii_uppercase
PROVIDER_CHOICE_LIMITS = {"ollama": len(CHOICE_KEYS), "typesafe": 255}
SYSTEMS = ("miu", "algebra", "lambda")


def validate_system(value: Any) -> str:
    if not isinstance(value, str) or value not in SYSTEMS:
        raise ValueError("system must be miu, algebra, or lambda")
    return value


def load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        name = name.strip()
        if name and name not in os.environ:
            os.environ[name] = value.strip().strip("\"'")


load_env_file(ROOT / ".env")
load_env_file(Path.home() / ".copilot" / ".env")


def parse_version(value: str) -> tuple[int, int, int] | None:
    match = re.match(r"^\s*(\d+)\.(\d+)\.(\d+)", value)
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def ollama_status() -> dict[str, Any]:
    try:
        with urllib.request.urlopen(OLLAMA_VERSION_URL, timeout=2) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        return {
            "available": False,
            "compatible": False,
            "version": None,
            "error": f"Could not reach Ollama: {error}",
        }

    version = payload.get("version")
    parsed = parse_version(version) if isinstance(version, str) else None
    compatible = parsed is not None and parsed >= MIN_OLLAMA_VERSION
    return {
        "available": True,
        "compatible": compatible,
        "version": version,
        "error": (
            None
            if compatible
            else f"Ollama {MIN_OLLAMA_VERSION_TEXT} or later is required"
        ),
    }


def require_compatible_ollama() -> None:
    status = ollama_status()
    if not status["available"]:
        raise RuntimeError(status["error"])
    if not status["compatible"]:
        installed = status["version"] or "unknown"
        raise RuntimeError(
            f"Ollama {MIN_OLLAMA_VERSION_TEXT} or later is required; "
            f"found {installed}"
        )


def legal_moves(value: str) -> list[dict[str, Any]]:
    moves: list[dict[str, Any]] = []

    if value.endswith("I"):
        moves.append(
            {
                "rule": 1,
                "position": len(value),
                "result": value + "U",
                "label": "Rule 1 · append U",
                "detail": "The string ends in I, so append U.",
            }
        )

    if value.startswith("M"):
        tail = value[1:]
        moves.append(
            {
                "rule": 2,
                "position": 1,
                "result": "M" + tail + tail,
                "label": "Rule 2 · duplicate tail",
                "detail": f"Duplicate the part after M ({tail or 'empty'}).",
            }
        )

    start = 0
    while True:
        position = value.find("III", start)
        if position < 0:
            break
        moves.append(
            {
                "rule": 3,
                "position": position,
                "result": value[:position] + "U" + value[position + 3 :],
                "label": f"Rule 3 · III → U at {position + 1}",
                "detail": f"Replace characters {position + 1}–{position + 3} with U.",
            }
        )
        start = position + 1

    start = 0
    while True:
        position = value.find("UU", start)
        if position < 0:
            break
        moves.append(
            {
                "rule": 4,
                "position": position,
                "result": value[:position] + value[position + 2 :],
                "label": f"Rule 4 · delete UU at {position + 1}",
                "detail": f"Delete characters {position + 1}–{position + 2}.",
            }
        )
        start = position + 1

    for index, move in enumerate(moves):
        move["id"] = f"move-{index}"
    return moves


def validate_miu(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or any(char not in "MIU" for char in value):
        raise ValueError(f"{field} must be a non-empty string containing only M, I, and U")
    if len(value) > MAX_MIU_LENGTH:
        raise ValueError(f"{field} must not exceed {MAX_MIU_LENGTH} characters")
    return value


def validate_history(history: list[str], system: str) -> None:
    if len(history) > MAX_HISTORY_ENTRIES:
        raise ValueError(f"history must not exceed {MAX_HISTORY_ENTRIES} entries")
    if system == "algebra":
        for item in history:
            algebra.parse_equation(item)
    elif system == "lambda":
        for item in history:
            lambda_calc.parse_term(item)
    else:
        for item in history:
            validate_miu(item, "history")


def rewrite_opportunities(value: str) -> int:
    return (
        int(value.endswith("I"))
        + sum(value[index : index + 3] == "III" for index in range(len(value) - 2))
        + sum(value[index : index + 2] == "UU" for index in range(len(value) - 1))
    )


def contraction_opportunities(value: str) -> int:
    return (
        sum(value[index : index + 3] == "III" for index in range(len(value) - 2))
        + sum(value[index : index + 2] == "UU" for index in range(len(value) - 1))
    )


def is_growth_only_trap(value: str) -> bool:
    moves = legal_moves(value)
    if len(moves) != 1 or moves[0]["rule"] != 2:
        return False
    doubled = moves[0]["result"]
    return (
        contraction_opportunities(doubled) == 0
        and not doubled.endswith("I")
    )


def heuristic_score(
    move: dict[str, Any],
    current: str,
    goal: str,
    history: list[str],
) -> float:
    result = move["result"]
    if result == goal:
        return 1_000_000.0

    length_delta = len(result) - len(current)
    contractions = contraction_opportunities(result)
    score = -2.0 * length_delta
    score += 5.0 if result not in history else -20.0
    score += 6.0 * contractions
    score += 1.5 * rewrite_opportunities(result)
    score += 0.25 * (abs(len(current) - len(goal)) - abs(len(result) - len(goal)))
    if length_delta < 0:
        score += 20.0
    if move["rule"] == 2 and contractions == 0:
        score -= 10.0
    if is_growth_only_trap(result):
        score -= 100.0
    return score


def select_move(
    policy: str,
    current: str,
    goal: str,
    history: list[str],
    candidates: list[dict[str, Any]],
    model_choice: dict[str, Any],
    probabilities: dict[str, float],
    max_length: int,
    explanation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    evidence: dict[str, Any] = {"filters": [], "scores": {}}
    if explanation is not None:
        explanation.update(evidence)

    def record_filter(reason: str, pool: list[dict[str, Any]]) -> None:
        evidence["filters"].append(
            {"reason": reason, "eligible": [move["id"] for move in pool]}
        )

    def finish(move: dict[str, Any], reason: str) -> dict[str, Any]:
        if explanation is not None:
            explanation["reason"] = reason
        return move

    if policy == "model":
        return finish(model_choice, "Provider choice preserved; execution limits still apply.")
    if policy != "guided":
        raise ValueError("policy must be guided or model")

    bounded = [
        move for move in candidates if len(move["result"]) <= max_length
    ]
    if bounded:
        candidates = bounded
        record_filter("Prefer moves within the length budget.", candidates)

    targets = [move for move in candidates if move["result"] == goal]
    if targets:
        record_filter("Prefer an immediate target.", targets)
        return finish(targets[0], "Selected an immediate target.")

    reductions = [
        move for move in candidates if len(move["result"]) < len(current)
    ]
    pool = reductions or candidates
    if reductions:
        record_filter("Prefer shortening moves.", pool)
    novel = [move for move in pool if move["result"] not in history]
    if novel:
        pool = novel
        record_filter("Prefer unvisited results.", pool)
    productive = [
        move for move in pool if not is_growth_only_trap(move["result"])
    ]
    if productive:
        pool = productive
        record_filter("Avoid growth-only traps when an alternative exists.", pool)

    for move in pool:
        score = heuristic_score(move, current, goal, history)
        adjustment = 5.0 * probabilities.get(move["id"], 0.0)
        evidence["scores"][move["id"]] = {
            "heuristic": score,
            "probability_adjustment": adjustment,
            "total": score + adjustment,
        }
    selected = max(
        pool,
        key=lambda move: (
            evidence["scores"][move["id"]]["total"],
            probabilities.get(move["id"], 0.0),
        ),
    )
    return finish(
        selected,
        "Highest heuristic plus group-local probability score among retained moves; "
        "ties use probability, then menu order.",
    )


def decision_request(
    provider: str,
    model: str,
    policy: str,
    current: str,
    goal: str,
    history: list[str],
    candidates: list[dict[str, Any]],
    max_length: int,
    trace: dict[str, Any] | None = None,
    system: str = "miu",
) -> tuple[dict[str, Any], dict[str, float]]:
    validate_system(system)
    criteria: dict[str, str] = {}
    by_key: dict[str, dict[str, Any]] = {}
    keys = (
        list(CHOICE_KEYS)
        if provider == "ollama"
        else [f"move_{index}" for index in range(len(candidates))]
    )
    for key, move in zip(keys, candidates):
        by_key[key] = move
        domain_detail = (
            f"immediate non-duplication rewrites: {rewrite_opportunities(move['result'])}; "
            f"growth-only trap: {'yes' if is_growth_only_trap(move['result']) else 'no'}; "
        ) if system == "miu" else (
            f"position: {move['position']}; justification: {move['detail']}; "
            f"solved: {move['solved']}; structural progress cost: {move['progress']}; "
            + (f"duplication cost: {move['duplication']}; redexes after: {move['redexes']}; "
               if system == "lambda" else "")
        )
        criteria[key] = (
            f"{move['label']}; result: {move['result']}; "
            f"length: {len(move['result'])}; "
            f"length change: {len(move['result']) - len(current):+d}; "
            f"{domain_detail}"
            f"already visited: {'yes' if move['result'] in history else 'no'}"
        )

    state = {
        "formal_system": "MIU",
        "current_string": current,
        "target_string": goal,
        "recent_derivation": history[-12:],
        "candidate_moves": criteria,
        "invariant": (
            "The number of I symbols modulo 3 cannot become 0 when starting from MI. "
            "Use this fact when relevant, but still choose one of the supplied legal moves."
        ),
        "search_guidance": (
            "String growth is not progress by itself. Repeated Rule 2 doubling can grow "
            "exponentially forever, especially when the target is impossible. Prefer "
            "contractions, novel states, and moves that create immediate III or UU "
            "rewrites. Choose doubling only when it creates a concrete rewrite opportunity."
            " Avoid a growth-only trap where Rule 2 remains the sole move and repeated "
            "doubling can never create III or UU."
        ),
    }
    instructions = (
        "Select the legal move most promising for reaching the target. Prefer the "
        "target immediately, then novel states that appear to make structural "
        "progress. Strongly avoid revisiting states or increasing length without "
        "creating an immediate III or UU rewrite opportunity."
    )
    if system == "algebra":
        state = {
            "formal_system": "Single-variable linear equations over the rational numbers",
            "current_equation": current, "goal": goal,
            "recent_derivation": history[-12:], "candidate_moves": criteria,
            "invariant": "Every supplied rewrite preserves exactly the solution set. "
                         "Division is permitted only by known nonzero numeric constants.",
            "search_guidance": "Isolate x on the left with a rational number on the right, "
                               "or reduce an identity/contradiction to a numeric equality. "
                               "Consider dividing before distributing. Avoid needless expansion "
                               "and revisiting equations. The finite menu is a declared algebra "
                               "vocabulary, not every possible algebraic transformation.",
        }
        instructions = (
            "Choose one supplied equivalent rewrite that makes a short, clear derivation "
            "toward an isolated x or a numeric identity/contradiction. "
            "Do not invent an equation or a transformation."
        )
    elif system == "lambda":
        state = {
            "formal_system": "Untyped lambda calculus under beta reduction",
            "current_term": current, "goal": goal,
            "recent_derivation": history[-12:], "candidate_moves": criteria,
            "invariant": (
                "Every candidate is a single capture-avoiding beta contraction at a "
                "marked position. The server performs the substitution, so each step "
                "preserves the term's equivalence class by construction."
            ),
            "search_guidance": (
                "Leftmost-outermost (normal-order) reduction reaches a normal form "
                "whenever one exists; reducing inner redexes first can diverge where "
                "outer order terminates. Prefer outer redexes and results that are "
                "normal forms. Be cautious contracting a redex whose bound variable "
                "occurs more than once while the argument is large, because the "
                "substitution duplicates that work. Normalization is undecidable in "
                "general, so budget stops are inconclusive rather than proofs. The "
                "menu lists every redex; do not invent a term or transformation."
            ),
        }
        instructions = (
            "Choose the supplied beta contraction that most directly progresses "
            "toward the normal-form goal. Do not invent a term or a transformation."
        )
    request_body: dict[str, Any] = {
        "model": model,
        "state": state,
        "questions": {
            "next_move": {
                "type": "choice",
                "instructions": instructions,
                "criteria": criteria,
            }
        },
    }
    headers = {"Content-Type": "application/json"}
    url = OLLAMA_URL
    provider_name = "Ollama"
    if provider == "ollama":
        require_compatible_ollama()
        request_body["keep_alive"] = "10m"
    elif provider == "typesafe":
        api_key = os.environ.get("TYPESAFE_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "TypeSafe is not configured. Set TYPESAFE_API_KEY before starting the server."
            )
        url = TYPESAFE_URL
        headers["Authorization"] = f"Bearer {api_key}"
        provider_name = "TypeSafe"
    else:
        raise ValueError(f"Unsupported decision provider: {provider}")

    encoded = json.dumps(request_body).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=encoded,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        error.close()
        raise RuntimeError(
            f"{provider_name} returned HTTP {error.code}"
        ) from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Could not reach {provider_name}: {error.reason}") from error
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise RuntimeError(f"{provider_name} returned invalid JSON") from error
    except TimeoutError as error:
        raise RuntimeError(f"{provider_name} request timed out") from error

    answers = payload.get("answers") if isinstance(payload, dict) else None
    answer = answers.get("next_move") if isinstance(answers, dict) else None
    if not isinstance(answer, dict):
        raise RuntimeError(f"{provider_name} returned an invalid decision response")
    selected_key = answer.get("choice")
    if not isinstance(selected_key, str) or selected_key not in by_key:
        raise RuntimeError(f"{provider_name} returned an invalid move choice")
    raw_probabilities = answer.get("probabilities", {})
    if not isinstance(raw_probabilities, dict):
        raise RuntimeError(f"{provider_name} returned invalid probabilities")
    probabilities: dict[str, float] = {}
    for key, value in raw_probabilities.items():
        if key not in by_key:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise RuntimeError(f"{provider_name} returned an invalid probability")
        try:
            probability = float(value)
        except (ValueError, OverflowError) as error:
            raise RuntimeError(
                f"{provider_name} returned an invalid probability"
            ) from error
        if not math.isfinite(probability) or not 0 <= probability <= 1:
            raise RuntimeError(f"{provider_name} returned an invalid probability")
        probabilities[by_key[key]["id"]] = probability
    selection: dict[str, Any] = {}
    selector = (
        select_move if system == "miu"
        else algebra.select_move if system == "algebra"
        else lambda_calc.select_move
    )
    selected = selector(
        policy,
        current,
        goal,
        history,
        candidates,
        by_key[selected_key],
        probabilities,
        max_length,
        selection,
    )
    if trace is not None:
        trace.update({
            "raw_choice": by_key[selected_key]["id"],
            "overridden": selected["id"] != by_key[selected_key]["id"],
            "selection": selection,
        })
    return selected, probabilities


class DecisionError(RuntimeError):
    def __init__(self, message: str, decision: dict[str, Any]) -> None:
        super().__init__(message)
        self.decision = decision


def choose_move(
    provider: str,
    model: str,
    policy: str,
    current: str,
    goal: str,
    history: list[str],
    moves: list[dict[str, Any]],
    max_length: int = 64,
    system: str = "miu",
) -> dict[str, Any]:
    validate_system(system)
    if not moves:
        raise ValueError("There are no legal moves from the current string")

    started = time.perf_counter()
    rounds: list[dict[str, Any]] = []
    result: dict[str, Any] = {
        "schema_version": 1, "system": system, "current": current, "goal": goal,
        "provider": provider, "model": model, "policy": policy,
        "history": list(history), "max_length": max_length, "moves": moves,
        "rounds": rounds, "provider_calls": 0, "override_count": 0,
    }
    contenders = moves
    round_number = 1
    while True:
        winners: list[dict[str, Any]] = []
        groups: list[dict[str, Any]] = []
        round_trace = {
            "round": round_number, "contenders": len(contenders),
            "winners": 0, "groups": groups,
        }
        rounds.append(round_trace)
        choice_limit = PROVIDER_CHOICE_LIMITS[provider]
        for offset in range(0, len(contenders), choice_limit):
            group = contenders[offset : offset + choice_limit]
            group_trace: dict[str, Any] = {
                "group": len(groups) + 1,
                "candidates": [move["id"] for move in group],
                "requested": len(group) > 1,
                "raw_choice": None, "winner": None, "overridden": False,
                "probabilities": {},
                "probability_scope": "within this group only",
            }
            groups.append(group_trace)
            group_started = time.perf_counter()
            if len(group) == 1:
                winner = group[0]
                probabilities = {}
                group_trace["selection"] = {
                    "reason": "Only candidate; advanced without a provider request.",
                    "filters": [], "scores": {},
                }
            else:
                result["provider_calls"] += 1
                try:
                    winner, probabilities = decision_request(
                        provider, model, policy, current, goal, history,
                        group, max_length, trace=group_trace, system=system,
                    )
                except RuntimeError as error:
                    group_trace["error"] = str(error)
                    group_trace["elapsed_ms"] = (time.perf_counter() - group_started) * 1000
                    result["elapsed_ms"] = (time.perf_counter() - started) * 1000
                    raise DecisionError(str(error), result) from error
            winners.append(winner)
            round_trace["winners"] = len(winners)
            group_trace["winner"] = winner["id"]
            group_trace["probabilities"] = probabilities
            group_trace["elapsed_ms"] = (time.perf_counter() - group_started) * 1000
            result["override_count"] += int(group_trace["overridden"])
        if len(winners) == 1:
            result["move"] = winners[0]
            result["elapsed_ms"] = (time.perf_counter() - started) * 1000
            return result
        contenders = winners
        round_number += 1


class RequestHandler(BaseHTTPRequestHandler):
    server_version = "MIU/Jev MVP"

    def do_GET(self) -> None:
        if self.path == "/api/health":
            ollama = ollama_status()
            typesafe_available = bool(
                os.environ.get("TYPESAFE_API_KEY", "").strip()
            )
            self.send_json(
                {
                    "ok": True,
                    "default_provider": DEFAULT_PROVIDER,
                    "providers": {
                        "ollama": {
                            "available": ollama["compatible"],
                            "default_model": DEFAULT_MODELS["ollama"],
                            "label": "Local Ollama 0.35.0+ / Nimble",
                            "version": ollama["version"],
                            "minimum_version": MIN_OLLAMA_VERSION_TEXT,
                            "error": ollama["error"],
                        },
                        "typesafe": {
                            "available": typesafe_available,
                            "default_model": DEFAULT_MODELS["typesafe"],
                            "label": "TypeSafe API / Jev",
                        },
                    },
                }
            )
            return

        path_only = urlsplit(self.path).path
        requested = "index.html" if path_only in ("/", "") else path_only.lstrip("/")
        path = (WEB_ROOT / requested).resolve()
        if WEB_ROOT.resolve() not in path.parents or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        content = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self) -> None:
        try:
            payload = self.read_json()
            system = validate_system(payload.get("system", "miu"))
            if self.path == "/api/moves":
                if system == "algebra":
                    self.send_json(algebra.describe(payload.get("current")))
                    return
                if system == "lambda":
                    self.send_json(lambda_calc.describe(payload.get("current")))
                    return
                current = validate_miu(payload.get("current"), "current")
                self.send_json({"system": system, "current": current, "moves": legal_moves(current)})
                return
            if self.path == "/api/choose":
                if system == "algebra":
                    analysis = algebra.describe(payload.get("current"))
                    current = analysis["current"]
                    goal = payload.get("goal", algebra.GOAL)
                    if goal != algebra.GOAL:
                        raise ValueError(f"Algebra goal must be {algebra.GOAL}")
                    moves = analysis["moves"]
                elif system == "lambda":
                    analysis = lambda_calc.describe(payload.get("current"))
                    current = analysis["current"]
                    goal = payload.get("goal", lambda_calc.GOAL)
                    if goal != lambda_calc.GOAL:
                        raise ValueError(f"Lambda goal must be {lambda_calc.GOAL}")
                    moves = analysis["moves"]
                else:
                    current = validate_miu(payload.get("current"), "current")
                    goal = validate_miu(payload.get("goal", "MU"), "goal")
                    analysis = None
                    moves = legal_moves(current)
                provider = payload.get("provider", DEFAULT_PROVIDER)
                if not isinstance(provider, str) or provider not in DEFAULT_MODELS:
                    raise ValueError("provider must be ollama or typesafe")
                model = payload.get("model", DEFAULT_MODELS[provider])
                policy = payload.get("policy", "guided")
                if policy not in ("guided", "model"):
                    raise ValueError("policy must be guided or model")
                history = payload.get("history", [])
                max_length = payload.get("max_length", 64)
                absolute_limit = {
                    "miu": MAX_MIU_LENGTH,
                    "algebra": algebra.MAX_LENGTH,
                    "lambda": lambda_calc.MAX_CHARS,
                }[system]
                if not isinstance(model, str) or not model.strip():
                    raise ValueError("model must be a non-empty string")
                if not isinstance(history, list) or not all(
                    isinstance(item, str) for item in history
                ):
                    raise ValueError("history must be a list of strings")
                validate_history(history, system)
                if (
                    not isinstance(max_length, int)
                    or isinstance(max_length, bool)
                    or not 8 <= max_length <= absolute_limit
                ):
                    raise ValueError(
                        f"max_length must be an integer from 8 to {absolute_limit}"
                    )
                result = choose_move(
                    provider,
                    model,
                    policy,
                    current,
                    goal,
                    history,
                    moves,
                    max_length,
                    system,
                )
                if analysis is not None:
                    result["analysis"] = {
                        key: value for key, value in analysis.items() if key != "moves"
                    }
                result["provider"] = provider
                result["policy"] = policy
                result["moves"] = moves
                self.send_json(result)
                return
            self.send_error(HTTPStatus.NOT_FOUND)
        except ValueError as error:
            self.send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
        except DecisionError as error:
            self.send_json(
                {"error": str(error), "decision": error.decision},
                HTTPStatus.BAD_GATEWAY,
            )
        except RuntimeError as error:
            self.send_json({"error": str(error)}, HTTPStatus.BAD_GATEWAY)
        except Exception as error:
            self.send_json(
                {"error": f"Unexpected server error: {error}"},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > MAX_BODY_BYTES:
            raise ValueError("invalid request body size")
        try:
            payload = json.loads(self.rfile.read(length))
        except json.JSONDecodeError as error:
            raise ValueError("request body must be valid JSON") from error
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        return payload

    def send_json(
        self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK
    ) -> None:
        encoded = json.dumps(payload, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[web] {self.address_string()} {format % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the MIU + Jev MVP")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), RequestHandler)
    print(f"MIU + Jev is running at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
