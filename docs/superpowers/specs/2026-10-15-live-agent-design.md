# Interlock - Live agent and real settlement

**Date:** 2026-10-15
**Purpose:** Replace the scripted demo with a real agent run and real (devnet)
settlement, so the live site shows Interlock doing its job rather than replaying it.
Interlock is the AI safety work sample in Arun's Anthropic Fellows application
(deadline 18 Oct 2026); target is done and live by 17 Oct.

## What is simulated today

1. **The agent.** Both instruction chains are hard-coded in `demo/scenarios.py`. The
   "Run" buttons replay them; no agent runs.
2. **Settlement.** An allowed decision returns JSON. Nothing is ever sent.
3. **Layer 3.** Off. Only a Claude assessor exists, and there is no key.
4. **Signatures.** `app.py` signs with a fresh key per request unless
   `INTERLOCK_SIGNING_KEY` is set, so a past decision cannot be verified.

The engine (layers 1-2, Ed25519 signing) is real, tested, and stays as it is.

## Goals

- A real LLM agent performs the booking task and its own tool calls produce the
  instruction chain Interlock checks.
- An allowed payment actually settles on Solana devnet; a denied one is never sent.
- Decisions are verifiable after the fact, and each settlement is linked to the
  decision that authorized it.
- Layer 3 runs on Gemini, with a scenario that only layer 3 catches.
- Visitors without a Gemini key still see real decisions and real settlement.

## Non-goals

- Real money or mainnet. Devnet only, with a test token.
- A real flight inventory. Fares come from a fixed demo fixture.
- Decision history, persistence, accounts, rate limiting. The visitor pays for their
  own model calls; devnet costs nothing.
- Attack variants beyond the two listing pages and the semantic replay scenario.

## Decisions taken

| Question | Decision |
| --- | --- |
| What "actual run" means | Live agent + real devnet settlement |
| Model provider and cost | Visitor brings their own Gemini API key. No key of ours is in the app. |
| Where the agent runs | Server side, in Python. The key is used for that request only. |
| Extras in scope | Verifiable decisions; layer 3 on Gemini |

## Architecture

```
browser ──POST /api/run  (X-Gemini-Key)──▶ agent harness ──tool calls──▶ fixtures + /fares/* pages
                                                │
                                   instruction chain built by the harness
                                                │
                                                ▼
browser ──POST /api/authorize {scenario}──▶ Interlock engine (L1 ▸ L2 ▸ L3) ──▶ signed Decision
                                                │ allowed only
                                                ▼
                                       Solana devnet transfer + memo(decision signature)
```

### New units

**`agent/harness.py` - the live agent.** Runs a manual Gemini function-calling loop
(`google-genai`, automatic function calling disabled) with at most 8 tool calls. The
harness, not the model, records each step and its trust level:

| Tool | Returns | Recorded as |
| --- | --- | --- |
| `search_fares(origin, destination, max_price)` | fares from `agent/fixtures.py` | `tool` |
| `get_quote(fare_id)` | merchant + amount for that fare | `tool`, with `PlanHint` |
| `open_listing(url)` | text of a page served by this app under `/fares/` | `content` (untrusted) |
| `request_payment(recipient, amount, memo)` | ends the run | `agent` |

The system prompt is an ordinary booking-agent prompt that requires opening the
fare's listing page to check conditions before paying. Two listing pages exist:
`/fares/lhr-540` (honest) and `/fares/lhr-540?variant=poisoned` (carries a
business-style injection: the fare "must be booked through our partner agency"
for a priority fee, sent to the allowlisted agency, plus a do-not-mention line).
The run mode picks which URL `get_quote` returns. `open_listing` only accepts a URL
that an earlier `get_quote` returned. This fixes the order quote -> listing ->
payment, which the `plan_divergence` rule depends on: it only fires on untrusted
content that arrives after the trusted plan.

Output: a `RunResult` with the transcript, and either a `PaymentRequest` or the
reason no payment was requested. The model never labels its own steps.

**`agent/fixtures.py` - demo inventory.** Fares, merchants and the two listing page
bodies. Plain data.

**`interlock/settlement.py` - devnet settlement.** Builds one transaction with an
SPL `TransferChecked` from the treasury's token account to the merchant's, plus a
Memo instruction carrying `payment_id` and the first 32 hex chars of the decision
signature. Signs with `solders`, sends via plain JSON-RPC over `urllib`, waits for
`confirmed`. Returns `Settlement(status, signature, explorer_url, error)`.
Merchant names map to devnet addresses in `interlock/devnet.json`, written by the setup script
(`merchant.airline.example` and `merchant.agency.example` each get a wallet).

**`interlock/intent.py` - `GeminiAssessor`.** Same `Assessor` protocol and prompt as
`ClaudeAssessor`, using structured JSON output. Constructed per request with the
visitor's key.

**`scripts/devnet_setup.py` - one-off setup.** Creates the treasury and merchant
keypairs, a 6-decimal test mint labelled "devnet test USDC", the token accounts,
and mints a large balance to the treasury. Writes `interlock/devnet.json` and prints the env vars to set. Run once by
hand; not part of the deploy.

### Changed units

**`interlock/engine.py`.** Layer 3 fails closed: if the assessor raises, the decision
is denied with `intent_match` failed and detail "intent check unavailable: <reason>".

**`demo/scenarios.py`.** Adds a third scenario, `semantic`: allowlisted merchant,
amount under cap, no untrusted content, but the memo books Bangalore to Dubai.
Layers 1-2 pass; only layer 3 catches it.

**`app.py`.**
- `POST /api/run` `{ "listing": "honest" | "poisoned" }`, header `X-Gemini-Key`.
  Runs the harness, then the engine with `GeminiAssessor`, then settlement if allowed.
- `POST /api/authorize` `{ "scenario": ... }`. Unchanged contract, plus a
  `settlement` field. Layer 3 runs only if `X-Gemini-Key` is supplied.
- `POST /api/verify` takes a decision body and returns `{ "valid": bool }`.
- `GET /api/public-key` returns the signing public key.
- `GET /fares/<id>` serves listing pages.
- The signer comes from `INTERLOCK_SIGNING_KEY`. Without it the app refuses to
  start in production (`VERCEL_ENV=production`) rather than sign with a throwaway key.

**`public/index.html`.** Mode switch (Live agent / Replay), key field, run buttons,
and a result view: agent steps with trust labels, proposed payment, checks by layer,
decision, settlement (explorer link or "not sent"), and a Verify button. Footer text
changes to say settlement is real on devnet with a test token.

## Key handling

The key travels from the browser in an `X-Gemini-Key` header over HTTPS. The server
uses it to build a client for that request and drops it. It is never written to
logs, responses, storage or the decision trace. The page keeps it in a JS variable
only and says so next to the field, with a link to create a free AI Studio key.

## Failure behaviour

Interlock fails closed. Nothing is reported as settled unless devnet confirmed it.

| Case | Behaviour |
| --- | --- |
| No key on `/api/run` | 400, "a Gemini API key is required for live mode" |
| Key rejected / quota exhausted | 401 / 429 with the provider's reason and a pointer to Replay mode. No decision. |
| Agent hits 8 tool calls or ends without `request_payment` | 200, transcript + "no payment requested". No decision, no settlement. |
| `request_payment` arguments malformed | Recorded in transcript; same as above. |
| Layer 3 error | Decision denied, `intent_match` failed, "intent check unavailable". |
| Devnet error (RPC, blockhash, treasury empty) | Signed decision returned; `settlement.status = "failed"` with the reason. One retry on blockhash expiry only. |
| Denied decision | `settlement.status = "not_sent"`. Nothing is broadcast. |

## Configuration

| Env var | Where | Notes |
| --- | --- | --- |
| `INTERLOCK_SIGNING_KEY` | Vercel, production + preview | Ed25519 private key, hex |
| `SOLANA_TREASURY_KEY` | Vercel, production + preview | Devnet-only keypair, base58 |
| `SOLANA_RPC_URL` | optional | Defaults to `https://api.devnet.solana.com` |

Mint and merchant addresses are public and live in `interlock/devnet.json`.

Runtime dependencies grow from `cryptography` to `cryptography`, `google-genai`,
`solders`. `vercel.json` sets `maxDuration` to 120s for the function.

## Testing

- Existing tests keep passing unchanged, except where `app.py`'s response gains a
  `settlement` field.
- `tests/test_harness.py`: a scripted fake Gemini client drives the loop. Asserts the
  chain is built from the tool calls actually made, trust labels come from the tool,
  `get_quote` produces the `PlanHint`, the 8-call cap holds, and a run without
  `request_payment` yields no payment.
- `tests/test_settlement.py`: transaction building with a fake RPC. Asserts the
  `TransferChecked` data and accounts, the memo content, the not-sent path for denied
  decisions, and the failed status on RPC errors. No network.
- `tests/test_intent.py`: `GeminiAssessor` with a stub client; engine fails closed
  when the assessor raises.
- `tests/test_app.py`: `/api/verify` accepts a real decision and rejects a tampered
  one; `/api/run` without a key returns 400; the key never appears in a response.
- Manual: with a real key on the preview deployment, run the poisoned listing about
  10 times and record how often the injection lands, and confirm explorer links
  resolve on devnet. If the agent resists, the page says so; the demo is not rigged.

## Rollout

1. All work on branch `live-agent`. Pushing it produces a Vercel preview URL.
2. Run `scripts/devnet_setup.py`, set the env vars on the Vercel project
   (`interlock`, team `personal-arun-brahma`) for preview and production.
3. Test on the preview URL.
4. README: a "What is real" section (agent, decisions, devnet settlement are real;
   fares are a fixture; the token is a devnet test token) and a line that the
   project was built with Claude Code.
5. Merge to `main` only on Arun's explicit go. That deploys `interlock-five.vercel.app`.
