"""
EventPulse Booking Agent — uAgent with Chat Protocol for Agentverse.

Uses Browser Use Cloud to navigate to a ticketing/reservation page, select the
correct date/time and number of seats, extract the total cost, and optionally
complete payment.

Run (from ``backend``)::

    set BOOKING_AGENT_SEED=your-stable-seed-phrase
    set BROWSER_USE_API_KEY=...
    python -m agents.booking_uagent

**Input payload** (``ChatMessage`` text = JSON)::

    {
      "booking_url": "https://www.ticketmaster.com/...",
      "event_title": "The Comedy Store - Saturday Night",
      "when": "Saturday April 5 at 8pm",
      "party_size": 4,
      "allow_payment": false,
      "notes": "prefer seats together",
      "max_steps": 40
    }

``allow_payment`` *(optional, default false)*: set to ``true`` to let the agent
submit payment using credentials supplied in sensitive_data. When false the
agent stops at the checkout page and returns the cart URL + total cost.

``notes`` *(optional)*: any extra free-text instructions forwarded to the browser
agent (e.g. preferred section, accessibility requirements).

``max_steps`` *(optional, default 40)*: browser-use step budget.

**Reply JSON**::

    {
      "ok": true,
      "result": {
        "status": "checkout_ready",          // confirmed | checkout_ready | blocked | failed
        "detail": "...",
        "total_cost_usd": 142.50,
        "cost_per_person_usd": 35.63,
        "confirmation_number": null,         // populated when status == confirmed
        "deep_link_or_cart_url": "https://...",
        "human_required_reason": "payment"
      }
    }

    // or on error:
    { "ok": false, "error": "missing_booking_url", "hint": "..." }
"""

from __future__ import annotations

import json
import os
import traceback
from datetime import datetime, timezone
from uuid import uuid4

from dotenv import load_dotenv
from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    EndSessionContent,
    TextContent,
    chat_protocol_spec,
)

from .browser_runner import run_event_booking

load_dotenv()


def _env_flag(name: str, default: bool = True) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


async def _book_from_json(data: dict, ctx: Context = None, sender: str = None) -> dict:
    """Validate the payload and run the booking browser agent."""
    action = data.get("action")
    if action is not None and action != "book":
        return {"ok": False, "error": "unknown_action", "hint": 'omit action or use "book"'}

    booking_url = data.get("booking_url", "").strip()
    if not booking_url:
        return {
            "ok": False,
            "error": "missing_booking_url",
            "hint": 'Provide "booking_url": "https://..." pointing to the event ticketing page.',
        }

    event_title = data.get("event_title", "").strip()
    if not event_title:
        return {
            "ok": False,
            "error": "missing_event_title",
            "hint": 'Provide "event_title": "..." with the name of the event.',
        }

    when = data.get("when", "").strip()
    if not when:
        return {
            "ok": False,
            "error": "missing_when",
            "hint": (
                'Provide "when": "..." with the desired date/time, e.g. '
                '"Saturday April 5 at 8pm" or "2026-04-05T20:00".'
            ),
        }

    party_size = data.get("party_size", 2)
    try:
        party_size = int(party_size)
        if party_size < 1:
            raise ValueError
    except (TypeError, ValueError):
        return {
            "ok": False,
            "error": "invalid_party_size",
            "hint": '"party_size" must be a positive integer.',
        }

    allow_payment: bool = bool(data.get("allow_payment", False))
    notes: str = str(data.get("notes", ""))
    max_steps: int = int(data.get("max_steps") or 40)

    live_url_holder = {}

    async def capture_live_url_async(url):
        live_url_holder["url"] = url
        # Send live URL immediately so the orchestrator can forward it to ASI:One
        if ctx and sender and url:
            await ctx.send(
                sender,
                ChatMessage(
                    timestamp=datetime.now(timezone.utc),
                    msg_id=uuid4(),
                    content=[TextContent(type="text", text=json.dumps({"live_url": url}))],
                ),
            )

    def capture_live_url(url):
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(capture_live_url_async(url))
        except RuntimeError:
            live_url_holder["url"] = url

    result = await run_event_booking(
        booking_url=booking_url,
        event_title=event_title,
        when=when,
        party_size=party_size,
        allow_payment=allow_payment,
        notes=notes,
        max_steps=max_steps,
        on_live_url=capture_live_url,
    )
    response = {
        "ok": True,
        "result": json.loads(result.model_dump_json()),
        "live_url": getattr(result, "_live_url", None) or live_url_holder.get("url"),
        "session_id": getattr(result, "_session_id", None),
    }
    return response


# ---------------------------------------------------------------------------
# Chat Protocol
# ---------------------------------------------------------------------------

protocol = Protocol(spec=chat_protocol_spec)


@protocol.on_message(ChatMessage)
async def handle_chat_message(ctx: Context, sender: str, msg: ChatMessage) -> None:
    await ctx.send(
        sender,
        ChatAcknowledgement(
            timestamp=datetime.now(timezone.utc),
            acknowledged_msg_id=msg.msg_id,
        ),
    )

    text = msg.text().strip()
    if not text:
        await _send_result(ctx, sender, {"ok": False, "error": "empty_message"})
        return

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        await _send_result(
            ctx,
            sender,
            {
                "ok": False,
                "error": "expected_json_text",
                "hint": (
                    '{"booking_url":"https://...","event_title":"Show Name",'
                    '"when":"Saturday April 5 at 8pm","party_size":4}'
                ),
            },
        )
        return

    try:
        body = await _book_from_json(data if isinstance(data, dict) else {}, ctx=ctx, sender=sender)
    except Exception as e:
        ctx.logger.exception("event booking failed")
        body = {
            "ok": False,
            "error": f"{type(e).__name__}: {e}",
            "traceback": traceback.format_exc(),
        }

    await _send_result(ctx, sender, body)


async def _send_result(ctx: Context, sender: str, body: dict) -> None:
    await ctx.send(
        sender,
        ChatMessage(
            timestamp=datetime.now(timezone.utc),
            msg_id=uuid4(),
            content=[
                TextContent(type="text", text=json.dumps(body, ensure_ascii=False)),
                EndSessionContent(type="end-session"),
            ],
        ),
    )


@protocol.on_message(ChatAcknowledgement)
async def handle_ack(_ctx: Context, _sender: str, _msg: ChatAcknowledgement) -> None:
    pass


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    seed = os.environ.get("BOOKING_AGENT_SEED") or os.environ.get("UAGENT_SEED")
    if not seed:
        raise RuntimeError(
            "Set BOOKING_AGENT_SEED (or UAGENT_SEED) to a stable seed phrase before starting."
        )

    use_mailbox = _env_flag("BOOKING_AGENT_MAILBOX", default=True)
    port = int(os.environ.get("BOOKING_AGENT_PORT", "8003"))

    agent = Agent(
        name=os.environ.get("BOOKING_AGENT_NAME", "event_booking"),
        seed=seed,
        port=port,
        mailbox=use_mailbox,
        publish_agent_details=True,
    )
    agent.include(protocol, publish_manifest=True)
    agent.run()


if __name__ == "__main__":
    main()
