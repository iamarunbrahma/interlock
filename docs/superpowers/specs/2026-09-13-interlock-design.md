# Interlock - Design

**Date:** 2026-09-13
**Purpose:** Venture design and application artifacts for R[3]sidency x Construct
(Wintermute + Fabric Ventures). Application deadline 15 Sept 2026.

## Context

R[3]sidency x Construct is a 12-week, fully in-person accelerator in London (demo
day in NYC). 8 teams, $300K each for equity plus a future token allocation,
follow-on up to $1M. Partners: Fabric Ventures, Wintermute, Solana, Coinbase.

Their published thesis ("Is there anything left to build in crypto?", 15 Jul 2026)
argues the components of the machine economy are crowded and well funded, and that
the opportunity is in the connective tissue: "the rails for transaction,
coordination, and trust between machines that do not yet exist."

Three areas named: the economic layer for agents, physical AI, machine-led
discovery. Interlock targets the first.

Two failure modes they call out by name:
- **Security.** May 2026, a Morse-code prompt injection caused Grok to emit a
  transfer instruction that an automated trading agent executed on-chain, moving
  ~$150-200K (SlowMist).
- **Liability.** Feb 2026, an oracle bug in AI-assisted contract code caused a
  $1.78M bad debt event on Moonwell; AI, human reviewers and a governance vote all
  signed off and none caught it (rekt.news).

Their stated business-model preference: "The better teams here charge for
authorization and risk reduction rather than a cut of payment value, which makes
the business viable well before agent volume is real."

## Founder

Arun Brahma. Senior MLE, Walmart Global Tech. Solo founder.

- Walmart: agentic shopping assistant on multi-agent architecture + MCP,
  orchestrating Text-to-SQL, Graph and RAG sub-agents. +37% conversion in pilot
  categories via intent routing and context retrieval.
- Citi: enterprise Text-to-SQL analytics on fine-tuned Llama over financial data,
  under financial data governance constraints.
- Carelon: hybrid RAG (Qdrant + BM25) over health insurance policy documents.
- Accenture: two-tower embedding recommender, +47% CTR.
- OSS: vision-parse (481 stars), finetuned-qlora-falcon7b-medical (261),
  pdf-to-markdown (204), purr (106). ~1,050 stars total.
- Stated research interests: multi-agent systems, RLVR, agentic RAG.
- Onchain experience: none. This is a deliberate constraint on the design.

## Problem

Agents can already pay. x402, AP2 and stablecoin rails solved settlement. What is
unsolved is **authority**: who decides whether a given agent-initiated payment is
allowed, and who can defend that decision afterwards.

Today the decision is either absent (the agent holds a key and spends) or static
(wallet-level allowlists and caps that cannot tell whether a payment matches what
the human actually asked for). Neither survives a prompt injection, and neither
produces an artifact you can point at when asked who approved a loss.

## Product

A policy and authorization layer between an agent and its wallet. Per payment, it
decides whether settlement may proceed.

An authorization decision sits inline in the payment path, so it must be cheap and
fast enough to price per decision. That rules out a model call per payment as the
primary mechanism. The checks are layered accordingly, cheapest first.

**Layer 1 - deterministic.** Counterparty allowlist, per-payment cap, cumulative
budget, currency and chain match. Microseconds.

**Layer 2 - provenance (information-flow analysis).** The agent's instruction chain
is modelled as typed steps, each carrying a trust level: `principal` (the human),
`tool` (trusted structured tool output), `content` (untrusted fetched content),
`agent` (the agent's own step). Trusted tool steps may carry a structured plan hint
(recipient, amount) - what a real tool integration returns. Three rules fire:

- `override_language` - an untrusted step contains imperative text directed at the
  agent (ignore previous, new instructions, instead send, override).
- `plan_divergence` - the payment's recipient or amount differs from the last
  trusted plan, and an untrusted step intervened between that plan and the payment.
- `concealment` - untrusted content instructs the agent not to disclose a step.

This is taint tracking applied to payments. No model, no network, no secrets.

**Layer 3 - semantic escalation (optional).** A `ClaudeAssessor` that judges
intent-to-payment consistency with a model. Present in the codebase, off by default,
enabled when an API key is configured.

Output: allow or deny, with a signed, auditable reasoning trace.

Integration surface: an MCP server, so an agent wires it in one call. Also a plain
HTTP `POST /authorize`.

### Known limitation

Layer 2 catches attacks that are structurally visible - a redirected payment, an
injected imperative, a concealment instruction. It will not catch a payment that is
structurally clean but semantically wrong: an allowlisted merchant, the right
amount, for the wrong thing. That is what layer 3 is for, and the deck states this
plainly rather than implying the heuristics are complete.

## Business model

Priced per authorization decision and on risk reduction. Explicitly **not** a
percentage of payment value. This means revenue does not wait on agent payment
volume becoming real, which is the viability point their thesis makes.

Per-decision pricing only works if a decision is nearly free to produce. That is
the reason the architecture is layered the way it is, not an afterthought.

## Target users

Near-term: agent wallet and agent-infrastructure providers (Privy, Turnkey,
Crossmint, AgentKit-style platforms) who must offer policy controls to their own
customers; and crypto-native agent platforms already being exploited.

Following: enterprise agent deployments, where regulated-industry compliance
experience (Citi, Carelon) is the differentiator.

## Chains

Solana first - core ecosystem partner of the program, and x402 is live there. Base
second, via Coinbase and x402's origin. Long-term chain-agnostic: authorization is
a policy layer above settlement, and neutrality across rails is a structural
position the platforms cannot occupy.

## Competition

| Who | What they do | Gap |
|---|---|---|
| Privy, Turnkey, Fireblocks | Wallet-level policy engines | Static rules; no intent understanding, no injection detection |
| Lakera and prompt-injection vendors | Guardrails on model input/output | Understand text, not payments or settlement |
| AP2, x402 | Define the authorization envelope | Define the format, not the judgment of whether to grant it |
| Coinbase, Stripe | Could build it | Neutral-trust product; nobody routes risk decisions through a competitor's rail |

Why this founder wins: the judgment call is a semantic problem over intent and
instruction provenance, which is ML ground rather than crypto-native ground.

## Honesty constraints

The application will state, without softening:
- Stage: idea stage.
- Started: recently, September 2026.
- Traction: no users, no revenue, not incorporated.
- No fabricated metrics, no invented pilots, no implied customers.

What carries the application instead: a working adversarial demo, a public repo,
the OSS track record, and production multi-agent experience at Walmart scale.

## Deliverables

1. **Demo** - policy engine + MCP server + attack harness. A prompt-injected agent
   must actually be blocked; a clean agent must actually pass.
2. **Landing page** - hosts the live attack demo, deployed on Vercel. Satisfies the
   required "website or demo" field.
3. **Deck** - 10-12 slide PDF for the required file upload. Readable without the
   founder present.
4. **Form answers** - all required fields drafted honestly.

## Success criteria

- Injected run denied, clean run allowed, both reproducible from the repo with no
  API key, no account, and no network: `pip install -r requirements.txt && pytest`.
- Landing page live on a public URL with the demo callable from the browser, and
  deployable with zero secrets configured.
- Deck exported to PDF.
- Every form field has an answer; no field contains a fabricated fact.
- Submitted before end of 14 Sept 2026 (deadline has no stated timezone).

## Out of scope

No smart contracts. No token design. No real funds movement - the demo operates on
testnet semantics and simulated settlement, and says so plainly.
