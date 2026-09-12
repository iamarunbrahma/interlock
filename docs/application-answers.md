# R[3]sidency × Construct - application answers

Draft for review. Nothing here is submitted.

**Still needed from Arun:** current city (City, Country).

---

# Page 1 - Application Form

## Team/Project Name

Interlock

## First Name

Arun

## Last Name

Brahma

## Email

contact@arunbrahma.com

## Telegram Handle

No Telegram - best reached at contact@arunbrahma.com

*(Field is required by the form but unvalidated, so this passes. Arun does not use
Telegram.)*

## What category best describes your project?

**AI Infrastructure & Tooling**

## Which statement best describes your current product status?

**We have developed a Proof of Concept (POC)**

Working engine, full test suite, public live demo. No users yet.

---

# Page 2 - Team & Company

## Have you incorporated a company yet?

**No, but willing to incorporate if selected for the program**

## Which country have you incorporated in or intend to incorporate in?

United Kingdom, given the program runs out of London and my first design partners are
likely to be European agent-infrastructure teams. Open to Delaware instead if that
suits the investor syndicate better.

## How many full time people will be working on the project?

1

## Team Details

**Arun Brahma** - Founder (CEO/CTO)
X: none
Telegram: none - reachable at contact@arunbrahma.com
LinkedIn: https://linkedin.com/in/iamarunbrahma
GitHub: https://github.com/iamarunbrahma
ENS: none
Website: https://arunbrahma.com

Background: Senior Machine Learning Engineer at Walmart Global Tech, working on Gen AI
initiatives - most recently the Agentic AI Shopping Assistant, a multi-agent system
built on MCP that orchestrates Text-to-SQL, graph and RAG sub-agents. Previously built
an enterprise Text-to-SQL analytics platform at Citi on a fine-tuned Llama over
financial data under financial data governance, a hybrid RAG system over health
insurance policy documents at Carelon, and a two-tower recommender at Accenture.
Maintains four open-source ML tools with roughly 1,050 GitHub stars between them.

## Provide evidence of exceptional ability or achievements within the team

I build multi-agent systems that run in production at retail scale. At Walmart Global
Tech I built the Agentic AI Shopping Assistant on a multi-agent MCP architecture
orchestrating Text-to-SQL, graph and RAG sub-agents, which lifted conversion 37% across
pilot categories through intent routing and context retrieval. Before that I shipped an
enterprise Text-to-SQL platform at Citi on a fine-tuned Llama over financial data under
financial data governance (+65% analyst productivity), and a hybrid Qdrant + BM25 RAG
system over health insurance policy documents at Carelon (+23% customer satisfaction).
My open-source work has drawn roughly 1,050 GitHub stars across four projects -
vision-parse (481), a PDF-to-markdown library using vision LLMs that benchmarked 0.88
markdown accuracy against Microsoft MarkItDown's 0.52; finetuned-qlora-falcon7b-medical
(261); pdf-to-markdown (204); and purr (105). The through-line is intent
understanding and agent orchestration in domains where being wrong is expensive, which
is exactly the problem Interlock is built on.

## Where do the team members currently work?

`[NEEDED - City, Country]`

## If accepted to the program, would you be willing to work primarily onsite in London during the program?

**Yes**

## Website URL

https://interlock-personal-arun-brahma.vercel.app

## Company Twitter URL

`[none yet - leave blank]`

## Where are most founders located?

**Asia**

## If one or more founders are not working from the above location, from which city/country they're working out of?

Not applicable - solo founder.

---

# Page 3 - Product

## What are you building or planning to build?

The authorization layer that decides whether an AI agent's payment is allowed to settle.

## Pitch the idea in one paragraph. What makes it interesting or different?

Agents can already pay - x402, AP2 and stablecoin rails solved settlement, and agent
wallets shipped at Coinbase, Robinhood and Binance. What nobody solved is who holds
authority when the agent is wrong. In May 2026 a prompt injection moved roughly $200K
out of a trading agent; in February an AI-assisted contract bug cost Moonwell $1.78M
with human reviewers and a governance vote in the loop. Interlock sits between an agent
and its wallet and decides, per payment, whether it may settle. The part that is
different is how: instead of asking a model whether each payment looks sensible, it
models the agent's instruction chain as typed steps carrying trust levels and applies
taint tracking to the payment - did anything untrusted get between the plan and the
payment, does the payment diverge from the last trusted plan, is something asking the
agent to conceal a step. That is a structural question answered structurally, in
microseconds, with no model call. Every decision is signed with Ed25519, so there is a
defensible answer to "who approved this" afterwards. It matters commercially because we
charge per authorization decision and for risk reduction rather than a cut of payment
value, and that pricing only works if a decision is nearly free to produce - which is
also why an authorization layer built on a per-payment model call cannot sit inline in
a checkout.

## When did you start working on this startup? Why did you choose this idea?

I started on Interlock in September 2026, so this is early and I would rather say so
than dress it up. There have been no pivots - there has not been time for one.

The idea is not new to me even if the company is. At Walmart I built the agentic
shopping assistant, which is the buy side of agent commerce, and the same blocker came
up every time we pushed toward letting the agent actually transact rather than just
recommend: the moment an agent can move money, somebody has to be accountable for why a
given action was permitted, and nothing in the stack owned that. Wallet policy engines
check the transaction. Prompt-injection guardrails check the text. Neither one connects
what the human asked for to what the agent is about to pay, and neither leaves an
artifact you can point at afterwards.

Reading Wintermute's "Is there anything left to build in crypto?" was what turned that
into a company rather than a complaint. The essay names the two failure modes -
security and liability - and says the opportunity is in the connective tissue rather
than the components. That is the same gap I kept hitting from the other side. So I
built the thing: engine, provenance layer, MCP server, signed traces, public demo,
tests. It is small and it works and you can run it yourself.

## Which chain(s) are you building on?

Solana first, and not only because it is the program's ecosystem partner. Solana now
carries roughly 70% of monthly x402 volume, which means the agent payment flows
Interlock authorizes are already happening there at scale - 400ms finality and
sub-cent fees are what make per-request agent payments viable in the first place, and
per-request payments are exactly where a per-decision authorization layer belongs. Base
second, via Coinbase and x402's origin.

Longer term the honest answer is chain-agnostic, and deliberately so. Authorization is a
policy layer that sits above settlement: Interlock never holds keys and never touches
the transfer, it returns a signed allow or deny before the agent signs. That neutrality
is also the strategic position - an agent platform will not route its risk decisions
through a rail owned by a competitor, which is a structural advantage the large
platforms cannot occupy.

## Who are your target users or use case?

Teams that have given an LLM the ability to move money. Near-term the sharpest buyers
are agent wallet and agent-infrastructure providers (Privy, Turnkey, Crossmint,
AgentKit-style platforms) who need to offer policy controls to their own customers, and
crypto-native agent platforms that are already being exploited. Enterprise agent
deployments follow, and that is where regulated-industry experience becomes the
differentiator.

## Do you already have users, traction, or community?

No users, no revenue, no community. The project is days old and I am not going to
invent traction.

What exists instead is working software anyone can verify. The engine, the provenance
layer, the MCP server and the signed decision traces are all built and tested, and the
demo is live at https://interlock-personal-arun-brahma.vercel.app - two payments against
the same mandate, one clean and one carrying a prompt injection, both of which pass
every static rule, and only one of which Interlock allows. The source is public at
https://github.com/iamarunbrahma/interlock; cloning it and running
`python -m demo.run_attack` reproduces the result locally.

On the question of whether I ship: four open-source projects at roughly 1,050 GitHub
stars is the closest proxy I can offer.

## Do you have a deck or memo?

`[UPLOAD: docs/interlock-deck.pdf]`

## Do you have a website or demo?

https://interlock-personal-arun-brahma.vercel.app (live demo)
https://github.com/iamarunbrahma/interlock (source)

## What other companies are solving this problem today or could if they wanted to? Why will you succeed against them?

Four groups are near this, and none of them are in it.

Wallet policy engines - Privy, Turnkey, Fireblocks - enforce allowlists, caps and
velocity limits. They are necessary and they are the thing my demo defeats: the injected
payment passes every one of those rules, because they inspect the transaction and never
the reasoning that produced it.

Prompt-injection guardrail vendors such as Lakera analyse model input and output. They
understand text and have no notion of a payment, a mandate, or a counterparty, so they
cannot tell an injected instruction that matters from one that does not.

Protocols - AP2 and x402 - define the envelope for authorization. They specify how a
mandate is expressed and carried. They deliberately do not decide whether to grant one;
that is the layer above, and it is the layer I am building.

The platforms - Coinbase, Stripe - could build this and may. The reason I think they
will not own it is structural rather than technical: a risk decision routed through a
rail you compete with is a non-starter for everyone else on the rail. Trust layers
consolidate around neutral parties.

Why me specifically: the hard part is the judgment, and the judgment is an intent and
provenance problem rather than a crypto problem. Deciding whether a payment is a
faithful execution of what a human asked is the same problem as intent routing in a
multi-agent shopping assistant, which is what I spent the last stretch of my career
doing in production. I came to this from the agent side rather than the chain side, and
that is the side the gap is on.

---

# Page 4 - Financials & Fundraising

## Have you raised money in the past (tokens, equity or grants etc.)?

No. No equity, no tokens, no grants, no angel money. Interlock is self-funded and
pre-incorporation, and there is no cap table to describe yet.

## Please give details on your current fundraising plans

R[3]sidency × Construct is the raise I am pursuing. The $300K would be the first outside
capital in the company and would fund roughly twelve months: incorporation, my own
runway so I can leave Walmart and work on this full-time, and the first two hires once
there are design partners to build against.

I am not running a parallel process or holding a term sheet. If the program goes well I
would expect to raise a pre-seed off Demo Day; if it does not, I would rather keep
building on a small base than raise against a story I have not tested.

## Do you plan to launch a digital asset (e.g. token or coin)?

**Not sure**

## Where do you expect the value of your project to accrue to today or in the near future?

**100% Equity**

## What is your most recent equity valuation?

N/A - not incorporated, no priced round, no SAFE outstanding.

## What is your most recent token valuation?

N/A - no token.

## What is your current burn rate?

$0/month. Self-funded, no entity, no payroll, and the demo runs on free-tier hosting
with no paid dependencies.

## What is your current runway?

**>12 months**

---

# Page 5

## Where did you hear about this accelerator?

X (Twitter) - a post from @suraj_sharma14 on 11 September 2026 about the Machine
Economy cohort, which led me to wintermute.com/construct.

## What convinced you to apply to R[3]sidency x Construct?

Your own essay, honestly. "Is there anything left to build in crypto?" argues that the
components are crowded and the opportunity is in the rails for transaction, coordination
and trust between machines that do not yet exist, and it names the two failure modes -
the Grok injection and the Moonwell liability chain - that Interlock is built around. I
had been circling this problem from the agent side at Walmart without a frame for it.
The essay was the frame.

Two other things. The first is that it says the better teams charge for authorization
and risk reduction rather than a cut of payment value, which is not a throwaway line -
it is a constraint that decides the architecture, and it is why Interlock's expensive
layer is optional and off by default instead of sitting in the payment path. Reading
that told me the people running this program have actually thought about the unit
economics of the thing I am building.

The second is Wintermute specifically. This product has to be adopted by people who
move real money and have been burned, and it has to be neutral enough that competitors
will both route through it. Feedback from a firm that has traded through every cycle
since 2017 and incubated Bebop and Wildcat is worth more to me here than a larger check
from a generalist fund. I would rather have my assumptions broken in week two of a
twelve-week program than in month nine of a seed round.

## Anything you would like to add?

Three things I would rather you hear from me than discover.

I am solo, and I know how that reads for an accelerator that weights team heavily. I am
not going to argue it is a strength. What I will say is that the thing is built and
publicly runnable rather than described, which is the only evidence a solo founder can
offer in place of a co-founder. I am actively looking for a technical co-founder and
would treat introductions inside the cohort as one of the most valuable things the
program could give me.

On the token question, I answered "Not sure" and "100% Equity" rather than picking the
answer that fits an accelerator that takes a token allocation. Interlock today is B2B
infrastructure priced per decision and I cannot presently see what a token would do for
it that equity does not. If the product evolves toward a decentralized attestation
network where independent parties sign authorization decisions, that changes, and I
would want to work that through with you properly rather than assert a token thesis I
have not earned.

And on what the software does not do yet: the provenance layer catches what is
structurally visible - a redirected payment, an injected imperative, a concealment
instruction. It will not catch a payment that is structurally clean but semantically
wrong, meaning the right merchant and the right amount for the wrong thing. That is what
the optional model layer is for and it is the next thing to build. I would rather have
that in the application than have you find it in the code.
