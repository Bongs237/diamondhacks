"""EventPulse Orchestrator Agent — uAgent with Chat Protocol for Agentverse.

The only externally-registered agent. Coordinates internal agents via
real agent-to-agent messaging through a Bureau:

  Orchestrator → VoteRequest → FriendAgent(Alex)
  Orchestrator → VoteRequest → FriendAgent(Sarah)
  FriendAgent(Alex) → VoteResponse → Orchestrator
  FriendAgent(Sarah) → VoteResponse → Orchestrator
  (all votes in) → Orchestrator → ConsensusRequest → ConsensusAgent
  ConsensusAgent → ConsensusResult → Orchestrator

All agents run in the same Bureau (single process, shared event loop).
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone

from uagents import Agent, Bureau, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    TextContent,
    chat_protocol_spec,
)

from agents.friend_profile import (
    VoteRequest,
    VoteResponse,
    create_friend_agent,
    get_all_friend_agents,
)
from agents.consensus import (
    ConsensusRequest,
    ConsensusResult,
    consensus_agent,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

FORM_BASE_URL = os.environ.get("FORM_BASE_URL", "http://localhost:3000")

# ---------------------------------------------------------------------------
# In-memory state
# ---------------------------------------------------------------------------

# group_id → list of member profiles
groups: dict[str, list[dict]] = {}

# group_id → group metadata
group_meta: dict[str, dict] = {}

# sender_address → their active group_id
_sender_groups: dict[str, str] = {}

# ---------------------------------------------------------------------------
# Voting state — tracks in-flight votes
# ---------------------------------------------------------------------------

# group_id → {expected: int, votes: [VoteResponse], events: [...], reply_to: str}
_pending_votes: dict[str, dict] = {}

# ---------------------------------------------------------------------------
# Group + profile logic
# ---------------------------------------------------------------------------

def create_group(creator: str) -> str:
    """Create a new group, return its ID."""
    group_id = str(uuid.uuid4())[:8]
    groups[group_id] = []
    group_meta[group_id] = {
        "created_by": creator,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "collecting",
    }
    _sender_groups[creator] = group_id
    return group_id


def get_form_link(group_id: str) -> str:
    return f"{FORM_BASE_URL}/join/{group_id}"


def add_member(group_id: str, profile: dict) -> int:
    """Add a member and create their FriendAgent."""
    if group_id not in groups:
        groups[group_id] = []
    groups[group_id].append(profile)
    friend_agent = create_friend_agent(group_id, profile)
    # Add to bureau if it exists
    if bureau is not None:
        bureau.add(friend_agent)
    return len(groups[group_id])


def get_group_summary(group_id: str) -> str:
    members = groups.get(group_id, [])
    if not members:
        return "No members have joined yet."

    friend_agents = get_all_friend_agents(group_id)
    agent_lookup = {name: a.address for name, a in friend_agents}

    lines = [f"Group {group_id} — {len(members)} member(s):"]
    for m in members:
        name = m.get("name", "Anonymous")
        likes = m.get("likes", "")
        if isinstance(likes, list):
            likes = ", ".join(likes)
        budget = m.get("budget", "?")
        addr = agent_lookup.get(name, "no agent")
        lines.append(f"  - {name}: likes [{likes}], budget ${budget}")
        lines.append(f"    Agent: {addr}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Agent setup
# ---------------------------------------------------------------------------

AGENT_PORT = int(os.environ.get("ORCHESTRATOR_PORT", "8101"))
AGENT_ENDPOINT = os.environ.get(
    "ORCHESTRATOR_ENDPOINT",
    "https://gets-notifications-sorted-promptly.trycloudflare.com/submit",
)

agent = Agent(
    name="EventPulseOrchestrator",
    seed=os.environ.get(
        "AGENT_SEED_PHRASE",
        "eventpulse orchestrator dev seed change me in production",
    ),
    port=AGENT_PORT,
    endpoint=[AGENT_ENDPOINT],
    publish_agent_details=True,
)

# Bureau — will be initialized in main.py or __main__
bureau: Bureau | None = None

# ---------------------------------------------------------------------------
# Chat Protocol — ASI:One interface
# ---------------------------------------------------------------------------

chat_proto = Protocol(spec=chat_protocol_spec)


@chat_proto.on_message(ChatMessage)
async def handle_chat(ctx: Context, sender: str, msg: ChatMessage):
    """Handle Chat Protocol messages from ASI:One."""
    text_parts = [c.text for c in msg.content if isinstance(c, TextContent)]
    user_text = " ".join(text_parts).strip()

    if not user_text:
        await ctx.send(sender, ChatAcknowledgement(acknowledged_msg_id=msg.msg_id))
        return

    logger.info("Chat from %s: %s", sender, user_text)

    # Check if this is a JSON events list to trigger voting
    group_id = _sender_groups.get(sender)
    if group_id:
        try:
            payload = json.loads(user_text)
            if isinstance(payload, list) and payload and "name" in payload[0]:
                # Start the voting flow — send VoteRequest to each friend agent
                reply_text = await _start_voting(ctx, sender, group_id, payload)
                await ctx.send(sender, ChatAcknowledgement(acknowledged_msg_id=msg.msg_id))
                await ctx.send(
                    sender,
                    ChatMessage(
                        timestamp=datetime.now(timezone.utc),
                        msg_id=uuid.uuid4(),
                        content=[TextContent(type="text", text=reply_text)],
                    ),
                )
                return
        except (json.JSONDecodeError, ValueError, KeyError):
            pass

    reply_text = _route_message(sender, user_text)

    await ctx.send(sender, ChatAcknowledgement(acknowledged_msg_id=msg.msg_id))
    await ctx.send(
        sender,
        ChatMessage(
            timestamp=datetime.now(timezone.utc),
            msg_id=uuid.uuid4(),
            content=[TextContent(type="text", text=reply_text)],
        ),
    )


@chat_proto.on_message(ChatAcknowledgement)
async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    logger.debug("Ack from %s", sender)


agent.include(chat_proto, publish_manifest=True)


# ---------------------------------------------------------------------------
# Vote collection — orchestrator receives VoteResponses from friend agents
# ---------------------------------------------------------------------------

@agent.on_message(VoteResponse)
async def handle_vote_response(ctx: Context, sender: str, msg: VoteResponse):
    """Collect a vote from a FriendAgent. When all votes are in, run consensus."""
    pending = _pending_votes.get(msg.group_id)
    if not pending:
        logger.warning("Received vote for unknown group %s", msg.group_id)
        return

    scores = json.loads(msg.scores_json)
    pending["votes"].append({
        "member_name": msg.member_name,
        "agent_address": sender,
        "scores": scores,
    })

    logger.info(
        "Vote received from %s (%s) for group %s [%d/%d]",
        msg.member_name, sender[:20], msg.group_id,
        len(pending["votes"]), pending["expected"],
    )

    # All votes in — send to consensus agent
    if len(pending["votes"]) >= pending["expected"]:
        logger.info("All votes in for group %s — sending to ConsensusAgent", msg.group_id)
        await ctx.send(
            consensus_agent.address,
            ConsensusRequest(
                group_id=msg.group_id,
                all_votes_json=json.dumps(pending["votes"]),
                events_json=json.dumps(pending["events"]),
            ),
        )


# ---------------------------------------------------------------------------
# Consensus result — orchestrator receives the final result
# ---------------------------------------------------------------------------

@agent.on_message(ConsensusResult)
async def handle_consensus_result(ctx: Context, sender: str, msg: ConsensusResult):
    """Receive voting results from ConsensusAgent and store them."""
    winner = json.loads(msg.winner_json)
    pending = _pending_votes.pop(msg.group_id, None)

    # Store results
    group_meta.setdefault(msg.group_id, {})["vote_result"] = {
        "winner": winner,
        "summary": msg.summary,
        "rankings_json": msg.rankings_json,
    }
    group_meta[msg.group_id]["status"] = "voted"

    logger.info(
        "Consensus result for group %s: %s",
        msg.group_id,
        winner["name"] if winner else "no winner",
    )

    # Build detailed summary with agent voting breakdown
    lines = [msg.summary]
    if pending and pending.get("votes"):
        lines.append("\n--- Agent Voting Details ---")
        for ballot in pending["votes"]:
            lines.append(f"\n{ballot['member_name']} ({ballot['agent_address'][:20]}...):")
            for s in ballot["scores"]:
                status = "VETO" if s["vetoed"] else f"score {s['score']}"
                reasons = ", ".join(s["reasons"]) if s["reasons"] else "no factors"
                lines.append(f"  {s['event_name']}: {status} ({reasons})")

    full_summary = "\n".join(lines)
    group_meta[msg.group_id]["vote_result"]["full_summary"] = full_summary

    # Reply to the original sender who triggered voting
    if pending and pending.get("reply_to"):
        await ctx.send(
            pending["reply_to"],
            ChatMessage(
                timestamp=datetime.now(timezone.utc),
                msg_id=uuid.uuid4(),
                content=[TextContent(type="text", text=full_summary)],
            ),
        )


# ---------------------------------------------------------------------------
# Voting trigger
# ---------------------------------------------------------------------------

async def _start_voting(ctx: Context, sender: str, group_id: str, events: list[dict]) -> str:
    """Send VoteRequest to each FriendAgent. Responses come back async."""
    friend_agents = get_all_friend_agents(group_id)
    if not friend_agents:
        return "No members in group — can't vote."

    events_json = json.dumps(events)

    # Set up pending vote tracking
    _pending_votes[group_id] = {
        "expected": len(friend_agents),
        "votes": [],
        "events": events,
        "reply_to": sender,
    }

    # Send VoteRequest to each friend agent
    for name, fagent in friend_agents:
        await ctx.send(
            fagent.address,
            VoteRequest(group_id=group_id, events_json=events_json),
        )
        logger.info("Sent VoteRequest to %s (%s)", name, fagent.address)

    group_meta.setdefault(group_id, {})["status"] = "voting"

    return (
        f"Voting started! Sent ballots to {len(friend_agents)} agent(s).\n"
        f"Each friend's agent is scoring the events independently.\n"
        f"Results will appear shortly — ask me for 'results' in a moment."
    )


# ---------------------------------------------------------------------------
# Message routing (non-voting messages)
# ---------------------------------------------------------------------------

def _route_message(sender: str, text: str) -> str:
    lower = text.lower().strip()

    if sender not in _sender_groups:
        return _create_group_and_link(sender)

    group_id = _sender_groups[sender]

    if any(word in lower for word in ("status", "who", "how many", "members", "update")):
        return get_group_summary(group_id)

    if any(phrase in lower for phrase in ("new group", "new event", "start over", "create")):
        return _create_group_and_link(sender)

    if any(word in lower for word in ("link", "share", "invite", "url")):
        return f"Share this link with your friends:\n{get_form_link(group_id)}"

    if any(word in lower for word in ("vote", "result", "winner", "pick")):
        vote_result = group_meta.get(group_id, {}).get("vote_result")
        if vote_result:
            return vote_result.get("full_summary", vote_result["summary"])
        status = group_meta.get(group_id, {}).get("status", "")
        if status == "voting":
            return "Voting is in progress — agents are still scoring. Ask again in a moment."
        return "No vote has been run yet. Send me a list of events to start voting."

    summary = get_group_summary(group_id)
    link = get_form_link(group_id)
    return f"{summary}\n\nShare this link to invite more friends:\n{link}"


def _create_group_and_link(sender: str) -> str:
    group_id = create_group(sender)
    link = get_form_link(group_id)
    return (
        f"I've created your event group!\n\n"
        f"Share this link with your friends so they can fill out their preferences:\n"
        f"{link}\n\n"
        f"Once everyone has joined, ask me for a status update or say 'find events' "
        f"to start the search."
    )


# ---------------------------------------------------------------------------
# Bureau setup + standalone runner
# ---------------------------------------------------------------------------

def create_bureau() -> Bureau:
    """Create a Bureau with the orchestrator + consensus agent."""
    global bureau
    bureau = Bureau(port=AGENT_PORT, endpoint=[AGENT_ENDPOINT])
    bureau.add(agent)
    bureau.add(consensus_agent)
    return bureau


if __name__ == "__main__":
    b = create_bureau()
    print(f"OrchestratorAgent: {agent.address}")
    print(f"ConsensusAgent:    {consensus_agent.address}")
    print(f"Endpoint:          {AGENT_ENDPOINT}")
    print("Bureau running — all agents active.")
    b.run()
