from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import string
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


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
CHOICE_KEYS = string.ascii_uppercase
PROVIDER_CHOICE_LIMITS = {"ollama": len(CHOICE_KEYS), "typesafe": 255}


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
) -> dict[str, Any]:
    if policy == "model":
        return model_choice
    if policy != "guided":
        raise ValueError("policy must be guided or model")

    bounded = [
        move for move in candidates if len(move["result"]) <= max_length
    ]
    if bounded:
        candidates = bounded

    targets = [move for move in candidates if move["result"] == goal]
    if targets:
        return targets[0]

    reductions = [
        move for move in candidates if len(move["result"]) < len(current)
    ]
    pool = reductions or candidates
    novel = [move for move in pool if move["result"] not in history]
    if novel:
        pool = novel
    productive = [
        move for move in pool if not is_growth_only_trap(move["result"])
    ]
    if productive:
        pool = productive

    return max(
        pool,
        key=lambda move: (
            heuristic_score(move, current, goal, history)
            + 5.0 * probabilities.get(move["id"], 0.0),
            probabilities.get(move["id"], 0.0),
        ),
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
) -> tuple[dict[str, Any], dict[str, float]]:
    criteria: dict[str, str] = {}
    by_key: dict[str, dict[str, Any]] = {}
    keys = (
        list(CHOICE_KEYS)
        if provider == "ollama"
        else [f"move_{index}" for index in range(len(candidates))]
    )
    for key, move in zip(keys, candidates):
        by_key[key] = move
        criteria[key] = (
            f"{move['label']}; result: {move['result']}; "
            f"length: {len(move['result'])}; "
            f"length change: {len(move['result']) - len(current):+d}; "
            f"immediate non-duplication rewrites: {rewrite_opportunities(move['result'])}; "
            f"growth-only trap: {'yes' if is_growth_only_trap(move['result']) else 'no'}; "
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
    request_body: dict[str, Any] = {
        "model": model,
        "state": state,
        "questions": {
            "next_move": {
                "type": "choice",
                "instructions": (
                    "Select the legal move most promising for reaching the target. Prefer the "
                    "target immediately, then novel states that appear to make structural "
                    "progress. Strongly avoid revisiting states or increasing length without "
                    "creating an immediate III or UU rewrite opportunity."
                ),
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
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"{provider_name} returned HTTP {error.code}: {detail}"
        ) from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Could not reach {provider_name}: {error.reason}") from error

    answer = payload.get("answers", {}).get("next_move", {})
    selected_key = answer.get("choice")
    if selected_key not in by_key:
        raise RuntimeError(f"{provider_name} returned an invalid move choice")
    probabilities = {
        by_key[key]["id"]: float(probability)
        for key, probability in answer.get("probabilities", {}).items()
        if key in by_key
    }
    selected = select_move(
        policy,
        current,
        goal,
        history,
        candidates,
        by_key[selected_key],
        probabilities,
        max_length,
    )
    return selected, probabilities


def choose_move(
    provider: str,
    model: str,
    policy: str,
    current: str,
    goal: str,
    history: list[str],
    moves: list[dict[str, Any]],
    max_length: int = 64,
) -> dict[str, Any]:
    if not moves:
        raise ValueError("There are no legal moves from the current string")

    rounds: list[dict[str, Any]] = []
    contenders = moves
    round_number = 1
    while len(contenders) > 1:
        winners: list[dict[str, Any]] = []
        round_probabilities: dict[str, float] = {}
        choice_limit = PROVIDER_CHOICE_LIMITS[provider]
        for offset in range(0, len(contenders), choice_limit):
            group = contenders[offset : offset + choice_limit]
            if len(group) == 1:
                winner = group[0]
                probabilities = {winner["id"]: 1.0}
            else:
                winner, probabilities = decision_request(
                    provider,
                    model,
                    policy,
                    current,
                    goal,
                    history,
                    group,
                    max_length,
                )
            winners.append(winner)
            round_probabilities.update(probabilities)
        rounds.append(
            {
                "round": round_number,
                "contenders": len(contenders),
                "winners": len(winners),
                "probabilities": round_probabilities,
            }
        )
        contenders = winners
        round_number += 1

    return {"move": contenders[0], "rounds": rounds}


class RequestHandler(BaseHTTPRequestHandler):
    server_version = "MIU/Jev MVP"

    def do_GET(self) -> None:
        if self.path == "/api/health":
            ollama = ollama_status()
            typesafe_available = bool(
                os.environ.get("TYPESAFE_API_KEY", "").strip()
            )
            default_provider = (
                "ollama"
                if ollama["compatible"]
                else "typesafe" if typesafe_available else "ollama"
            )
            self.send_json(
                {
                    "ok": True,
                    "default_provider": default_provider,
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

        requested = "index.html" if self.path in ("/", "") else self.path.lstrip("/")
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
            if self.path == "/api/moves":
                current = validate_miu(payload.get("current"), "current")
                self.send_json({"moves": legal_moves(current)})
                return
            if self.path == "/api/choose":
                current = validate_miu(payload.get("current"), "current")
                goal = validate_miu(payload.get("goal", "MU"), "goal")
                provider = payload.get("provider", DEFAULT_PROVIDER)
                if provider not in DEFAULT_MODELS:
                    raise ValueError("provider must be ollama or typesafe")
                model = payload.get("model", DEFAULT_MODELS[provider])
                policy = payload.get("policy", "guided")
                if policy not in ("guided", "model"):
                    raise ValueError("policy must be guided or model")
                history = payload.get("history", [])
                max_length = payload.get("max_length", 64)
                if not isinstance(model, str) or not model.strip():
                    raise ValueError("model must be a non-empty string")
                if not isinstance(history, list) or not all(
                    isinstance(item, str) for item in history
                ):
                    raise ValueError("history must be a list of strings")
                if (
                    not isinstance(max_length, int)
                    or isinstance(max_length, bool)
                    or not 8 <= max_length <= MAX_MIU_LENGTH
                ):
                    raise ValueError(
                        f"max_length must be an integer from 8 to {MAX_MIU_LENGTH}"
                    )
                moves = legal_moves(current)
                result = choose_move(
                    provider,
                    model,
                    policy,
                    current,
                    goal,
                    history,
                    moves,
                    max_length,
                )
                result["provider"] = provider
                result["policy"] = policy
                result["moves"] = moves
                self.send_json(result)
                return
            self.send_error(HTTPStatus.NOT_FOUND)
        except ValueError as error:
            self.send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
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
        encoded = json.dumps(payload).encode("utf-8")
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
