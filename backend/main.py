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
from fastapi import FastAPI
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

    return {
        "status": "joined",
        "group_id": group_id,
        "member_count": count,
        "group_full": full,
        "summary": get_group_summary(group_id),
    }


@app.get("/api/group/{group_id}")
async def group_status(group_id: str):
    if group_id not in groups:
        return {"error": "Group not found"}, 404

    return {
        "group_id": group_id,
        "members": groups[group_id],
        "member_count": len(groups[group_id]),
        "status": group_meta.get(group_id, {}).get("status", "unknown"),
        "vote_result": group_meta.get(group_id, {}).get("vote_result"),
    }


@app.post("/api/dropout/{group_id}/{name}")
async def dropout(group_id: str, name: str):
    """A member drops out of a group."""
    if group_id not in groups:
        return {"error": "Group not found"}, 404
    result = _remove_member(group_id, name)
    return {"status": "removed", "detail": result}


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
