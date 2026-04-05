"""
Browser-use runners: activity discovery (broad web search) and reservation assistance.

LLM: **Browser Use Cloud** via ``ChatBrowserUse``. Requires ``BROWSER_USE_API_KEY``.

Browser: **Browser Use Cloud** by default (``BrowserSession(use_cloud=True)``).
Set ``BROWSER_USE_CLOUD=0`` for a local browser; LLM still uses Browser Use Cloud.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass

from browser_use import Agent, BrowserSession, ChatBrowserUse

from .browser_schemas import ActivityDiscoveryResult, ReservationAttemptResult


@dataclass(frozen=True)
class MemberLocation:
    """A single group member's position and the farthest they are willing to travel."""

    lat: float
    lon: float
    radius_miles: float


def _llm() -> ChatBrowserUse:
    if not os.environ.get("BROWSER_USE_API_KEY"):
        raise RuntimeError(
            "BROWSER_USE_API_KEY is required for the Browser Use Cloud LLM. "
            "Get a key at https://cloud.browser-use.com"
        )
    model = os.environ.get("BROWSER_USE_LLM_MODEL", "bu-latest")
    return ChatBrowserUse(model=model)


def _browser_agent_kwargs() -> dict:
    """Return kwargs for Agent() controlling local vs Browser Use Cloud."""
    raw = os.environ.get("BROWSER_USE_CLOUD", "1").strip().lower()
    use_local = raw in ("0", "false", "no", "off", "local")
    if use_local:
        return {}
    if not os.environ.get("BROWSER_USE_API_KEY"):
        raise RuntimeError(
            "Browser Use Cloud is enabled (BROWSER_USE_CLOUD defaults to 1) but BROWSER_USE_API_KEY "
            "is not set. Add an API key from https://cloud.browser-use.com or set BROWSER_USE_CLOUD=0 "
            "to use a local browser."
        )
    return {"browser": BrowserSession(use_cloud=True)}


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Straight-line distance in miles between two WGS84 points."""
    R = 3958.8  # Earth radius in miles
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def _search_center(members: list[MemberLocation]) -> tuple[float, float]:
    """Approximate centre of all member circles — used only to seed the web search."""
    return (
        sum(m.lat for m in members) / len(members),
        sum(m.lon for m in members) / len(members),
    )


def _discovery_task(*, members: list[MemberLocation], when: str | None = None) -> str:
    from datetime import datetime, timezone  # local import to keep module-level imports clean

    lines = "\n".join(
        f"  - User {i + 1}: latitude {m.lat:.6f}, longitude {m.lon:.6f}, radius {m.radius_miles:.1f} miles"
        for i, m in enumerate(members)
    )
    c_lat, c_lon = _search_center(members)

    _now = datetime.now(timezone.utc)
    now_utc = f"{_now.strftime('%A %B')} {_now.day}, {_now.strftime('%Y %H:%M')} UTC"
    if when:
        time_section = f"""
**Time constraint**: the group wants to attend on/around **{when}**.
Current date/time for reference: {now_utc}
Interpret relative expressions (e.g. "saturday evening", "tomorrow afternoon", "this weekend") relative
to the current date/time above. Only include activities that are **open, running, or available**
during that window — exclude anything that is closed, sold out, or only offered on different days.
If an activity's schedule cannot be confirmed for that time, omit it.
Fill `starts_at_local_hint` with the specific date and local time this activity starts (or the
range of times it is available) during the requested window.
""".strip()
    else:
        time_section = f"""
Current date/time for reference: {now_utc}
Include any activities that are currently available or upcoming in the near future.
Fill `starts_at_local_hint` with the date and time the activity is next available when known.
""".strip()

    return f"""
You are gathering a **broad, diverse list** of real things to do (events, venues, shows, experiences)
so another system can rank them later. Do **not** optimize for specific tastes, budget, or diet—only
geographic and temporal feasibility for the whole group.

Group member locations with individual travel radii (WGS84 decimal degrees):
{lines}

Constraint — **intersection rule**: only include an activity if it falls within **each member's own
radius** (straight-line miles from that member's location). An activity that is reachable by some
members but outside even one member's radius must be excluded.

Search anchor (approximate centre of the group's positions): latitude {c_lat:.5f}, longitude {c_lon:.5f}.
Use this as the starting point for map searches, but verify each candidate against every member's
individual radius before including it.

{time_section}

Search the open web (search engines, maps, local listings, ticketing sites) for **many** varied
options in the region that satisfy the constraints. Prefer primary sources (official venue or ticket
pages) over scraper blogs.

**Blocked pages / CAPTCHAs**: if any page presents a CAPTCHA, robot check, login wall, or any
challenge that requires human interaction, **immediately navigate away** — do not attempt to solve
it. Note the blocked URL in search_notes and move on to the next source. There are always
alternative listing sites and search results to try.

**Partial results are fine**: if you exhaust `max_steps` or run into repeated blocks before
finding a full list, output whatever activities you have gathered so far rather than stopping
with an empty result.

For **every** activity you include:
- Compute `distances_to_members`: the straight-line distance in miles from each member's coordinates
  to the venue coordinates, using the Haversine formula. Include one entry per member (member_index
  is 1-based).
- Fill `estimated_cost_per_person_usd` with a realistic **total spend** per person — this means
  tickets or entry fees PLUS typical consumption at the venue (drinks, food, games, etc.). A bar
  with no cover still costs ~$25–40 per person in drinks; a restaurant costs a typical meal; a
  free public park where people spend nothing is 0.0. 0.0 is ONLY for activities where a person
  would genuinely spend nothing. For walk-in venues, check the venue's menu, Yelp, Google, or
  similar to estimate a realistic per-person total. Only leave null if an estimate is genuinely
  impossible after actively searching.
- Fill `booking_url` with the direct ticket-purchase or reservation link for **any** activity that
  involves tickets, cover charges, reservations, or entry fees. Check the venue's official site and
  major platforms (Ticketmaster, Eventbrite, OpenTable, etc.). Only omit if the activity is
  walk-in and completely free with no booking needed.

When finished, use the structured output action with JSON matching ActivityDiscoveryResult:
include search_notes and a list of activities with accurate booking_url when available.
Do not invent events; if uncertain, say so in the description and omit booking_url.
""".strip()


def _reservation_task(
    *,
    area: str,
    activity_type: str,
    title_hint: str,
    when: str,
    party_size: int,
    allow_payment: bool,
    notes: str,
) -> str:
    pay = (
        "You MAY proceed through payment only if the user explicitly allowed payment and the site "
        "uses a safe flow; never type raw card numbers into chat. Prefer stopping at checkout and "
        "returning the URL."
        if allow_payment
        else "Do NOT complete payment. Stop before submitting card details. Return checkout or cart URL."
    )
    return f"""
You are automating a reservation or ticket purchase flow for a group.

Area: {area}
Activity type: {activity_type}
Target show or venue (hint): {title_hint}
When: {when}
Party size: {party_size}
Extra notes: {notes or "none"}

Open relevant official ticketing or booking sites, find matching showtimes or slots, and advance as far
as is safe. {pay}

If login, CAPTCHA, or SMS verification blocks automation, set status to blocked and explain.
When finished, use the structured output action with JSON matching ReservationAttemptResult.
""".strip()


async def run_activity_discovery(
    *,
    members: list[MemberLocation],
    when: str | None = None,
    max_steps: int = 30,
    sensitive_data: dict[str, str | dict[str, str]] | None = None,
) -> ActivityDiscoveryResult:
    if not members:
        raise ValueError("members must contain at least one MemberLocation")
    if any(m.radius_miles <= 0 for m in members):
        raise ValueError("every MemberLocation.radius_miles must be > 0")

    agent = Agent(
        task=_discovery_task(members=members, when=when),
        llm=_llm(),
        output_model_schema=ActivityDiscoveryResult,
        sensitive_data=sensitive_data,
        extend_system_message=(
            "If you encounter a CAPTCHA, robot/bot check, login wall, or any page challenge that "
            "requires human input, navigate away immediately — never attempt to solve or wait on it. "
            "Note the blocked URL in search_notes and continue with a different source. "
            "If you are running low on steps, stop searching and output the activities you have "
            "already found rather than returning an empty result."
        ),
        **_browser_agent_kwargs(),
    )
    history = await agent.run(max_steps=max_steps)
    parsed = history.structured_output
    if parsed is not None:
        return parsed
    raw = history.final_result()
    if raw:
        return ActivityDiscoveryResult.model_validate_json(raw)
    return ActivityDiscoveryResult(
        search_notes="Agent finished without structured output; check logs.",
        activities=[],
    )


async def run_reservation_assist(
    *,
    area: str,
    activity_type: str,
    title_hint: str,
    when: str,
    party_size: int = 2,
    allow_payment: bool = False,
    notes: str = "",
    max_steps: int = 35,
    sensitive_data: dict[str, str | dict[str, str]] | None = None,
) -> ReservationAttemptResult:
    agent = Agent(
        task=_reservation_task(
            area=area,
            activity_type=activity_type,
            title_hint=title_hint,
            when=when,
            party_size=party_size,
            allow_payment=allow_payment,
            notes=notes,
        ),
        llm=_llm(),
        output_model_schema=ReservationAttemptResult,
        sensitive_data=sensitive_data,
        extend_system_message=(
            "Never expose secrets in extracted content. Use sensitive_data placeholders for logins when configured. "
            "Prefer completing seat selection and stopping at payment unless allow_payment is true."
        ),
        **_browser_agent_kwargs(),
    )
    history = await agent.run(max_steps=max_steps)
    parsed = history.structured_output
    if parsed is not None:
        return parsed
    raw = history.final_result()
    if raw:
        return ReservationAttemptResult.model_validate_json(raw)
    return ReservationAttemptResult(
        status="blocked",
        detail="Agent finished without structured output; check logs.",
        human_required_reason="retry_or_inspect_browser_session",
    )
