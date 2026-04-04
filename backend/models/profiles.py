"""Pydantic model for friend profiles, matching the JSON schema in profiles/."""

from pydantic import BaseModel, Field


class FriendProfile(BaseModel):
    name: str
    likes: list[str] = []
    dislikes: list[str] = []
    budget_target: float = 50.0
    budget_max: float = 75.0
    budget_strictness: str = "flexible"  # "strict" | "flexible" | "generous"
    available_times: list[str] = []
    max_transit_min: int = 30
    location: list[float] = Field(default_factory=lambda: [40.73, -73.99])
    dietary: list[str] = []
    flake_score: float = 0.0
    events_organized: int = 0
    notes: str = ""
