from __future__ import annotations

import argparse
import json
import mimetypes
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
DEFAULT_MODEL = "nimble:latest"
MAX_BODY_BYTES = 1_000_000
CHOICE_KEYS = string.ascii_uppercase


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
    return value


def ollama_decision(
    model: str,
    current: str,
    goal: str,
    history: list[str],
    candidates: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, float]]:
    criteria: dict[str, str] = {}
    by_key: dict[str, dict[str, Any]] = {}
    for key, move in zip(CHOICE_KEYS, candidates):
        by_key[key] = move
        criteria[key] = (
            f"{move['label']}; result: {move['result']}; "
            f"length: {len(move['result'])}; "
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
    }
    request_body = {
        "model": model,
        "state": state,
        "questions": {
            "next_move": {
                "type": "choice",
                "instructions": (
                    "Select the legal move most promising for reaching the target. Prefer the "
                    "target immediately, then novel states that appear to make structural "
                    "progress. Avoid previously visited states and uncontrolled growth unless "
                    "growth creates a useful rewrite opportunity."
                ),
                "criteria": criteria,
            }
        },
        "keep_alive": "10m",
    }
    encoded = json.dumps(request_body).encode("utf-8")
    request = urllib.request.Request(
        OLLAMA_URL,
        data=encoded,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama returned HTTP {error.code}: {detail}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Could not reach Ollama at 127.0.0.1:11434: {error.reason}") from error

    answer = payload.get("answers", {}).get("next_move", {})
    selected_key = answer.get("choice")
    if selected_key not in by_key:
        raise RuntimeError("Ollama returned an invalid move choice")
    probabilities = {
        by_key[key]["id"]: float(probability)
        for key, probability in answer.get("probabilities", {}).items()
        if key in by_key
    }
    return by_key[selected_key], probabilities


def choose_move(
    model: str,
    current: str,
    goal: str,
    history: list[str],
    moves: list[dict[str, Any]],
) -> dict[str, Any]:
    if not moves:
        raise ValueError("There are no legal moves from the current string")

    rounds: list[dict[str, Any]] = []
    contenders = moves
    round_number = 1
    while len(contenders) > 1:
        winners: list[dict[str, Any]] = []
        round_probabilities: dict[str, float] = {}
        for offset in range(0, len(contenders), len(CHOICE_KEYS)):
            group = contenders[offset : offset + len(CHOICE_KEYS)]
            if len(group) == 1:
                winner = group[0]
                probabilities = {winner["id"]: 1.0}
            else:
                winner, probabilities = ollama_decision(
                    model, current, goal, history, group
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
            self.send_json({"ok": True, "model": DEFAULT_MODEL})
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
                model = payload.get("model", DEFAULT_MODEL)
                history = payload.get("history", [])
                if not isinstance(model, str) or not model.strip():
                    raise ValueError("model must be a non-empty string")
                if not isinstance(history, list) or not all(
                    isinstance(item, str) for item in history
                ):
                    raise ValueError("history must be a list of strings")
                moves = legal_moves(current)
                result = choose_move(model, current, goal, history, moves)
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
