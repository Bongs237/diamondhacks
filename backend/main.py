"""EventPulse backend entrypoint.

Runs two things in one process:
  1. A Bureau with all uAgents (orchestrator, consensus, discovery, friend agents)
  2. A minimal FastAPI server for form submissions

Run with: .venv/bin/python main.py
"""

import logging
import os
import sys
import threading

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    stream=sys.stdout,
)

from agents.orchestrator import (  # noqa: E402
    agent,
    groups,
    group_meta,
    add_member,
    get_group_summary,
    is_group_full,
    _discovery_queue,
    _notification_queue,
    _remove_member,
    create_bureau,
)
from agents.consensus import consensus_agent  # noqa: E402

# Try to import the discovery agent — requires browser_use
discovery_agent = None
try:
    from agents.activity_search_uagent import protocol as discovery_protocol
    from uagents import Agent as UAgent

    discovery_agent = UAgent(
        name="activity_search",
        seed=os.environ.get("ACTIVITY_SEARCH_AGENT_SEED", "activity search dev seed"),
        port=None,  # Internal — no separate HTTP server
    )
    discovery_agent.include(discovery_protocol, publish_manifest=True)
    # Tell the orchestrator where to send discovery requests
    import agents.orchestrator as orch
    orch.DISCOVERY_AGENT_ADDRESS = discovery_agent.address
    logging.info("Discovery agent loaded — address: %s", discovery_agent.address)
except ImportError as e:
    logging.warning("Discovery agent not available (missing dependency: %s)", e)

# ---------------------------------------------------------------------------
# Form submission model
# ---------------------------------------------------------------------------

class JoinForm(BaseModel):
    user_id: str
    name: str
    budget: str = ""
    available_times: str = ""
    location: list[float] = []
    distance: str = ""
    likes: str | list[str] = ""
    dislikes: str | list[str] = ""

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="EventPulse")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/submit/{group_id}")
async def join_group(group_id: str, form: JoinForm):
    print(group_id, form, flush=True)

    """Receive a friend's preferences from the shareable form."""
    if group_id not in groups:
        return {"error": "Group not found"}, 404

    profile = form.model_dump()
    count = add_member(group_id, profile)
    logging.info("Form: %s joined group %s (%d members)", form.name, group_id, count)

    full = is_group_full(group_id)

    if full:
        logging.info("Group %s is full — queuing discovery", group_id)
        _discovery_queue.append(group_id)

    print("Did we even get here?", flush=True)

    return {
        "status": "joined",
        "group_id": group_id,
        "member_count": count,
        "group_full": full,
        "summary": get_group_summary(group_id),
    }


@app.get("/api/group/{group_id}")
async def group_status(group_id: str):
    print("The groups are like", groups, flush=True)

    if group_id not in groups:
        return {"error": "Group not found"}, 404

    return {
        "group_id": group_id,
        "members": groups[group_id],
        "member_count": len(groups[group_id]),
        "status": group_meta.get(group_id, {}).get("status", "unknown"),
        "vote_result": group_meta.get(group_id, {}).get("vote_result"),
    }


@app.post("/api/dropout/{group_id}/{user_id}")
async def dropout(group_id: str, user_id: str):
    """A member drops out of a group."""
    if group_id not in groups:
        return {"error": "Group not found"}, 404
    result = _remove_member(group_id, user_id)
    return {"status": "removed", "detail": result}


@app.get("/api/user/{user_id}/groups")
async def user_groups(user_id: str):
    """Return every group that contains a member with the given user_id."""
    result = []
    for gid, members in groups.items():
        if any(m.get("user_id") == user_id for m in members):
            result.append({
                "group_id": gid,
                "members": members,
                "member_count": len(members),
                "status": group_meta.get(gid, {}).get("status", "unknown"),
                "vote_result": group_meta.get(gid, {}).get("vote_result"),
            })
    return result


@app.post("/api/payment-confirm/{group_id}/{member_name}")
async def confirm_payment(group_id: str, member_name: str):
    """Manually confirm a member's payment (for demo/testing).

    In production, this would be triggered by Stripe webhook.
    """
    if group_id not in groups:
        return {"error": "Group not found"}, 404

    meta = group_meta.get(group_id, {})
    if meta.get("status") != "awaiting_payment":
        return {"error": "Group is not awaiting payment"}

    paid = meta.setdefault("payments_received", [])
    if member_name not in paid:
        paid.append(member_name)

    total = len(groups[group_id])
    logging.info("Payment confirmed: %s in group %s (%d/%d)", member_name, group_id, len(paid), total)

    # Check if all members have paid
    if len(paid) >= total:
        meta["status"] = "booked"
        logging.info("All payments received for group %s — ready to book", group_id)
        _notification_queue.append((
            group_id,
            f"All {total} members have paid! Tickets are being booked for {meta.get('chosen_event', {}).get('name', 'the event')}.",
        ))

    return {
        "status": "confirmed",
        "member": member_name,
        "paid_count": len(paid),
        "total_members": total,
        "all_paid": len(paid) >= total,
    }


@app.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events (payment completed)."""
    import stripe as stripe_lib
    body = await request.body()
    sig = request.headers.get("stripe-signature", "")
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

    if webhook_secret:
        try:
            event = stripe_lib.Webhook.construct_event(body, sig, webhook_secret)
        except Exception as e:
            logging.warning("Stripe webhook verification failed: %s", e)
            return {"error": "Invalid signature"}, 400
    else:
        import json as _json
        event = _json.loads(body)

    if event.get("type") == "checkout.session.completed":
        session = event["data"]["object"]
        # The payment link ID helps us find which group this is for
        payment_link_id = session.get("payment_link")
        customer_email = session.get("customer_details", {}).get("email", "unknown")

        logging.info("Stripe payment received: link=%s email=%s", payment_link_id, customer_email)

        # Find the group with this payment link
        for gid, meta in group_meta.items():
            if meta.get("payment", {}).get("payment_link_id") == payment_link_id:
                paid = meta.setdefault("payments_received", [])
                paid.append(customer_email)
                total = len(groups.get(gid, []))

                if len(paid) >= total:
                    meta["status"] = "booked"
                    _notification_queue.append((
                        gid,
                        f"All {total} members have paid! Booking tickets now.",
                    ))
                break

    return {"received": True}


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "orchestrator": agent.address,
        "consensus": consensus_agent.address,
        "discovery": discovery_agent.address if discovery_agent else "not loaded",
    }


# ---------------------------------------------------------------------------
# Start Bureau + API server
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    bureau = create_bureau(discovery_agent=discovery_agent)

    def run_bureau():
        logging.info("Bureau starting:")
        logging.info("  Orchestrator: %s", agent.address)
        logging.info("  Consensus:    %s", consensus_agent.address)
        if discovery_agent:
            logging.info("  Discovery:    %s", discovery_agent.address)
        bureau.run()

    threading.Thread(target=run_bureau, daemon=True).start()

    api_port = int(os.environ.get("PORT", "8000"))
    logging.info("API server starting on port %s", api_port)
    uvicorn.run(app, host="0.0.0.0", port=api_port)
