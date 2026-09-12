"""Serve the landing page and the authorize endpoint locally.

Usage: python dev_server.py   ->   http://localhost:8000

Mirrors what Vercel does in production: static files from public/, and
POST /api/authorize handled by the same code as api/authorize.py.
"""
import json
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from demo.scenarios import SCENARIOS
from interlock.engine import authorize
from interlock.trace import Signer

PUBLIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=PUBLIC, **kwargs)

    def _send(self, status, body):
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        if self.path.rstrip("/") != "/api/authorize":
            self._send(404, {"error": "not found"})
            return

        length = int(self.headers.get("Content-Length", 0))
        try:
            request = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send(400, {"error": "invalid JSON body"})
            return

        scenario = SCENARIOS.get(request.get("scenario", ""))
        if scenario is None:
            self._send(400, {"error": "unknown scenario"})
            return

        decision = authorize(
            scenario.mandate, scenario.payment, scenario.spent, Signer.generate()
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
        self._send(200, body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    print("Interlock dev server on http://localhost:8000")
    ThreadingHTTPServer(("127.0.0.1", 8000), Handler).serve_forever()
