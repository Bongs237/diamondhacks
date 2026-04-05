"""EventPulse backend entrypoint.

Runs two things in one process:
  1. A Bureau with all uAgents (orchestrator, consensus, friend agents)
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
    create_bureau,
)
from agents.consensus import consensus_agent  # noqa: E402

# ---------------------------------------------------------------------------
# Form submission model
# ---------------------------------------------------------------------------

class JoinForm(BaseModel):
    name: str
    budget: str                      # "10-20" or "50" — parsed into a number
    available_times: str = ""        # "sat-evening" or "all the time"
    location: list[float] = []
    distance: str = ""               # "5 miles" or "everywhere"
    likes: str | list[str] = ""      # single string or list
    dislikes: str | list[str] = ""   # single string or list

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


@app.post("/api/join/{group_id}")
async def join_group(group_id: str, form: JoinForm):
    """Receive a friend's preferences from the shareable form."""
    if group_id not in groups:
        return {"error": "Group not found"}, 404

    profile = form.model_dump()
    count = add_member(group_id, profile)
    logging.info("Form: %s joined group %s (%d members)", form.name, group_id, count)

    return {
        "status": "joined",
        "group_id": group_id,
        "member_count": count,
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


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "orchestrator": agent.address,
        "consensus": consensus_agent.address,
    }

@app.post("/api/submit/{id}")
async def submit(id: str):
    print("yeah")
    return {"message": "Join request submitted"}

# ---------------------------------------------------------------------------
# Start Bureau + API server
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    # Start the Bureau (all agents) in a background thread
    bureau = create_bureau()

    def run_bureau():
        logging.info("Bureau starting with orchestrator + consensus agents")
        logging.info("  Orchestrator: %s", agent.address)
        logging.info("  Consensus:    %s", consensus_agent.address)
        bureau.run()

    threading.Thread(target=run_bureau, daemon=True).start()

    # Start FastAPI on the main thread
    api_port = int(os.environ.get("PORT", "8000"))
    logging.info("API server starting on port %s", api_port)
    uvicorn.run(app, host="0.0.0.0", port=api_port)
