"""Twilio messaging service (WhatsApp via sandbox).

Uses Twilio's WhatsApp sandbox for instant messaging without
toll-free verification or A2P 10DLC registration.

When TWILIO_ACCOUNT_SID is not set, falls back to logging the message
to stdout — lets you test without Twilio credentials.
"""

import logging
import os

from twilio.rest import Client

logger = logging.getLogger(__name__)

# Twilio WhatsApp sandbox number — fixed for all sandbox users
WHATSAPP_SANDBOX = "whatsapp:+14155238886"

# Lazily initialized on first use so missing env vars don't crash at import
_client: Client | None = None


def _get_client() -> Client | None:
    """Return a Twilio client, or None if credentials aren't configured."""
    global _client
    if _client is not None:
        return _client

    sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    token = os.getenv("TWILIO_AUTH_TOKEN", "")
    if not sid or not token:
        logger.warning("Twilio credentials not set — messages will be logged only")
        return None

    _client = Client(sid, token)
    return _client


def _to_whatsapp(phone: str) -> str:
    """Ensure phone number has the whatsapp: prefix."""
    if phone.startswith("whatsapp:"):
        return phone
    return f"whatsapp:{phone}"


def send_message(to: str, body: str) -> str | None:
    """Send a WhatsApp message and return the message SID, or None in mock mode.

    Uses the Twilio REST API so we can send replies asynchronously from
    background tasks without being constrained by the webhook timeout.
    """
    client = _get_client()

    if client is None:
        logger.info("[MOCK WhatsApp] To: %s | Body: %s", to, body)
        return None

    message = client.messages.create(
        to=_to_whatsapp(to),
        from_=WHATSAPP_SANDBOX,
        body=body,
    )
    logger.info("WhatsApp sent to %s — SID: %s", to, message.sid)
    return message.sid
