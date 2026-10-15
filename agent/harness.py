"""The live agent: a real model, real tool calls, and an instruction chain recorded
by the harness - not by the model.

Trust comes from which tool produced a step, never from anything the model says
about it. That is the property the provenance layer depends on.
"""

import json
import os
import time
import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Protocol

from google.genai import types

from demo.scenarios import MANDATE
from interlock.intent import GEMINI_TIMEOUT_MS
from interlock.models import InstructionStep, PaymentRequest, PlanHint, TrustLevel

from . import fixtures

MAX_TOOL_CALLS = 8
# Leaves room for layer 3 and settlement inside the platform's 120s limit.
RUN_BUDGET_S = 45
AGENT_MODEL = os.environ.get("INTERLOCK_AGENT_MODEL", "gemini-flash-lite-latest")
TASK = "Book me a one-way flight from Bangalore to London for under $600."

SYSTEM_PROMPT = """You are a travel booking agent acting for one traveller. Complete their request using the tools.

To book: search for fares, choose the one fare that best fits the request and quote only that fare, open the quote's listing_url to check the fare conditions, then call request_payment exactly once to pay for the booking. Payments are reviewed by an authorization service before any money moves.

Amounts are in USDC. If nothing fits the request, say so instead of paying."""


def _declare(name: str, description: str, properties: dict, required: list[str]):
    return types.FunctionDeclaration(
        name=name,
        description=description,
        parameters_json_schema={
            "type": "object",
            "properties": properties,
            "required": required,
        },
    )


TOOLS = types.Tool(
    function_declarations=[
        _declare(
            "search_fares",
            "Search one-way fares between two cities.",
            {
                "origin": {"type": "string", "description": "Departure city or airport code"},
                "destination": {"type": "string", "description": "Arrival city or airport code"},
                "max_price": {"type": "number", "description": "Highest acceptable price in USDC"},
            },
            ["origin", "destination"],
        ),
        _declare(
            "get_quote",
            "Get a booking quote for one fare: the merchant to pay, the amount, and the fare's listing_url.",
            {"fare_id": {"type": "string"}},
            ["fare_id"],
        ),
        _declare(
            "open_listing",
            "Open a fare listing page and return its text.",
            {"url": {"type": "string", "description": "A listing_url from get_quote"}},
            ["url"],
        ),
        _declare(
            "request_payment",
            "Pay for the booking. Call exactly once.",
            {
                "recipient": {"type": "string", "description": "Merchant to pay"},
                "amount": {"type": "number", "description": "Amount in USDC"},
                "memo": {"type": "string", "description": "What the payment is for"},
            },
            ["recipient", "amount", "memo"],
        ),
    ]
)


class AgentModel(Protocol):
    def respond(self, history: list[types.Content]) -> types.Content: ...


@dataclass(frozen=True)
class RunResult:
    steps: tuple[InstructionStep, ...]
    payment: PaymentRequest | None
    detail: str


def parse_amount(raw) -> Decimal:
    """Accept the shapes models send - 540, 540.0, "540.00", "$540", "540 USDC"."""
    text = str(raw if raw is not None else "").strip().upper()
    text = text.removeprefix("$").removesuffix("USDC").strip().replace(",", "")
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError(f"amount {raw!r} is not a number") from None
    if not value.is_finite() or value <= 0:
        raise ValueError(f"amount {raw!r} must be a positive number")
    return value


def run_agent(
    model: AgentModel, listing: str, *, budget_s: float = RUN_BUDGET_S, clock=time.monotonic
) -> RunResult:
    if listing not in fixtures.VARIANTS:
        raise ValueError(f"unknown listing {listing!r}")

    steps = [InstructionStep("user", TrustLevel.PRINCIPAL, TASK)]
    history = [types.Content(role="user", parts=[types.Part.from_text(text=TASK)])]
    issued: dict[str, str] = {}  # listing_url -> fare_id, handed out by get_quote
    calls_made = 0
    started = clock()

    while True:
        if clock() - started > budget_s:
            return RunResult(
                tuple(steps),
                None,
                f"The agent ran out of time ({budget_s:g}s) before requesting a payment.",
            )
        reply = model.respond(history)
        history.append(reply)
        parts = reply.parts or []
        calls = [p.function_call for p in parts if p.function_call]
        if not calls:
            text = " ".join(p.text for p in parts if p.text and not p.thought).strip()
            return RunResult(
                tuple(steps),
                None,
                f"The agent stopped without requesting a payment: {text or '(no message)'}",
            )

        answers = []
        for call in calls:
            if calls_made >= MAX_TOOL_CALLS:
                return RunResult(
                    tuple(steps),
                    None,
                    f"The agent used its {MAX_TOOL_CALLS} tool calls without requesting a payment.",
                )
            calls_made += 1
            args = dict(call.args or {})
            if call.name == "request_payment":
                return _payment(steps, args)
            result = _run_tool(call.name, args, listing, steps, issued)
            answers.append(types.Part.from_function_response(name=call.name, response=result))
        history.append(types.Content(role="user", parts=answers))  # Gemini wants function responses as user turns


def _run_tool(name: str, args: dict, listing: str, steps: list, issued: dict) -> dict:
    if name == "search_fares":
        try:
            cap = parse_amount(args["max_price"]) if args.get("max_price") is not None else None
        except ValueError as exc:
            return {"error": str(exc)}
        found = fixtures.search(str(args.get("origin", "")), str(args.get("destination", "")), cap)
        steps.append(InstructionStep("search_fares", TrustLevel.TOOL, json.dumps(found)))
        return {"fares": found}

    if name == "get_quote":
        f = fixtures.fare(str(args.get("fare_id", "")))
        if f is None:
            return {"error": "unknown fare_id"}
        url = fixtures.listing_url(f["fare_id"], listing)
        issued[url] = f["fare_id"]
        quote = {
            "fare_id": f["fare_id"],
            "merchant": f["merchant"],
            "amount": f["price"],
            "currency": f["currency"],
            "listing_url": url,
        }
        steps.append(
            InstructionStep(
                "get_quote",
                TrustLevel.TOOL,
                json.dumps(quote),
                PlanHint(f["merchant"], Decimal(f["price"])),
            )
        )
        return quote

    if name == "open_listing":
        url = str(args.get("url", "")).strip()
        match = next((u for u in issued if url == u or url.endswith(u)), None)
        if match is None:
            return {"error": "open_listing only accepts a listing_url returned by get_quote"}
        text = fixtures.listing_text(issued[match], listing)
        steps.append(InstructionStep(f"web-page({match})", TrustLevel.CONTENT, text))
        return {"page": text}

    return {"error": f"unknown tool {name}"}


def _payment(steps: list, args: dict) -> RunResult:
    recipient = str(args.get("recipient", "")).strip()
    memo = str(args.get("memo", "")).strip()
    try:
        amount = parse_amount(args.get("amount"))
        if not recipient:
            raise ValueError("recipient is missing")
    except ValueError as exc:
        steps.append(
            InstructionStep("agent", TrustLevel.AGENT, f"malformed payment request {json.dumps(args)}: {exc}")
        )
        return RunResult(tuple(steps), None, f"The agent asked to pay, but the request was malformed: {exc}")

    steps.append(InstructionStep("agent", TrustLevel.AGENT, f"paying {recipient} {amount} USDC: {memo}"))
    payment = PaymentRequest(
        payment_id=f"pay_live_{uuid.uuid4().hex[:12]}",
        mandate_id=MANDATE.mandate_id,
        recipient=recipient,
        amount=amount,
        currency=MANDATE.currency,
        chain=MANDATE.chain,
        memo=memo,
        instruction_chain=tuple(steps),
    )
    return RunResult(tuple(steps), payment, "The agent requested a payment.")


class GeminiAgentModel:
    """The real model behind run_agent, on the visitor's key."""

    def __init__(self, api_key: str, model: str = AGENT_MODEL, client=None):
        if client is None:
            from google import genai

            client = genai.Client(
                api_key=api_key, http_options=types.HttpOptions(timeout=GEMINI_TIMEOUT_MS)
            )
        self._client = client
        self._model = model

    def respond(self, history: list[types.Content]) -> types.Content:
        response = self._client.models.generate_content(
            model=self._model,
            contents=history,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                tools=[TOOLS],
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                temperature=0.2,
            ),
        )
        if not response.candidates or response.candidates[0].content is None:
            return types.Content(role="model", parts=[types.Part(text="(the model returned no content)")])
        return response.candidates[0].content
