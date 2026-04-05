from __future__ import annotations
import os
from uagents import Agent, Bureau, Context
from dotenv import load_dotenv
load_dotenv()

from stripe_agent import (
    stripe_agent,
    EventPaymentRequest,
    PaymentLinkResponse,
    PaymentConfirmation,
)

mock = Agent(
    name="mock_orchestrator",
    seed="mock-orchestrator-seed",
    port=8005,
    endpoint=["http://localhost:8005/submit"],
    network="testnet",
)

EVENT_NAME   = "Comedy Night at The Laugh Factory"
TOTAL_AMOUNT = 6000
NUM_PEOPLE   = 3

_current_people = NUM_PEOPLE
_current_link   = None

@mock.on_event("startup")
async def send_mock_request(ctx: Context):
    ctx.logger.info(f"Sending mock event — {NUM_PEOPLE} people, ${TOTAL_AMOUNT/100:.2f} total")
    await ctx.send(stripe_agent.address, EventPaymentRequest(
        event_name=EVENT_NAME,
        total_amount=TOTAL_AMOUNT,
        num_people=NUM_PEOPLE,
    ))

@mock.on_message(model=PaymentLinkResponse)
async def got_link(ctx: Context, sender: str, msg: PaymentLinkResponse):
    global _current_link
    _current_link = msg.payment_link
    ctx.logger.info(f"✅ Payment link: {msg.payment_link}")
    ctx.logger.info(f"   ${msg.per_person_cents/100:.2f} per person")

@mock.on_message(model=PaymentConfirmation)
async def got_confirmation(ctx: Context, sender: str, msg: PaymentConfirmation):
    ctx.logger.info(f"🎉 ALL PAID — {msg.event_name} — ${msg.total_collected_cents/100:.2f}")

@mock.on_interval(period=10.0)
async def simulate_drop(ctx: Context):
    global _current_people
    if _current_link is None:
        return
    if _current_people <= 1:
        ctx.logger.info("Only 1 person left — can't drop further")
        return
    _current_people -= 1
    ctx.logger.info(f"⚠️  Someone dropped! Recalculating for {_current_people} people...")
    await ctx.send(stripe_agent.address, EventPaymentRequest(
        event_name=EVENT_NAME,
        total_amount=TOTAL_AMOUNT,
        num_people=_current_people,
    ))

if __name__ == "__main__":
    bureau = Bureau()
    bureau.add(stripe_agent)
    bureau.add(mock)
    bureau.run()