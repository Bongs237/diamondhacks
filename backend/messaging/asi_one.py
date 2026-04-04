"""ASI:One API client.

Sends user messages to ASI:One's chat completions endpoint, which
automatically discovers and routes to our agents on Agentverse.

When ASI1_API_KEY is not set, falls back to a mock that echoes the
message — lets you test the full Twilio→FastAPI→reply pipeline
without an API key.
"""

import asyncio
import logging
import os

import httpx

logger = logging.getLogger(__name__)

ASI_ONE_URL = "https://api.asi1.ai/v1/chat/completions"
# Max times to poll "Any update?" for long-running agent tasks
MAX_POLL_ATTEMPTS = 12  # 12 × 5s = 60s ceiling
POLL_INTERVAL_SEC = 5


async def send_message(session_id: str, message: str) -> str:
    """Send a user message through ASI:One and return the assistant reply.

    ASI:One discovers our OrchestratorAgent on Agentverse via Chat Protocol.
    The x-session-id header ties the conversation to a specific friend so
    ASI:One maintains per-user context across turns.

    For long-running agent tasks, ASI:One may return an interim response
    indicating work is in progress. We poll with "Any update?" until we
    get a substantive reply or hit the timeout.
    """
    api_key = os.getenv("ASI1_API_KEY", "")
    if not api_key:
        logger.warning("ASI1_API_KEY not set — using mock response")
        return _mock_response(message)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "x-session-id": session_id,
    }
    payload = {
        "model": "asi1",
        "messages": [{"role": "user", "content": message}],
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await _post(client, headers, payload)
        reply = _extract_reply(response)

        # Poll if the agent indicates work in progress
        for _ in range(MAX_POLL_ATTEMPTS):
            if not _is_pending(reply):
                return reply
            await asyncio.sleep(POLL_INTERVAL_SEC)
            payload["messages"] = [{"role": "user", "content": "Any update?"}]
            response = await _post(client, headers, payload)
            reply = _extract_reply(response)

        return reply


async def _post(
    client: httpx.AsyncClient,
    headers: dict,
    payload: dict,
) -> dict:
    """POST to ASI:One and return parsed JSON. Raises on HTTP errors."""
    resp = await client.post(ASI_ONE_URL, json=payload, headers=headers)
    resp.raise_for_status()
    return resp.json()


def _extract_reply(response: dict) -> str:
    """Pull the assistant message text out of the OpenAI-style response."""
    try:
        return response["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        logger.error("Unexpected ASI:One response shape: %s", response)
        return "Sorry, something went wrong. Please try again."


def _is_pending(reply: str) -> bool:
    """Heuristic: ASI:One returns short status messages while agents work."""
    pending_phrases = ["processing", "working on", "please wait", "in progress"]
    lower = reply.lower()
    return any(phrase in lower for phrase in pending_phrases)


def _mock_response(message: str) -> str:
    """Fake response for local testing without an API key."""
    return (
        f"[MOCK] EventPulse received your message: \"{message}\". "
        "Once ASI:One is connected, our agents will handle your preferences!"
    )
