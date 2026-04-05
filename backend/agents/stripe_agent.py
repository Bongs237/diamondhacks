from __future__ import annotations
import os
import stripe
from uagents import Agent, Context, Model
from dotenv import load_dotenv
load_dotenv()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

class EventPaymentRequest(Model):
    event_name: str
    total_amount: int
    num_people: int

class PaymentLinkResponse(Model):
    event_name: str
    payment_link: str
    per_person_cents: int

class WebhookPaymentReceived(Model):
    event_name: str
    payer_email: str
    amount_cents: int
    payment_intent_id: str

class PaymentConfirmation(Model):
    event_name: str
    num_people: int
    total_collected_cents: int
    payment_link: str

stripe_agent = Agent(
    name="stripe_agent",
    seed=os.getenv("STRIPE_AGENT_SEED", "stripe-agent-seed"),
    port=8006,
    endpoint=["http://localhost:8006/submit"],
    network="testnet",
)

ORCHESTRATOR_ADDRESS = os.getenv("ORCHESTRATOR_ADDRESS", "")
_sessions: dict[str, dict] = {}

@stripe_agent.on_interval(period=30.0)
async def keep_alive(ctx: Context):
    ctx.logger.info("stripe_agent alive and waiting...")

@stripe_agent.on_message(model=EventPaymentRequest)
async def handle_event_request(ctx: Context, sender: str, msg: EventPaymentRequest):
    per_person = msg.total_amount // msg.num_people
    ctx.logger.info(f"{msg.event_name}: ${msg.total_amount/100:.2f} total, {msg.num_people} people, ${per_person/100:.2f} each")

    product = stripe.Product.create(name=msg.event_name)
    price = stripe.Price.create(unit_amount=per_person, currency="usd", product=product.id)
    link = stripe.PaymentLink.create(
        line_items=[{"price": price.id, "quantity": 1}],
        metadata={"event_name": msg.event_name},
    )

    _sessions[msg.event_name] = {
        "num_people": msg.num_people,
        "payment_link": link.url,
        "sender": sender,
        "payments": [],
    }

    ctx.logger.info(f"Payment link: {link.url}")
    await ctx.send(sender, PaymentLinkResponse(
        event_name=msg.event_name,
        payment_link=link.url,
        per_person_cents=per_person,
    ))

@stripe_agent.on_message(model=WebhookPaymentReceived)
async def handle_payment(ctx: Context, sender: str, msg: WebhookPaymentReceived):
    session = _sessions.get(msg.event_name)
    if not session:
        ctx.logger.warning(f"No session for {msg.event_name}")
        return

    if msg.payment_intent_id not in [p["pi_id"] for p in session["payments"]]:
        session["payments"].append({
            "email": msg.payer_email,
            "amount": msg.amount_cents,
            "pi_id": msg.payment_intent_id,
        })

    paid = len(session["payments"])
    needed = session["num_people"]
    ctx.logger.info(f"{paid}/{needed} paid for {msg.event_name}")

    if paid >= needed:
        total = sum(p["amount"] for p in session["payments"])
        ctx.logger.info(f"ALL PAID ✅ {msg.event_name} — ${total/100:.2f}")
        await ctx.send(ORCHESTRATOR_ADDRESS, PaymentConfirmation(
            event_name=msg.event_name,
            num_people=needed,
            total_collected_cents=total,
            payment_link=session["payment_link"],
        ))

def main():
    stripe_agent.run()

if __name__ == "__main__":
    main()
