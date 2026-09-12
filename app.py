"""HTTP entrypoint - serves the landing page and the authorization endpoint.

Used both locally (`python app.py`) and as the deployed entrypoint.
"""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from demo.scenarios import SCENARIOS
from interlock.engine import authorize
from interlock.trace import Signer

PUBLIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public")


def _signer() -> Signer:
    key = os.environ.get("INTERLOCK_SIGNING_KEY")
    return Signer.from_hex(key) if key else Signer.generate()


def decide(name: str) -> dict:
    """Run one named demo scenario and return its decision plus the scenario."""
    scenario = SCENARIOS[name]
    decision = authorize(
        scenario.mandate, scenario.payment, scenario.spent, _signer()
    )
    body = decision.to_dict()
    body["scenario"] = {
        "name": scenario.name,
        "description": scenario.description,
        "intent": scenario.mandate.intent,
        "recipient": scenario.payment.recipient,
        "amount": str(scenario.payment.amount),
        "currency": scenario.payment.currency,
        "chain": scenario.payment.chain,
        "memo": scenario.payment.memo,
        "instruction_chain": [
            {"source": s.source, "trust": s.trust.value, "content": s.content}
            for s in scenario.payment.instruction_chain
        ],
    }
    return body


class handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, body: dict) -> None:
        self._send(status, json.dumps(body).encode(), "application/json")

    def do_GET(self) -> None:
        with open(os.path.join(PUBLIC, "index.html"), "rb") as f:
            self._send(200, f.read(), "text/html; charset=utf-8")

    def do_POST(self) -> None:
        if self.path.split("?")[0].rstrip("/") != "/api/authorize":
            self._json(404, {"error": "not found"})
            return

        try:
            length = int(self.headers.get("Content-Length", 0))
            request = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._json(400, {"error": "invalid JSON body"})
            return

        name = request.get("scenario", "")
        if name not in SCENARIOS:
            self._json(
                400, {"error": f"unknown scenario; expected one of {sorted(SCENARIOS)}"}
            )
            return

        self._json(200, decide(name))

    def log_message(self, *args) -> None:
        pass


if __name__ == "__main__":
    print("Interlock on http://localhost:8000")
    ThreadingHTTPServer(("127.0.0.1", 8000), handler).serve_forever()
