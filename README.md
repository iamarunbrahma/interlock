# Interlock

The authorization layer that decides whether an AI agent's payment is allowed to settle.

Agents can already pay. x402, AP2 and stablecoin rails solved settlement. What is
unsolved is **authority**: who decides whether a given agent-initiated payment is
allowed, and who can defend that decision afterwards. Today that decision is either
absent (the agent holds a key and spends) or static (allowlists and caps that cannot
tell whether a payment matches what the human actually asked for). Neither survives a
prompt injection, and neither leaves an artifact you can point at when someone asks
who approved a loss.

## How it works

An authorization decision sits inline in the payment path, so it has to be cheap and
fast enough to price per decision. The checks are layered accordingly, cheapest first,
and short-circuit.

**Layer 1 - deterministic.** Counterparty allowlist, per-payment cap, cumulative
budget, currency and chain.

**Layer 2 - provenance.** Taint tracking applied to payments. The agent's instruction
chain is modelled as typed steps, each carrying a trust level - `principal` (the
human), `tool` (trusted structured output), `content` (untrusted fetched content),
`agent`. Trusted tool steps may carry a structured plan hint. Three rules fire:

- `override_language` - untrusted content contains imperative text aimed at the agent
- `plan_divergence` - the payment differs from the last trusted plan, and untrusted
  content intervened between that plan and the payment
- `concealment` - untrusted content instructs the agent not to disclose a step

**Layer 3 - semantic escalation (optional).** A model judges intent-to-payment
consistency. Off by default; only sees what layers 1 and 2 could not settle.

Every decision is signed with Ed25519, the same curve Solana uses, producing a
verifiable trace.

## Run it

```bash
pip install -r requirements.txt
python -m demo.run_attack
```

`requirements.txt` is the runtime dependency only (`cryptography`). For the tests and
the MCP server, install `requirements-dev.txt` instead.

Two scenarios run against the engine. The clean payment is allowed. The injected one
is denied - even though it passes every deterministic check: the recipient is
allowlisted, the amount is under the cap, the chain is right. A poisoned web page in
the instruction chain redirected it, and that is only visible in the provenance layer.

Tests:

```bash
pip install -r requirements-dev.txt
python -m pytest
```

The landing page and its endpoint, locally:

```bash
python dev_server.py   # http://localhost:8000
```

## Use it from an agent

As an MCP server:

```bash
python mcp_server.py
```

It exposes one tool, `authorize_payment`. Call it before signing or broadcasting any
transaction. Each `instruction_chain` entry is a dict with `source`, `trust` (one of
`principal`/`tool`/`content`/`agent`), `content`, and optionally `plan_recipient` and
`plan_amount` for trusted tool steps that established the payment parameters.

Or directly:

```python
from decimal import Decimal
from interlock.engine import authorize
from interlock.trace import Signer

decision = authorize(mandate, payment, Decimal("0"), Signer.generate())
print(decision.allowed, decision.to_dict()["checks"])
```

### Enabling layer 3

```bash
pip install anthropic
export ANTHROPIC_API_KEY=...
```

```python
from interlock.intent import ClaudeAssessor

decision = authorize(mandate, payment, spent, signer, ClaudeAssessor())
```

## What it does not catch yet

Provenance analysis catches what is structurally visible. It will not catch a payment
that is structurally clean but semantically wrong - the right merchant, the right
amount, for the wrong thing. That is what layer 3 is for, and it is the next thing to
build out.

## Note

This is early-stage work. Settlement is simulated; no funds move. The demo scenarios
use example counterparties, not real merchants.
