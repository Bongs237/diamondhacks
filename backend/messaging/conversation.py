"""Phone number ↔ ASI:One session mapping.

Each phone number gets a persistent session UUID so ASI:One maintains
conversation context across multiple SMS messages from the same friend.
"""

import uuid

# phone_number → session_id
_phone_to_session: dict[str, str] = {}
# session_id → phone_number (reverse lookup for sending replies)
_session_to_phone: dict[str, str] = {}


def get_or_create_session(phone: str) -> str:
    """Return existing session ID for this phone, or create a new one.

    ASI:One uses x-session-id to maintain conversation state per user.
    We create one session per phone number so each friend has a persistent
    conversation thread with the orchestrator agent.
    """
    if phone in _phone_to_session:
        return _phone_to_session[phone]

    session_id = str(uuid.uuid4())
    _phone_to_session[phone] = session_id
    _session_to_phone[session_id] = phone
    return session_id


def get_phone_by_session(session_id: str) -> str | None:
    """Reverse lookup: find the phone number that owns a session."""
    return _session_to_phone.get(session_id)


def get_session_by_phone(phone: str) -> str | None:
    """Look up session without creating one. Returns None if not found."""
    return _phone_to_session.get(phone)
