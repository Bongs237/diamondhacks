"""Pydantic v2 schemas for browser-use structured outputs."""

from pydantic import BaseModel, Field


class MemberDistance(BaseModel):
    member_index: int = Field(description="1-based index matching the input member list")
    distance_miles: float = Field(description="Straight-line distance in miles from this member's location to the venue")


class ActivityIdea(BaseModel):
    title: str = Field(description="Short name of the activity or event")
    category: str = Field(
        description="e.g. movies, comedy, live_music, dining, museum, outdoors"
    )
    description: str = Field(description="One or two sentences; include timing if known")
    estimated_cost_per_person_usd: float | None = Field(
        default=None,
        description=(
            "Estimated total USD spend per person for a typical visit. "
            "This covers ALL expected costs: tickets, entry fees, cover charges, AND typical "
            "consumption spend at the venue (drinks, food, games, etc.). "
            "Examples: a bar with no cover but $8 drinks → estimate ~$25–40; a restaurant → estimate "
            "a typical meal cost; a free park with no spending expected → 0.0. "
            "0.0 is ONLY for activities where a person would realistically spend nothing at all. "
            "For walk-in venues, research typical prices on the venue's menu, Yelp, Google, or similar "
            "and return a realistic per-person estimate. "
            "Only return null if a reasonable estimate is genuinely impossible after searching."
        ),
    )
    booking_url: str | None = Field(
        default=None,
        description=(
            "Direct URL to purchase tickets, make a reservation, or complete booking. "
            "REQUIRED for any activity that involves tickets, cover charges, reservations, or entry fees — "
            "search the venue's official site, Ticketmaster, Eventbrite, OpenTable, or the relevant platform. "
            "Only omit (null) for activities that are genuinely walk-in and free with no booking needed."
        ),
    )
    venue_or_provider: str | None = Field(default=None, description="Venue, chain, or organizer")
    starts_at_local_hint: str | None = Field(
        default=None, description="Human-readable date/time in local timezone if known"
    )
    distances_to_members: list[MemberDistance] = Field(
        default_factory=list,
        description=(
            "Straight-line distance in miles from each group member to this venue. "
            "Include one entry per member using their 1-based index and the coordinates provided."
        ),
    )


class ActivityDiscoveryResult(BaseModel):
    search_notes: str = Field(
        description="Which kinds of sites or searches you used (no need for full URLs unless key)"
    )
    activities: list[ActivityIdea] = Field(
        default_factory=list,
        max_length=15,
        description="Ranked suggestions that fit the group's constraints",
    )


class ReservationAttemptResult(BaseModel):
    status: str = Field(
        description="One of: selection_ready, checkout_ready, blocked, completed"
    )
    detail: str = Field(description="What you accomplished and what is left for a human")
    deep_link_or_cart_url: str | None = Field(
        default=None, description="Checkout, cart, or seat-selection URL if reached"
    )
    human_required_reason: str | None = Field(
        default=None,
        description="If blocked or checkout_ready, why a human must continue (login, CAPTCHA, payment, etc.)",
    )
