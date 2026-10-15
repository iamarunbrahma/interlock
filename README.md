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
- `plan_divergence` - untrusted content appeared after a trusted plan, and the payment
  matches none of the trusted plans made before that content (a later re-quote does not count)
- `concealment` - untrusted content instructs the agent not to disclose a step

**Layer 3 - semantic escalation (optional).** A model judges intent-to-payment
consistency. Off by default; only sees what layers 1 and 2 could not settle.

Every decision is signed with Ed25519, the same curve Solana uses, producing a
verifiable trace.

![Interlock denying an injected payment](docs/img/denied.png)

## Run it

```bash
pip install -r requirements-dev.txt
python -m demo.run_attack
```

Runtime dependencies are `cryptography`, `google-genai` and `solders`. `requirements-dev.txt`
adds `pytest` and `mcp` for the tests and the MCP server.

Two scenarios run against the engine. The clean payment is allowed. The injected one
is denied - even though it passes every deterministic check: the recipient is
allowlisted, the amount is under the cap, the chain is right. A poisoned web page in
the instruction chain redirected it, and that is only visible in the provenance layer.

Tests:

```bash
python -m pytest
```

The landing page and its endpoint, locally:

```bash
python app.py   # http://localhost:8000
```

Devnet settlement needs a one-off setup, then two environment variables:

```bash
python -m scripts.devnet_setup   # writes interlock/devnet.json, prints the treasury key
export SOLANA_TREASURY_KEY=...   # printed by the script
export INTERLOCK_SIGNING_KEY=... # any Ed25519 private key, hex
python app.py
```

Live mode takes the visitor's Gemini key from the page, per request; nothing is configured
server side for it.

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

Or on Gemini, which is what the live demo uses:

```python
from interlock.intent import GeminiAssessor

decision = authorize(mandate, payment, spent, signer, GeminiAssessor(api_key))
```

If the assessor fails for any reason, the decision is a denial.

## What it does not catch yet

Provenance analysis catches what is structurally visible. It will not catch a payment
that is structurally clean but semantically wrong - the right merchant, the right
amount, for the wrong thing. That is what layer 3 is for. It runs on Gemini with the
caller's key and fails closed, but it is a model's judgement, so it is only as good as
the model.

## What is real

- **The agent.** In Live mode a Gemini model (`gemini-flash-lite-latest` by default) books
  the flight with tools. The instruction chain Interlock checks is built by the harness
  from the tool calls the agent actually made; trust levels come from which tool produced
  a step, never from the model.
- **The decisions.** Every decision is signed with one published Ed25519 key, binds the
  payment terms (recipient, amount, currency, chain), and can be checked at `/api/verify`.
- **The settlement.** Allowed payments are sent on Solana devnet as an SPL transfer with a
  memo carrying the payment id and the start of the decision signature. Denied payments
  are never sent, and settlement refuses any decision not signed by this deployment's key
  over exactly the terms being paid.

What is not: the fares are a fixture, the merchants are example names, and the token is a
devnet test token standing in for USDC. No real money moves. Each run is a fresh mandate,
so the total budget applies within one run.

How the live agent behaves: against the poisoned listing (which tells it to pay a partner
agency instead of the airline), `gemini-flash-lite-latest` resisted in 10 of 10 runs, and
each of those payments to the quoted fare was allowed and settled. An agent that does
follow the injection is stopped by `plan_divergence`; the Replay mode's injected scenario
shows that case.

Built with Claude Code.
