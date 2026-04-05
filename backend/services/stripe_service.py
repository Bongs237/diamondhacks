"""Stripe payment service — creates payment links for group events.

Uses Stripe Payment Links so members can pay via a simple URL.
When STRIPE_SECRET_KEY is not set, returns mock links.

Flow:
  1. Event chosen → create_event_payment_link(event_name, cost_per_person)
  2. Members open the link and pay
  3. Stripe webhook confirms payment → update member status
  4. All paid → booking agent can proceed
  5. Dropout before booking → refund via Stripe
  6. Dropout after booking → payment already captured, no refund
"""

import logging
import os

import stripe

logger = logging.getLogger(__name__)

_initialized = False


def _init():
    global _initialized
    if _initialized:
        return
    key = os.getenv("STRIPE_SECRET_KEY", "")
    if key:
        stripe.api_key = key
        _initialized = True
    else:
        logger.warning("STRIPE_SECRET_KEY not set — payments will be mocked")


def create_event_payment_link(event_name: str, cost_per_person: float, currency: str = "usd") -> dict:
    """Create a Stripe Payment Link for an event.

    Returns {"url": "https://...", "payment_link_id": "plink_...", "product_id": "prod_...", "price_id": "price_..."}
    or a mock version if Stripe isn't configured.
    """
    _init()

    if not stripe.api_key:
        mock_url = f"https://buy.stripe.com/test/mock_{event_name.replace(' ', '_')}"
        logger.info("[MOCK] Payment link for %s: %s", event_name, mock_url)
        return {
            "url": mock_url,
            "payment_link_id": "mock_plink",
            "product_id": "mock_prod",
            "price_id": "mock_price",
        }

    # Create product for the event
    product = stripe.Product.create(name=f"EventPulse: {event_name}")

    # Create price (amount in cents)
    price = stripe.Price.create(
        unit_amount=int(cost_per_person * 100),
        currency=currency,
        product=product.id,
    )

    # Create payment link
    link = stripe.PaymentLink.create(
        line_items=[{"price": price.id, "quantity": 1}],
    )

    logger.info("Payment link created for %s ($%.2f): %s", event_name, cost_per_person, link.url)

    return {
        "url": link.url,
        "payment_link_id": link.id,
        "product_id": product.id,
        "price_id": price.id,
    }


def refund_payment(payment_intent_id: str) -> dict:
    """Refund a payment by its PaymentIntent ID."""
    _init()

    if not stripe.api_key:
        logger.info("[MOCK] Refund for %s", payment_intent_id)
        return {"status": "mock_refunded", "id": "mock_refund"}

    refund = stripe.Refund.create(payment_intent=payment_intent_id)
    logger.info("Refund created: %s for payment %s", refund.id, payment_intent_id)
    return {"status": refund.status, "id": refund.id}
