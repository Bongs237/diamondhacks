"""Anthropic Claude SDK wrapper for LLM calls.

Used by agents that need natural language understanding (e.g. parsing
friend preference text into structured JSON). When ANTHROPIC_API_KEY
is not set, returns a hardcoded example so the pipeline still works.
"""

import json
import logging
import os

import anthropic

logger = logging.getLogger(__name__)

_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic | None:
    """Lazy-init the Anthropic client."""
    global _client
    if _client is not None:
        return _client

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set — LLM calls will return mocks")
        return None

    _client = anthropic.AsyncAnthropic(api_key=api_key)
    return _client


async def parse_preferences(raw_text: str) -> dict:
    """Parse a natural language preference message into structured profile fields.

    Example input:  "I like comedy and live music, budget around $50, nothing far"
    Example output: {"likes": ["comedy", "live-music"], "budget_target": 50, ...}

    The LLM extracts whatever fields it can find. Missing fields are omitted
    from the dict so the caller can merge with defaults.
    """
    client = _get_client()
    if client is None:
        return _mock_parse(raw_text)

    system_prompt = (
        "You are a preference parser for an event planning app. "
        "Extract structured fields from the user's message. "
        "Return ONLY valid JSON with any of these fields: "
        "likes (list of strings), dislikes (list of strings), "
        "budget_target (number), budget_max (number), "
        "budget_strictness ('strict'|'flexible'|'generous'), "
        "available_times (list like 'sat-evening','fri-night'), "
        "max_transit_min (number), dietary (list of strings). "
        "Omit fields not mentioned. Return only the JSON object, no markdown."
    )

    response = await client.messages.create(
        model="claude-sonnet-4-6-20250514",
        max_tokens=512,
        system=system_prompt,
        messages=[{"role": "user", "content": raw_text}],
    )

    text = response.content[0].text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.error("LLM returned invalid JSON: %s", text)
        return {}


async def generate_reasoning(prompt: str) -> str:
    """General-purpose LLM call for agent reasoning strings.

    Used by agents that need to explain their decisions in natural language
    (e.g. FriendProfileAgent explaining why it voted for an event).
    """
    client = _get_client()
    if client is None:
        return f"[MOCK reasoning for: {prompt[:80]}]"

    response = await client.messages.create(
        model="claude-sonnet-4-6-20250514",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


def _mock_parse(raw_text: str) -> dict:
    """Fallback parse when no API key is set."""
    logger.info("[MOCK LLM] Would parse: %s", raw_text)
    return {
        "likes": ["comedy", "live-music"],
        "budget_target": 50,
        "budget_strictness": "flexible",
        "available_times": ["sat-evening"],
    }
