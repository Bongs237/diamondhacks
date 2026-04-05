"""
Browser-use runners: activity discovery, reservation assistance, and event booking.

Uses the **Browser Use Cloud SDK** (``browser-use-sdk``) which runs tasks on a
managed hardened Chromium fork with stealth anti-fingerprinting, automatic CAPTCHA
solving, and residential proxies — all enabled by default.

Requires ``BROWSER_USE_API_KEY`` (starts with ``bu_``).
"""

from __future__ import annotations

import json
import logging
import math
import os
from collections.abc import Callable
from dataclasses import dataclass

from browser_use_sdk.v3 import AsyncBrowserUse

from .browser_schemas import ActivityDiscoveryResult, BookingResult, ReservationAttemptResult

logger = logging.getLogger(__name__)


def _client() -> AsyncBrowserUse:
    if not os.environ.get("BROWSER_USE_API_KEY"):
        raise RuntimeError(
            "BROWSER_USE_API_KEY is not set. "
            "Get a key at https://cloud.browser-use.com"
        )
    return AsyncBrowserUse()


@dataclass(frozen=True)
class MemberLocation:
    """A single group member's position and the farthest they are willing to travel."""

    lat: float
    lon: float
    radius_miles: float


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


# ---------------------------------------------------------------------------
# Activity Discovery
# ---------------------------------------------------------------------------

def _discovery_task(*, members: list[MemberLocation], when: str | None = None) -> str:
    from datetime import datetime, timezone

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

Search the open web (search engines, maps, local listings, ticketing sites) for **at least 20**
varied options in the region that satisfy the constraints. Use multiple sources and search queries
to reach 20 results — try different categories (events, venues, dining, outdoors, arts, sports,
nightlife) and different listing sites to maximise variety. Prefer primary sources (official venue
or ticket pages) over scraper blogs.

If a page is blocked (CAPTCHA, login wall), skip it and try a different source — there are always
alternative listing sites.

**Partial results are fine**: if you run into repeated blocks before finding a full list, output
whatever activities you have gathered so far rather than stopping with an empty result.

For **every** activity you include:
- Compute `distances_to_members`: the straight-line distance in miles from each member's coordinates
  to the venue coordinates, using the Haversine formula. Include one entry per member (member_index
  is 1-based).
- Fill `estimated_cost_per_person_usd` with ONLY the ticket price, entry fee, or cover charge per
  person. Do NOT add estimated food, drinks, or other consumption costs. A movie ticket is ~$15,
  not $30. A free park is 0.0. A restaurant entry is 0.0 (food cost is the person's choice).
  Only include what someone MUST pay to attend. Leave null if unknown.
- Fill `booking_url` with the direct ticket-purchase or reservation link for **any** activity that
  involves tickets, cover charges, reservations, or entry fees. Check the venue's official site and
  major platforms (Ticketmaster, Eventbrite, OpenTable, etc.). Only omit if the activity is
  walk-in and completely free with no booking needed.

**Verification — CRITICAL**:
- ONLY include events/activities you have CONFIRMED exist by visiting an official source (venue
  website, ticketing platform, or verified event listing). Do NOT guess or assume an event exists.
- For movies: you MUST verify the specific film is actually showing at that theater on that date
  by checking the theater's showtimes page (AMC, Fandango, etc.). Do NOT list a movie unless you
  see it in the actual showtimes for that date.
- For concerts/shows: verify the performer is listed on the venue's calendar for that specific date.
- For restaurants/bars: verify they are open on the requested day by checking their hours page.
- If you cannot confirm an event is real, DO NOT include it. Fewer verified results are better
  than many unverified ones.

**Specificity**: every title must be specific enough to book. Do NOT return generic titles like
"Movie at AMC" or "Concert at Venue". Instead use the actual event name, e.g. "Project Hail Mary
at AMC La Jolla 12 (4:00 PM)" or "Hot 8 Brass Band at Belly Up Tavern". For movies, include the
film title and showtime. For restaurants, include the cuisine type.

Return JSON matching the ActivityDiscoveryResult schema:
include search_notes and a list of activities with accurate booking_url when available.
Do not invent events. If you are unsure whether something is real, leave it out.
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

    client = _client()
    result = await client.run(
        _discovery_task(members=members, when=when),
        output_schema=ActivityDiscoveryResult,
        model="gemini-3-flash",
    )
    if result.output is not None:
        if isinstance(result.output, ActivityDiscoveryResult):
            return result.output
        return ActivityDiscoveryResult.model_validate(result.output)
    return ActivityDiscoveryResult(
        search_notes="Agent finished without structured output; check logs.",
        activities=[],
    )


# ---------------------------------------------------------------------------
# Reservation Assist
# ---------------------------------------------------------------------------

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

If a hard login wall or SMS verification blocks automation, set status to blocked and explain.
Return JSON matching the ReservationAttemptResult schema.
""".strip()


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
    client = _client()
    result = await client.run(
        _reservation_task(
            area=area,
            activity_type=activity_type,
            title_hint=title_hint,
            when=when,
            party_size=party_size,
            allow_payment=allow_payment,
            notes=notes,
        ),
        output_schema=ReservationAttemptResult,
    )
    if result.output is not None:
        if isinstance(result.output, ReservationAttemptResult):
            return result.output
        return ReservationAttemptResult.model_validate(result.output)
    return ReservationAttemptResult(
        status="blocked",
        detail="Agent finished without structured output; check logs.",
        human_required_reason="retry_or_inspect_browser_session",
    )


# ---------------------------------------------------------------------------
# Event Booking
# ---------------------------------------------------------------------------

def _booking_task(
    *,
    booking_url: str,
    event_title: str,
    when: str,
    party_size: int,
    allow_payment: bool,
    notes: str,
) -> str:
    pay_instruction = (
        "You MAY complete payment if the user explicitly allowed it and the flow is secure. "
        "Never type raw card numbers into a chat input. After payment succeeds, record the "
        "confirmation number from the confirmation page."
        if allow_payment
        else "Do NOT submit payment. Stop at the checkout/cart page and record the total cost "
        "shown there. Return the checkout URL so a human can complete payment."
    )
    return f"""
You are completing a ticket or reservation booking for a group.

Event: {event_title}
Starting URL: {booking_url}
When: {when}
Party size (number of tickets): {party_size}
Extra notes: {notes or "none"}

Steps:
1. Navigate to the starting URL.
2. Select the date/time that matches "{when}". If multiple slots are available, pick the closest match.
3. Choose {party_size} ticket(s) / seat(s).
4. Proceed through the booking flow as far as is safe.
5. Before or at the checkout page, extract the **total cost** shown (all tickets + fees + taxes combined).
   Also compute cost_per_person_usd = total / {party_size}.
6. {pay_instruction}

**CAPTCHAs and bot challenges**: the browser has built-in stealth and CAPTCHA-solving capabilities.
If you land on a Cloudflare, hCaptcha, reCAPTCHA, or similar challenge page, wait a few seconds
and retry — the browser will handle it automatically. Only set status to "blocked" if a hard
login/SMS wall requires human credentials.

**Alternative routes**: if the main URL is consistently blocked, try navigating to the event via a
search engine result or an alternative ticketing platform (e.g. StubHub, SeatGeek, Vivid Seats).

**Partial progress is fine**: if you cannot complete the booking, return whatever you reached
(checkout URL, total cost if visible, reason for stopping).

Return JSON matching the BookingResult schema.
Populate total_cost_usd and cost_per_person_usd whenever those numbers are visible on screen.
""".strip()


async def run_event_booking(
    *,
    booking_url: str,
    event_title: str,
    when: str,
    party_size: int = 2,
    allow_payment: bool = False,
    notes: str = "",
    max_steps: int = 40,
    sensitive_data: dict[str, str | dict[str, str]] | None = None,
    on_live_url: Callable[[str], None] | None = None,
) -> BookingResult:
    """Navigate to *booking_url*, select *party_size* tickets for *when*, and return cost + status.

    Uses Browser Use Cloud SDK — runs on a hardened Chromium fork with stealth
    anti-fingerprinting, CAPTCHA solving, and residential proxies.

    Args:
        booking_url:   Direct ticket/reservation URL for the event.
        event_title:   Human-readable event name (used only for the task prompt).
        when:          Date/time expression, e.g. "Saturday April 5 at 8pm".
        party_size:    Number of tickets to select.
        allow_payment: If True the agent may submit payment; otherwise stops at checkout.
        notes:         Any extra instructions forwarded to the browser agent.
        max_steps:     Unused (Cloud SDK manages step budget internally). Kept for API compat.
        sensitive_data: Unused (Cloud SDK handles secrets via profiles). Kept for API compat.
        on_live_url:   Optional callback called with the live browser preview URL immediately
                       after the session is created. Use this to watch the agent in real time.

    Returns:
        BookingResult with status, total_cost_usd, cost_per_person_usd, and optional
        confirmation_number / deep_link_or_cart_url.
    """
    client = _client()

    session = await client.sessions.create()
    if on_live_url:
        on_live_url(session.live_url)

    result = await client.run(
        _booking_task(
            booking_url=booking_url,
            event_title=event_title,
            when=when,
            party_size=party_size,
            allow_payment=allow_payment,
            notes=notes,
        ),
        output_schema=BookingResult,
        session_id=session.id,
    )

    if result.output is not None:
        output = result.output if isinstance(result.output, BookingResult) else BookingResult.model_validate(result.output)
    else:
        output = BookingResult(
            status="checkout_ready",
            detail="Agent finished navigating. Browser session is still open for you to complete checkout.",
            human_required_reason="payment",
        )

    # Keep session alive if user needs to take over (checkout/blocked)
    # Stop it for confirmed/failed since no user action needed
    if output.status in ("confirmed", "failed"):
        await client.sessions.stop(session.id)

    # Attach session ID so callers can stop it later
    output._session_id = str(session.id)
    output._live_url = session.live_url
    return output


async def stop_booking_session(session_id: str):
    """Stop a booking browser session (called when user says 'done booking')."""
    try:
        client = _client()
        await client.sessions.stop(session_id)
        logger.info("Stopped booking session %s", session_id)
    except Exception as e:
        logger.warning("Failed to stop booking session %s: %s", session_id, e)
