"""Pydantic v2 schemas for browser-use structured outputs."""

from pydantic import BaseModel, Field


class ActivityIdea(BaseModel):
    title: str = Field(description="Short name of the activity or event")
    category: str = Field(
        description="e.g. movies, comedy, live_music, dining, museum, outdoors"
    )
    description: str = Field(description="One or two sentences; include timing if known")
    estimated_cost_per_person_usd: float | None = Field(
        default=None, description="Approximate USD per person, or null if unknown"
    )
    booking_url: str | None = Field(
        default=None, description="Official booking or tickets URL if found"
    )
    venue_or_provider: str | None = Field(default=None, description="Venue, chain, or organizer")
    starts_at_local_hint: str | None = Field(
        default=None, description="Human-readable date/time in local timezone if known"
    )
    transit_friendly_note: str | None = Field(
        default=None, description="Optional note on distance/transit from the given area"
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
