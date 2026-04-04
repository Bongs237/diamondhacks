"""
Fetch.ai uAgents that delegate to browser-use (Browser Use Cloud by default).

Run from the `backend` directory (so `agents` is importable):

  cd backend
  .\\.venv\\Scripts\\activate
  set BROWSER_USE_API_KEY=...   # LLM + hosted browser — https://cloud.browser-use.com
  python -m agents.fetch_browser_agents

Local browser instead of cloud: set BROWSER_USE_CLOUD=0

------------------------------------------------------------------------------
Agentverse (mailbox) — so other agents can reach yours without your public IP
------------------------------------------------------------------------------

1. **Enable mailbox mode** when starting this process::

     set FETCH_MAILBOX=1

2. **Optional** custom Agentverse host (default is production Agentverse)::

     set FETCH_AGENTVERSE=https://agentverse.ai

3. **Run this bureau** and note the printed agent addresses (Almanac / logs).

4. **Connect to Agentverse** using the Local Agent Inspector (opened from the
   link uAgents prints, or your bureau URL — typically ``http://127.0.0.1:<port>/``).
   In the Inspector, use **Connect → Mailbox** and paste your **Agentverse user token**
   so Fetch can register the mailbox endpoint for your agent identity.

   Official guides:
   - https://uagents.fetch.ai/docs/agentverse/mailbox
   - https://uagents.fetch.ai/docs/agentverse/inspector

5. **Testnet wallet:** Almanac registration still uses the ledger; keep a small
   FET balance on **testnet** for the bureau wallet (derived from ``FETCH_BUREAU_SEED``
   if you set batch registration) or follow Fetch docs if you use a custom
   ``registration_policy``.

**Direct HTTP (no Agentverse mailbox):** omit ``FETCH_MAILBOX`` (or set ``0``).
Set ``FETCH_BUREAU_ENDPOINT`` to a reachable URL if other machines must call ``/submit``.
"""

from __future__ import annotations

import os
import traceback

from uagents import Agent, Bureau, Context, Model

from .browser_runner import run_activity_discovery, run_reservation_assist


class DiscoverRequest(Model):
    area: str
    latitude: float = 0.0
    longitude: float = 0.0
    when: str = "upcoming Saturday evening"
    interests_csv: str = ""
    budget_per_person: float = 0.0
    dietary_csv: str = ""
    max_transit_min: int = 0
    max_steps: int = 25


class DiscoverResponse(Model):
    ok: bool
    payload_json: str
    error: str = ""


class ReserveRequest(Model):
    area: str
    activity_type: str = "movie"
    title_hint: str = ""
    when: str = ""
    party_size: int = 2
    allow_payment: bool = False
    notes: str = ""
    max_steps: int = 30


class ReserveResponse(Model):
    ok: bool
    payload_json: str
    error: str = ""


def _split_csv(s: str) -> list[str]:
    return [p.strip() for p in s.split(",") if p.strip()]


def _env_flag(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def _agentverse_url() -> str | None:
    u = os.environ.get("FETCH_AGENTVERSE", "").strip()
    return u or None


def _network() -> str:
    n = os.environ.get("FETCH_NETWORK", "testnet").strip().lower()
    return n if n in ("mainnet", "testnet") else "testnet"


def build_agents() -> tuple[Agent, Agent]:
    """Construct agents so ``FETCH_*`` env is read at startup, not import time."""
    use_mailbox = _env_flag("FETCH_MAILBOX", default=False)
    agentverse = _agentverse_url()
    net = _network()
    port = int(os.environ.get("FETCH_BUREAU_PORT", "8100"))

    discovery_agent = Agent(
        name="plan_browser_discovery",
        seed=os.environ.get("FETCH_DISCOVERY_SEED", "plan browser discovery dev seed change me"),
        port=port,
        network=net,
        mailbox=use_mailbox,
        agentverse=agentverse,
        description="Searches the web for group activities (browser-use + Browser Use Cloud).",
    )

    reservation_agent = Agent(
        name="plan_browser_reservation",
        seed=os.environ.get("FETCH_RESERVATION_SEED", "plan browser reservation dev seed change me"),
        port=port,
        network=net,
        mailbox=use_mailbox,
        agentverse=agentverse,
        description="Assists with ticketing / reservations (browser-use + Browser Use Cloud).",
    )

    @discovery_agent.on_message(DiscoverRequest, replies=DiscoverResponse)
    async def on_discover(ctx: Context, sender: str, msg: DiscoverRequest) -> None:
        try:
            interests = _split_csv(msg.interests_csv)
            dietary = _split_csv(msg.dietary_csv)
            budget = msg.budget_per_person if msg.budget_per_person > 0 else None
            transit = msg.max_transit_min if msg.max_transit_min > 0 else None
            result = await run_activity_discovery(
                area=msg.area,
                latitude=msg.latitude,
                longitude=msg.longitude,
                when=msg.when,
                interests=interests,
                budget_per_person=budget,
                dietary=dietary,
                max_transit_min=transit,
                max_steps=msg.max_steps,
            )
            await ctx.send(
                sender,
                DiscoverResponse(ok=True, payload_json=result.model_dump_json(), error=""),
            )
        except Exception as e:
            await ctx.send(
                sender,
                DiscoverResponse(
                    ok=False,
                    payload_json="{}",
                    error=f"{type(e).__name__}: {e}\n{traceback.format_exc()}",
                ),
            )

    @reservation_agent.on_message(ReserveRequest, replies=ReserveResponse)
    async def on_reserve(ctx: Context, sender: str, msg: ReserveRequest) -> None:
        try:
            result = await run_reservation_assist(
                area=msg.area,
                activity_type=msg.activity_type,
                title_hint=msg.title_hint,
                when=msg.when,
                party_size=msg.party_size,
                allow_payment=msg.allow_payment,
                notes=msg.notes,
                max_steps=msg.max_steps,
            )
            await ctx.send(
                sender,
                ReserveResponse(ok=True, payload_json=result.model_dump_json(), error=""),
            )
        except Exception as e:
            await ctx.send(
                sender,
                ReserveResponse(
                    ok=False,
                    payload_json="{}",
                    error=f"{type(e).__name__}: {e}\n{traceback.format_exc()}",
                ),
            )

    return discovery_agent, reservation_agent


def main() -> None:
    discovery_agent, reservation_agent = build_agents()
    port = int(os.environ.get("FETCH_BUREAU_PORT", "8100"))
    endpoint = os.environ.get(
        "FETCH_BUREAU_ENDPOINT",
        f"http://127.0.0.1:{port}/submit",
    )
    use_mailbox = _env_flag("FETCH_MAILBOX", default=False)
    agentverse = _agentverse_url()
    net = _network()

    bureau = Bureau(
        agents=[discovery_agent, reservation_agent],
        port=port,
        endpoint=None if use_mailbox else [endpoint],
        agentverse=agentverse,
        network=net,
        seed=os.environ.get("FETCH_BUREAU_SEED"),
    )
    print("Bureau starting — discovery address:", discovery_agent.address)
    print("Bureau starting — reservation address:", reservation_agent.address)
    if use_mailbox:
        print("Mailbox mode: ON — connect via Local Agent Inspector (see module docstring).")
        print("Agentverse base:", agentverse or "default (agentverse.ai)")
    else:
        print("Mailbox mode: OFF — endpoint:", endpoint)
    bureau.run()


if __name__ == "__main__":
    main()
