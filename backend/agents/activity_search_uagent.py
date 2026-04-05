"""
Activity search uAgent — **Agent Chat Protocol** + **Browser Use Cloud**.

Uses the uAgents framework for Agentverse / ASI:One:
https://docs.agentverse.ai/documentation/launch-agents/external-agents/u-agents

Chat protocol:
https://uagents.fetch.ai/docs/examples/asi-1

Run (from ``backend``)::

    set ACTIVITY_SEARCH_AGENT_SEED=your-stable-seed-phrase
    set BROWSER_USE_API_KEY=...
    python -m agents.activity_search_uagent

**Orchestrator payload** (``ChatMessage`` text = JSON)::

    {
      "locations": [
        [40.73, -73.99, 5],
        [40.72, -73.95, 8]
      ],
      "when": "saturday evening",
      "max_steps": 25
    }

``locations``: each entry is ``[latitude, longitude, radius_miles]`` or
``{"latitude": ..., "longitude": ..., "radius_miles": ...}``.
Each member has their own radius; an activity is only returned if it falls within
**every** member's individual radius (intersection rule).

``when`` *(optional)*: a date/time expression describing when the group wants to
go out. Accepts human-readable phrases such as ``"saturday evening"``,
``"tomorrow afternoon"``, ``"this weekend"``, or ISO-8601 strings like
``"2026-04-05T19:00"``. Only events/venues available during that window are
returned. Omit to get any currently available or near-future activities.

Optional ``max_steps`` for the browser-use loop (default 25).

Reply: JSON with ``ok``, ``result`` (``ActivityDiscoveryResult``), or ``error``.
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

from .browser_runner import MemberLocation, run_activity_discovery

load_dotenv()


def _env_flag(name: str, default: bool = True) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def _parse_members(raw: object) -> list[MemberLocation]:
    """Parse a list of per-member location+radius entries into MemberLocation objects.

    Accepted formats per entry:
      [lat, lng, radius_miles]
      {"latitude": ..., "longitude": ..., "radius_miles": ...}
      (aliases: lat/lng/lon, radius/max_radius_miles)
    """
    if not isinstance(raw, list) or not raw:
        return []
    out: list[MemberLocation] = []
    for item in raw:
        if isinstance(item, (list, tuple)) and len(item) >= 3:
            out.append(MemberLocation(float(item[0]), float(item[1]), float(item[2])))
        elif isinstance(item, dict):
            la = item.get("latitude", item.get("lat"))
            lo = item.get("longitude", item.get("lng", item.get("lon")))
            r = item.get("radius_miles", item.get("radius", item.get("max_radius_miles")))
            if la is not None and lo is not None and r is not None:
                out.append(MemberLocation(float(la), float(lo), float(r)))
    return out


async def _discover_from_json(data: dict) -> dict:
    action = data.get("action")
    if action is not None and action != "discover":
        return {"ok": False, "error": "unknown_action", "hint": 'omit action or use "discover"'}

    members = _parse_members(data.get("locations"))
    if not members:
        return {
            "ok": False,
            "error": "missing_locations",
            "hint": (
                'Provide "locations": [[lat, lng, radius_miles], ...] or '
                '[{"latitude":..., "longitude":..., "radius_miles":...}, ...]'
            ),
        }
    if any(m.radius_miles <= 0 for m in members):
        return {
            "ok": False,
            "error": "invalid_radius_miles",
            "hint": "Every entry's radius_miles must be > 0.",
        }

    when = data.get("when")
    if when is not None and not isinstance(when, str):
        return {
            "ok": False,
            "error": "invalid_when",
            "hint": (
                '"when" must be a string — e.g. "saturday evening", "tomorrow afternoon", '
                '"this weekend", or an ISO-8601 datetime like "2026-04-05T19:00".'
            ),
        }

    result = await run_activity_discovery(
        members=members,
        when=when or None,
        max_steps=int(data.get("max_steps") or 25),
    )
    return {
        "ok": True,
        "result": json.loads(result.model_dump_json()),
    }


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
        body = {"ok": False, "error": "empty_message"}
        await _send_result(ctx, sender, body)
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
                "hint": '{"locations":[[40.73,-73.99,5],[40.72,-73.95,8]],"when":"saturday evening"}',
            },
        )
        return

    try:
        body = await _discover_from_json(data if isinstance(data, dict) else {})
    except Exception as e:
        ctx.logger.exception("activity discovery failed")
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


def main() -> None:
    seed = os.environ.get("ACTIVITY_SEARCH_AGENT_SEED") or os.environ.get("UAGENT_SEED")
    if not seed:
        raise RuntimeError(
            "Set ACTIVITY_SEARCH_AGENT_SEED (or UAGENT_SEED) to a stable seed phrase before starting."
        )

    use_mailbox = _env_flag("ACTIVITY_SEARCH_MAILBOX", default=True)
    port = int(os.environ.get("ACTIVITY_SEARCH_AGENT_PORT", "8001"))

    agent = Agent(
        name=os.environ.get("ACTIVITY_SEARCH_AGENT_NAME", "activity_search"),
        seed=seed,
        port=port,
        mailbox=use_mailbox,
        publish_agent_details=True,
    )
    agent.include(protocol, publish_manifest=True)
    agent.run()


if __name__ == "__main__":
    main()
