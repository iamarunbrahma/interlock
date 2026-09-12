import json
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from demo.scenarios import SCENARIOS  # noqa: E402
from interlock.engine import authorize  # noqa: E402
from interlock.trace import Signer  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: dict) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", 0))
            request = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._send(400, {"error": "invalid JSON body"})
            return

        scenario = SCENARIOS.get(request.get("scenario", ""))
        if scenario is None:
            self._send(
                400, {"error": f"unknown scenario; expected one of {sorted(SCENARIOS)}"}
            )
            return

        signer = (
            Signer.from_hex(os.environ["INTERLOCK_SIGNING_KEY"])
            if os.environ.get("INTERLOCK_SIGNING_KEY")
            else Signer.generate()
        )
        decision = authorize(scenario.mandate, scenario.payment, scenario.spent, signer)

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
