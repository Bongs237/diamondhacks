"""Twilio incoming WhatsApp webhook.

POST /webhooks/twilio receives form-encoded data from Twilio when a
friend sends a WhatsApp message. We:
  1. Return an empty TwiML response immediately (no timeout risk)
  2. Kick off a background task that routes the message through
     conversation → ASI:One → agents → WhatsApp reply
"""

import logging

from fastapi import APIRouter, BackgroundTasks, Form, Response

from messaging import asi_one, conversation, twilio_service

logger = logging.getLogger(__name__)
router = APIRouter()

# Empty TwiML — tells Twilio "we got it, don't send any auto-reply"
EMPTY_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response/>'


@router.post("/webhooks/twilio")
async def twilio_incoming(
    background_tasks: BackgroundTasks,
    From: str = Form(...),
    Body: str = Form(""),
):
    """Handle an incoming WhatsApp message from Twilio.

    Twilio POSTs form data with From=whatsapp:+1xxx and Body= fields.
    We strip the whatsapp: prefix for internal use (session mapping),
    then add it back when sending the reply.
    """
    # Twilio sends "whatsapp:+15105567735" — strip prefix for session mapping
    phone = From.replace("whatsapp:", "")
    message = Body.strip()
    logger.info("Incoming WhatsApp from %s: %s", phone, message)

    if not message:
        return Response(content=EMPTY_TWIML, media_type="application/xml")

    background_tasks.add_task(_process_and_reply, phone, message)
    return Response(content=EMPTY_TWIML, media_type="application/xml")


async def _process_and_reply(phone: str, message: str):
    """Background task: route message through ASI:One and send WhatsApp reply.

    This runs after the webhook has already returned 200 to Twilio,
    so we're not constrained by the 15-second webhook timeout.
    """
    try:
        session_id = conversation.get_or_create_session(phone)
        reply = await asi_one.send_message(session_id, message)
        twilio_service.send_message(phone, reply)
    except Exception:
        logger.exception("Failed to process message from %s", phone)
        twilio_service.send_message(
            phone,
            "Sorry, we hit a snag processing your message. Please try again!",
        )
