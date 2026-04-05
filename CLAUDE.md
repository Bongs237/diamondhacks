@AGENTS.md

# EventPulse

Group event planning via SMS. Organizer creates a group on a dashboard, adds friends by phone number. AI agents handle discovery, voting, payment, and dropout handling — all through text messages powered by ASI:One agents on Agentverse.

Think When2Meet but it also decides WHERE to go, and the interface is texting.

## How It Works

1. Organizer visits dashboard → creates group → adds friends' phone numbers
2. Each friend gets an SMS from EventPulse asking about their preferences
3. Friend texts back naturally ("comedy and live music, budget $50, nothing far")
4. LLM parses into structured JSON profile, confirms via text
5. Agents discover events via Ticketmaster API + Browser Use
6. Each friend's personal agent votes independently based on their private preferences
7. GroupConsensusAgent runs ranked-choice voting with vetoes
8. CommitmentAgent places Stripe auth holds ($X held on each card)
9. On quorum → tickets purchased
10. If someone drops out → automatic refund + cost redistribution to remaining friends
11. GroupHistoryAgent tracks who flaked for future events

## Message Flow

```
Friend SMS → Twilio webhook → FastAPI /webhooks/twilio
    → conversation.py maps phone → ASI:One session ID
    → asi_one.py POSTs to api.asi1.ai/v1/chat/completions
        (model: "asi1", header: x-session-id per friend)
    → ASI:One discovers OrchestratorAgent on Agentverse via Chat Protocol
    → Agent processes, responds via Chat Protocol
    → Response returns through ASI:One API
    → twilio_service.py sends SMS back to friend
```

## Architecture

```
┌──────────────┐         ┌──────────────┐
│  Dashboard   │         │   Twilio     │
│  (separate   │         │   (SMS)      │
│  team member │         │  All friend  │
│  owns this)  │         │  interaction │
└──────┬───────┘         └──────┬───────┘
       │    ┌───────────────┐   │
       └───►│   FastAPI     │◄──┘
            └───────┬───────┘
            ┌───────▼───────┐
            │  ASI:One API  │
            │  api.asi1.ai  │
            └───────┬───────┘
            ┌───────▼───────┐
            │  Agents on    │
            │  Agentverse   │
            └───────────────┘
```

## Agent Architecture — 7 unique agents, 12 instances

Every agent earns its seat. If it can be a function call, it's a function call.

```
ASI1OrchestratorAgent (1)
├── EventDiscoveryAgent (1) — searches events via API + Browser Use, scores venues
├── FriendProfileAgent (x5) — per-person private state, independent voting
│   Factory pattern: same code, different JSON configs
│   Deterministic scoring + LLM reasoning string
├── GroupConsensusAgent (1) — ranked-choice voting, vetoes, tie-breaking
├── CommitmentAgent (1) — Stripe auth holds, quorum state machine, ticket purchase
├── SettlementAgent (1) — refunds, dropout cascade, redistribution, resale
└── GroupHistoryAgent (1) — persistent flake tracking, organizer fairness
```

All agents are uAgents registered on Agentverse with mailbox=True and Chat Protocol.

## Friend Profile Schema

```json
{
    "name": "Alex",
    "likes": ["stand-up", "live-music"],
    "dislikes": ["improv"],
    "budget_target": 55,
    "budget_max": 70,
    "budget_strictness": "flexible",
    "available_times": ["sat-evening", "sat-night"],
    "max_transit_min": 30,
    "location": [40.73, -73.99],
    "dietary": [],
    "flake_score": 0.0,
    "events_organized": 3,
    "notes": ""
}
```

Demo personas pre-seeded in backend/profiles/:
- Alex: comedy snob, flexible budget ($55, max $70), 30 min transit
- Sarah: budget-strict ($35 max), sat night only, 20 min transit
- Mike: generous ($70), only after 8pm, 45 min transit
- Jordan: easygoing, likes everything, chronic flaker (flake_score 0.4) — THE DROPOUT
- Riley: transit-sensitive (15 min max), moderate budget

## Voting Logic (FriendProfileAgent)

Deterministic scoring for reliability. LLM call only for reasoning string.

Hard veto if: time_slot not in available_times, price > budget_max, transit > max_transit_min
Soft score: +3 category in likes, -5 category in dislikes, +2 price <= budget_target, +1 close venue, +(rating - 3.0)

## Commitment Logic

Flake history affects how CommitmentAgent handles each person:
- flake_score >= 0.5 → immediate_charge (pay now)
- flake_score >= 0.25 → non_refundable_hold
- else → refundable_hold (standard)

Quorum state machine: waiting → quorum_met → purchasing → purchased → cancelled

## Stripe Integration — Throughout the Lifecycle

Stripe IS the product. Auth holds as commitment is the key innovation.

| Stage | Stripe Component | API Call |
|---|---|---|
| Card setup | SetupIntent via SMS link (frontend team handles the page) | stripe.setup_intents.create() |
| RSVP "I'm in" | PaymentIntent with manual capture | stripe.payment_intents.create(capture_method="manual") |
| Quorum met | Capture holds | stripe.payment_intents.capture() |
| Dropout | Refund dropout + charge remaining extra | stripe.refunds.create() + new PaymentIntents |
| Group cancel (refundable) | Refund everyone | stripe.refunds.create() |
| Group cancel (non-refundable) | Resale links | stripe.payment_links.create() |
| Post-event split | Individual charges for Uber, dinner | stripe.payment_intents.create() per person |
| Receipt | Itemized invoice | stripe.invoices.create() |

## Fetch.ai Integration

- uAgents framework for all agents
- Agentverse registration for all 12 instances
- Agentverse mailbox for async communication
- Almanac for discovery
- Chat Protocol for ASI:One interface (mandatory)
- Payment Protocol for on-chain payment verification (cosmpy)

## ASI:One API

Endpoint: POST https://api.asi1.ai/v1/chat/completions
Auth: Bearer token (ASI1_API_KEY)
Session: x-session-id header (UUID per conversation, maps to phone number)
Model: "asi1" (automatically discovers agents on Agentverse)
Long-running tasks: poll with "Any update?" every 5 seconds

## Browser Use

EventDiscoveryAgent uses Browser Use (Python lib) to:
- Search Ticketmaster.com / Eventbrite.com for real events
- Extract pricing from ticketing pages
- Purchase tickets on mock portal (localhost) during demo
- Fallback: pre-cached results if browser is slow

## Event Lifecycle Flows

Happy path: discovery → voting → commitment → quorum → purchase → event → history
Dropout: refund dropout → recalculate split → charge remaining the difference
Group cancel (refundable): poll → refund all
Group cancel (non-refundable): poll → resell via Payment Links or eat cost
Budget conflict: flag → someone covers difference → adjusted splits
Quorum failure: release all holds, cancel

## Tech Stack (Backend Only — frontend is handled by another team member)

- Python 3.11+
- FastAPI + uvicorn (API server)
- Fetch.ai uAgents (agent framework)
- Claude Sonnet 4.6 via Anthropic SDK + LangChain Anthropic (LLM)
- Stripe (payments)
- Twilio (SMS)
- ASI:One API at api.asi1.ai (AI orchestration)
- Browser Use (browser automation)
- cosmpy (Fetch.ai on-chain)
- Pydantic (models)
- In-memory dicts (state — no database for hackathon)

## File Structure

```
backend/
├── agents/
│   ├── orchestrator.py           # ASI1OrchestratorAgent
│   ├── discovery.py              # EventDiscoveryAgent
│   ├── friend_profile.py         # FriendProfileAgent factory (x5)
│   ├── consensus.py              # GroupConsensusAgent
│   ├── commitment.py             # CommitmentAgent
│   ├── settlement.py             # SettlementAgent
│   └── history.py                # GroupHistoryAgent
├── api/
│   ├── routes/
│   │   ├── groups.py             # POST /api/groups, add members, start
│   │   ├── profiles.py           # GET/PUT profiles
│   │   └── status.py             # GET status for dashboard
│   └── webhooks/
│       ├── stripe_webhook.py     # POST /webhooks/stripe
│       └── twilio_webhook.py     # POST /webhooks/twilio (incoming SMS)
├── messaging/
│   ├── twilio_service.py         # Send/receive SMS
│   ├── asi_one.py                # ASI:One API client (chat completions + sessions)
│   └── conversation.py           # Phone → session mapping, message routing
├── models/
│   ├── messages.py               # uAgent message schemas (VoteRequest, Vote, etc.)
│   ├── profiles.py               # FriendProfile pydantic model
│   ├── events.py                 # EventOption models
│   └── payments.py               # PaymentState, CommitmentStatus
├── services/
│   ├── stripe_service.py         # All Stripe API calls
│   ├── browser_service.py        # Browser Use tasks
│   ├── llm_service.py            # Anthropic SDK calls
│   └── fetch_protocol.py         # Fetch.ai Payment Protocol / cosmpy
├── profiles/                     # Pre-seeded demo profiles
│   ├── alex.json
│   ├── sarah.json
│   ├── mike.json
│   ├── jordan.json
│   └── riley.json
├── main.py                       # FastAPI app + agent startup
├── requirements.txt
└── .env                          # API keys

mock_portal/
└── index.html                    # Mock ticketing page for Browser Use demo
```

**IMPORTANT: Do not create, modify, or delete any files in the app/ directory. The frontend is owned by another team member.**

## Environment Variables

```
ANTHROPIC_API_KEY=
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_PHONE_NUMBER=
ASI1_API_KEY=
FETCH_WALLET_SEED=
```

## Hackathon Context

Track: Fetch.ai Agentverse + ASI:One + Stripe
Competing against AgentPlace-tier projects (24 agents, autonomous negotiation, Payment Protocol)
Our differentiators: Stripe depth (auth holds as commitment), SMS-first UX, Browser Use for visible agent actions, dropout cascade demo moment
Judges use ASI:One chat UI for demo. Twilio SMS is the product experience shown alongside.

## Code Guidelines

- All agents use uagents framework with Chat Protocol from uagents_core.contrib.protocols.chat
- ChatMessage, ChatAcknowledgement, TextContent, EndSessionContent for message types
- Each agent: mailbox=True, publish_agent_details=True
- Deterministic logic for correctness, LLM only for natural language generation
- Stripe in test mode — use test API keys and test card numbers
- In-memory state (dicts keyed by session/group ID) — no database
- Keep agent count at 7 unique (12 instances). Do not add agents that should be functions.
- Frontend (app/ directory) is fair game — polish the UI as needed.
- API routes in backend/api/routes/ expose JSON endpoints that the frontend consumes.
