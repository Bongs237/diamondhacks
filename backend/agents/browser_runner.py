"""
Browser-use runners: web discovery and reservation assistance.

LLM: **Browser Use Cloud** via ``ChatBrowserUse`` (same account as hosted browsers).
Requires BROWSER_USE_API_KEY. Optional BROWSER_USE_LLM_MODEL (default ``bu-latest``;
other examples: ``bu-2-0``, or models under ``browser-use/...`` per browser-use docs).

Browser: by default uses **Browser Use Cloud** (hosted browsers, CDP over the network).
Set BROWSER_USE_API_KEY from https://cloud.browser-use.com (see also browser-use CLI auth).
To force a **local** browser instead, set BROWSER_USE_CLOUD=0. The LLM still calls Browser Use
Cloud and needs BROWSER_USE_API_KEY.
"""

from __future__ import annotations

import os

from browser_use import Agent, BrowserSession, ChatBrowserUse

from .browser_schemas import ActivityDiscoveryResult, ReservationAttemptResult


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


def _discovery_task(
    *,
    area: str,
    latitude: float,
    longitude: float,
    when: str,
    interests: list[str],
    budget_per_person: float | None,
    dietary: list[str],
    max_transit_min: int | None,
) -> str:
    budget = f"around ${budget_per_person:.0f} per person" if budget_per_person else "flexible budget"
    dietary_s = ", ".join(dietary) if dietary else "none specified"
    interests_s = ", ".join(interests) if interests else "general group fun"
    transit = (
        f"Prefer options within ~{max_transit_min} minutes travel from the area."
        if max_transit_min
        else "Consider reasonable travel from the area."
    )
    return f"""
You are helping a friend group plan an outing.

Location context: {area} (coordinates {latitude}, {longitude} — use for maps/local search context).
When: {when}.
Interests: {interests_s}.
Budget: {budget}.
Dietary / constraints: {dietary_s}.
{transit}

Search the open web (search engine, local listings, venues, ticketing sites) for real, bookable or
reservable ideas. Prefer primary sources (official venue or ticket pages) over scraper blogs.

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
    area: str,
    latitude: float,
    longitude: float,
    when: str,
    interests: list[str] | None = None,
    budget_per_person: float | None = None,
    dietary: list[str] | None = None,
    max_transit_min: int | None = None,
    max_steps: int = 30,
    sensitive_data: dict[str, str | dict[str, str]] | None = None,
) -> ActivityDiscoveryResult:
    agent = Agent(
        task=_discovery_task(
            area=area,
            latitude=latitude,
            longitude=longitude,
            when=when,
            interests=interests or [],
            budget_per_person=budget_per_person,
            dietary=dietary or [],
            max_transit_min=max_transit_min,
        ),
        llm=_llm(),
        output_model_schema=ActivityDiscoveryResult,
        sensitive_data=sensitive_data,
        extend_system_message=(
            "Respect robots.txt and site terms; do not brute-force or bypass CAPTCHAs. "
            "If a page is inaccessible, note it in search_notes and continue with other sources."
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
