"""EventPulse Orchestrator Agent — uAgent with Chat Protocol for Agentverse.

The only externally-registered agent. Coordinates internal agents via
real agent-to-agent messaging through a Bureau:

  Form full → Orchestrator → ChatMessage(JSON) → DiscoveryAgent
  DiscoveryAgent → ChatMessage(results) → Orchestrator
  Orchestrator → VoteRequest → FriendAgent(Alex)
  FriendAgent(Alex) → VoteResponse → Orchestrator
  (all votes in) → Orchestrator → ConsensusRequest → ConsensusAgent
  ConsensusAgent → ConsensusResult → Orchestrator
  Orchestrator → ChatMessage(winner) → ASI:One → User

All internal agents run in the same Bureau (single process, shared event loop).
Discovery agent runs separately (teammate's process).
"""

import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone

from uagents import Agent, Bureau, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    EndSessionContent,
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
DISCOVERY_AGENT_ADDRESS = os.environ.get("DISCOVERY_AGENT_ADDRESS", "")

# ---------------------------------------------------------------------------
# In-memory state
# ---------------------------------------------------------------------------

groups: dict[str, list[dict]] = {}
group_meta: dict[str, dict] = {}
_session_groups: dict[str, str] = {}
_pending_setup: dict[str, dict] = {}
_pending_votes: dict[str, dict] = {}

# group_id → True when discovery has been triggered (prevent double-trigger)
_discovery_triggered: dict[str, bool] = {}

# Store the ASI:One session info so we can send async updates
# sender_address → {"session": uuid, "last_ctx": Context}
_asi_sessions: dict[str, dict] = {}

# ---------------------------------------------------------------------------
# Group + profile logic
# ---------------------------------------------------------------------------

def create_group(session_key: str, expected_members: int) -> str:
    group_id = str(uuid.uuid4())[:8]
    groups[group_id] = []
    group_meta[group_id] = {
        "created_by": session_key,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "collecting",
        "expected_members": expected_members,
    }
    _session_groups[session_key] = group_id
    return group_id


def get_form_link(group_id: str) -> str:
    return f"{FORM_BASE_URL}/join/{group_id}"


def add_member(group_id: str, profile: dict) -> int:
    """Add a member and create their FriendAgent. Returns member count."""
    if group_id not in groups:
        groups[group_id] = []
    groups[group_id].append(profile)
    friend_agent = create_friend_agent(group_id, profile)
    if bureau is not None:
        bureau.add(friend_agent)
    return len(groups[group_id])


def is_group_full(group_id: str) -> bool:
    """Check if all expected members have submitted."""
    meta = group_meta.get(group_id, {})
    expected = meta.get("expected_members", 0)
    current = len(groups.get(group_id, []))
    return expected > 0 and current >= expected


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


def _build_discovery_payload(group_id: str) -> dict:
    """Build the JSON payload for the discovery agent from member profiles."""
    members = groups.get(group_id, [])
    locations = []
    for m in members:
        loc = m.get("location", [])
        dist = m.get("distance", "10")
        # Parse distance to a number (miles) — default 10
        radius = 10.0
        nums = re.findall(r"[\d.]+", str(dist))
        if nums:
            radius = float(nums[0])
        if isinstance(loc, list) and len(loc) >= 2:
            locations.append([loc[0], loc[1], radius])

    # Use the most common available_time, or None
    times = [m.get("available_times", "") for m in members]
    times = [t for t in times if t and "all" not in t.lower()]
    when = times[0] if times else None

    return {
        "locations": locations,
        "when": when,
        "max_steps": 25,
    }


# ---------------------------------------------------------------------------
# Agent setup
# ---------------------------------------------------------------------------

AGENT_PORT = int(os.environ.get("ORCHESTRATOR_PORT", "8101"))
AGENT_ENDPOINT = os.environ.get(
    "ORCHESTRATOR_ENDPOINT",
    "https://unaccrued-sona-unmanipulated.ngrok-free.dev/submit",
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

bureau: Bureau | None = None

# Queue for groups that need discovery triggered (set by FastAPI, consumed by agent)
_discovery_queue: list[str] = []


@agent.on_interval(period=2.0)
async def check_discovery_queue(ctx: Context):
    """Poll for groups that are full and need discovery triggered."""
    while _discovery_queue:
        group_id = _discovery_queue.pop(0)
        await trigger_discovery(ctx, group_id)


# ---------------------------------------------------------------------------
# Chat Protocol — ASI:One interface + discovery agent responses
# ---------------------------------------------------------------------------

chat_proto = Protocol(spec=chat_protocol_spec)


@chat_proto.on_message(ChatMessage)
async def handle_chat(ctx: Context, sender: str, msg: ChatMessage):
    """Handle Chat Protocol messages from ASI:One or discovery agent."""
    text_parts = [c.text for c in msg.content if isinstance(c, TextContent)]
    user_text = " ".join(text_parts).strip()

    if not user_text:
        await ctx.send(sender, ChatAcknowledgement(acknowledged_msg_id=msg.msg_id))
        return

    # Use session ID as the user key (different ASI:One chats get different sessions)
    session_key = str(ctx.session) if ctx.session else sender
    logger.info("Chat from %s (session %s): %s", sender, session_key[:8], user_text[:200])
    await ctx.send(sender, ChatAcknowledgement(acknowledged_msg_id=msg.msg_id))

    # Check if this is a discovery agent response
    if DISCOVERY_AGENT_ADDRESS and sender == DISCOVERY_AGENT_ADDRESS:
        await _handle_discovery_response(ctx, user_text)
        return

    # Save session info for async updates
    _asi_sessions[session_key] = {"sender": sender, "session": ctx.session, "ctx": ctx}

    # Check if this is a JSON payload (events list or discovery response)
    group_id = _session_groups.get(session_key)
    if group_id:
        try:
            payload = json.loads(user_text)
            if isinstance(payload, dict) and payload.get("ok") and "result" in payload:
                await _handle_discovery_result(ctx, group_id, payload)
                return
            if isinstance(payload, list) and payload and "name" in payload[0]:
                reply_text = await _start_voting(ctx, sender, group_id, payload)
                await _send_chat(ctx, sender, reply_text)
                return
        except (json.JSONDecodeError, ValueError, KeyError):
            pass

    reply_text = _route_message(session_key, user_text)
    await _send_chat(ctx, sender, reply_text)


@chat_proto.on_message(ChatAcknowledgement)
async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    logger.debug("Ack from %s", sender)


agent.include(chat_proto, publish_manifest=True)


# ---------------------------------------------------------------------------
# Helper to send ChatMessage
# ---------------------------------------------------------------------------

async def _send_chat(ctx: Context, destination: str, text: str, end_session: bool = False):
    content = [TextContent(type="text", text=text)]
    if end_session:
        content.append(EndSessionContent(type="end-session"))
    await ctx.send(
        destination,
        ChatMessage(
            timestamp=datetime.now(timezone.utc),
            msg_id=uuid.uuid4(),
            content=content,
        ),
    )


async def _send_async_update(group_id: str, text: str):
    """Send an async update to the organizer using the stored session."""
    session_key = group_meta.get(group_id, {}).get("created_by", "")
    if not session_key:
        logger.warning("No creator for group %s — can't send async update", group_id)
        return

    session_info = _asi_sessions.get(session_key)
    if not session_info or not session_info.get("ctx"):
        logger.warning("No stored session for %s — can't send async update", session_key)
        return

    ctx = session_info["ctx"]
    sender_address = session_info["sender"]
    await _send_chat(ctx, sender_address, text)


# ---------------------------------------------------------------------------
# Discovery trigger — called when group is full
# ---------------------------------------------------------------------------

async def trigger_discovery(ctx: Context, group_id: str):
    """Send discovery request when all members have submitted."""
    if _discovery_triggered.get(group_id):
        return
    _discovery_triggered[group_id] = True

    group_meta[group_id]["status"] = "discovering"
    payload = _build_discovery_payload(group_id)
    creator = group_meta[group_id].get("created_by", "")

    logger.info("Group %s is full — triggering event discovery", group_id)
    logger.info("Discovery payload: %s", json.dumps(payload))

    # Async update to organizer
    await _send_async_update(
        group_id,
        f"All {group_meta[group_id]['expected_members']} members have submitted! Searching for events near your group...",
    )

    if DISCOVERY_AGENT_ADDRESS:
        await _send_chat(ctx, DISCOVERY_AGENT_ADDRESS, json.dumps(payload))
        logger.info("Sent discovery request to %s", DISCOVERY_AGENT_ADDRESS)
    else:
        logger.info("No discovery agent configured — waiting for manual events")
        group_meta[group_id]["status"] = "waiting_for_events"


async def _handle_discovery_response(ctx: Context, text: str):
    """Handle a ChatMessage from the discovery agent."""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Discovery agent sent non-JSON: %s", text[:200])
        return

    # Find which group this discovery is for (most recent discovering group)
    group_id = None
    for gid, meta in group_meta.items():
        if meta.get("status") == "discovering":
            group_id = gid
            break

    if not group_id:
        logger.warning("Got discovery response but no group is in discovering state")
        return

    await _handle_discovery_result(ctx, group_id, payload)


async def _handle_discovery_result(ctx: Context, group_id: str, payload: dict):
    """Process discovery results and auto-trigger voting."""
    result = payload.get("result", {})
    activities = result.get("activities", [])

    if not activities:
        creator = group_meta.get(group_id, {}).get("created_by", "")
        error = payload.get("error", "No events found")
        if creator:
            await _send_chat(ctx, creator, f"Discovery returned no events: {error}")
        group_meta[group_id]["status"] = "waiting_for_events"
        return

    # Convert ActivityIdea format to our event format for voting
    events = []
    for a in activities:
        events.append({
            "name": a.get("title", "Unknown"),
            "cost": a.get("estimated_cost_per_person_usd", 0) or 0,
            "category": a.get("category", "").lower().replace("_", "-"),
            "time": a.get("starts_at_local_hint", ""),
            "time_commitment": "",
            "venue": a.get("venue_or_provider", ""),
            "booking_url": a.get("booking_url", ""),
            "description": a.get("description", ""),
        })

    logger.info("Discovery found %d events for group %s — starting voting", len(events), group_id)

    creator = group_meta.get(group_id, {}).get("created_by", "")

    # Run voting directly (friend agents score synchronously since
    # dynamically-added agents can't reliably receive messages via Bureau)
    from agents.friend_profile import score_event
    from agents.consensus import _run_consensus

    members = groups.get(group_id, [])
    friend_agents = get_all_friend_agents(group_id)

    all_votes = []
    for name, fagent in friend_agents:
        profile = next((m for m in members if m.get("name") == name), None)
        if not profile:
            continue
        scores = [score_event(event, profile) for event in events]
        all_votes.append({
            "member_name": name,
            "agent_address": fagent.address,
            "scores": scores,
        })
        logger.info("FriendAgent %s (%s) scored %d events", name, fagent.address[:20], len(events))

    result = _run_consensus(all_votes, events)

    # Store results (keep full details for API access)
    group_meta.setdefault(group_id, {})["vote_result"] = result
    group_meta[group_id]["vote_result"]["all_votes"] = all_votes
    group_meta[group_id]["status"] = "voted"

    # Build clean summary for the organizer (no voting details)
    lines = [result["summary"]]
    lines.append("\nReply with a number to pick a different event (e.g. '3' for the 3rd option).")

    clean_summary = "\n".join(lines)
    group_meta[group_id]["vote_result"]["clean_summary"] = clean_summary

    # Store ranked events list for selection
    group_meta[group_id]["ranked_events"] = [r["event"] for r in result["rankings"]]

    winner_name = result["winner"]["name"] if result["winner"] else "no winner"
    logger.info("Voting complete for group %s — winner: %s", group_id, winner_name)

    # Async update to organizer with clean results
    await _send_async_update(group_id, clean_summary)


# ---------------------------------------------------------------------------
# Vote collection
# ---------------------------------------------------------------------------

@agent.on_message(VoteResponse)
async def handle_vote_response(ctx: Context, sender: str, msg: VoteResponse):
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
# Consensus result
# ---------------------------------------------------------------------------

@agent.on_message(ConsensusResult)
async def handle_consensus_result(ctx: Context, sender: str, msg: ConsensusResult):
    winner = json.loads(msg.winner_json)
    pending = _pending_votes.pop(msg.group_id, None)

    group_meta.setdefault(msg.group_id, {})["vote_result"] = {
        "winner": winner,
        "summary": msg.summary,
        "rankings_json": msg.rankings_json,
    }
    group_meta[msg.group_id]["status"] = "voted"

    logger.info(
        "Consensus for group %s: %s",
        msg.group_id,
        winner["name"] if winner else "no winner",
    )

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

    # Send result to organizer
    if pending and pending.get("reply_to"):
        await _send_chat(ctx, pending["reply_to"], full_summary)


# ---------------------------------------------------------------------------
# Voting trigger
# ---------------------------------------------------------------------------

async def _start_voting(ctx: Context, sender: str, group_id: str, events: list[dict]) -> str:
    friend_agents = get_all_friend_agents(group_id)
    if not friend_agents:
        return "No members in group — can't vote."

    meta = group_meta.get(group_id, {})
    expected = meta.get("expected_members", 0)
    current = len(groups.get(group_id, []))
    if expected > 0 and current < expected:
        return (
            f"Can't start voting yet — {current}/{expected} members have submitted.\n"
            f"Waiting for {expected - current} more.\n"
            f"Share the link: {get_form_link(group_id)}"
        )

    events_json = json.dumps(events)

    _pending_votes[group_id] = {
        "expected": len(friend_agents),
        "votes": [],
        "events": events,
        "reply_to": sender,
    }

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
# Message routing
# ---------------------------------------------------------------------------

def _route_message(sender: str, text: str) -> str:
    lower = text.lower().strip()

    if sender in _pending_setup:
        return _handle_setup(sender, text)

    if sender not in _session_groups:
        return _start_setup(sender, text)

    group_id = _session_groups[sender]

    if any(word in lower for word in ("status", "who", "how many", "members", "update")):
        return _group_status_with_readiness(group_id)

    if any(phrase in lower for phrase in ("new group", "new event", "start over", "create")):
        return _start_setup(sender, text)

    # Cancel the entire group
    if any(word in lower for word in ("cancel", "abort", "delete group", "end group")):
        return _cancel_group(group_id)

    # Remove a member by name (e.g. "remove Alex", "drop Sarah")
    if lower.startswith("remove ") or lower.startswith("drop ") or lower.startswith("kick "):
        name = text.split(maxsplit=1)[1].strip() if len(text.split()) > 1 else ""
        if name:
            return _remove_member(group_id, name)
        return "Who should I remove? Say 'remove <name>'."

    if any(word in lower for word in ("link", "share", "invite", "url")):
        return f"Share this link with your friends:\n{get_form_link(group_id)}"

    if any(word in lower for word in ("vote", "result", "winner", "pick")):
        vote_result = group_meta.get(group_id, {}).get("vote_result")
        if vote_result:
            return vote_result.get("clean_summary", vote_result["summary"])
        status = group_meta.get(group_id, {}).get("status", "")
        if status == "voting":
            return "Voting is in progress — agents are still scoring. Ask again in a moment."
        if status == "discovering":
            return "Searching for events near your group... this may take a minute."
        return "No vote has been run yet. Send me a list of events to start voting."

    # User picks an event by number
    ranked_events = group_meta.get(group_id, {}).get("ranked_events", [])
    if ranked_events:
        pick = _extract_number(text)
        if pick and 1 <= pick <= len(ranked_events):
            chosen = ranked_events[pick - 1]
            group_meta[group_id]["chosen_event"] = chosen
            group_meta[group_id]["status"] = "chosen"
            booking = chosen.get("booking_url", "")
            booking_line = f"\nBook here: {booking}" if booking else ""
            return (
                f"Great choice! The group is going to:\n\n"
                f"{chosen['name']}\n"
                f"Cost: ${chosen.get('cost', '?')} per person\n"
                f"Time: {chosen.get('time', 'TBD')}\n"
                f"Venue: {chosen.get('venue', '')}"
                f"{booking_line}"
            )

    summary = _group_status_with_readiness(group_id)
    link = get_form_link(group_id)
    return f"{summary}\n\nShare this link to invite more friends:\n{link}"


def _start_setup(sender: str, text: str) -> str:
    group_size = _extract_number(text)
    if group_size and group_size > 0:
        return _finalize_setup(sender, int(group_size))
    _pending_setup[sender] = {"stage": "need_group_size"}
    return "I'd love to help plan your event! How many friends are joining?"


def _handle_setup(sender: str, text: str) -> str:
    setup = _pending_setup[sender]
    if setup["stage"] == "need_group_size":
        group_size = _extract_number(text)
        if group_size and group_size > 0:
            del _pending_setup[sender]
            return _finalize_setup(sender, int(group_size))
        return "I need a number — how many friends will be joining the group?"
    del _pending_setup[sender]
    return _start_setup(sender, text)


def _finalize_setup(sender: str, group_size: int) -> str:
    group_id = create_group(sender, group_size)
    link = get_form_link(group_id)
    return (
        f"I've created your event group for {group_size} people!\n\n"
        f"Share this link with your friends so they can fill out their preferences:\n"
        f"{link}\n\n"
        f"I'll let you know once everyone has submitted. "
        f"Ask me for a 'status' update anytime."
    )


def _cancel_group(group_id: str) -> str:
    """Cancel the entire group."""
    members = groups.get(group_id, [])
    count = len(members)
    groups.pop(group_id, None)
    group_meta.pop(group_id, None)
    _discovery_triggered.pop(group_id, None)
    # Remove session → group mappings pointing to this group
    to_remove = [k for k, v in _session_groups.items() if v == group_id]
    for k in to_remove:
        del _session_groups[k]
    logger.info("Group %s cancelled (%d members)", group_id, count)
    return f"Group {group_id} has been cancelled. All {count} member(s) removed."


def _remove_member(group_id: str, name: str) -> str:
    """Remove a member by name and destroy their FriendAgent."""
    members = groups.get(group_id, [])
    match = next((m for m in members if m.get("name", "").lower() == name.lower()), None)
    if not match:
        names = ", ".join(m.get("name", "?") for m in members)
        return f"No member named '{name}'. Current members: {names}"

    members.remove(match)
    actual_name = match.get("name", name)

    # Remove friend agent
    from agents.friend_profile import _friend_agents
    agent_key = f"{group_id}:{actual_name}"
    _friend_agents.pop(agent_key, None)

    logger.info("Removed %s from group %s (%d remaining)", actual_name, group_id, len(members))

    # If voting already happened, re-run with remaining members
    meta = group_meta.get(group_id, {})
    if meta.get("status") == "voted" and meta.get("vote_result"):
        # Re-run voting with cached events
        ranked = meta.get("ranked_events", [])
        if ranked:
            from agents.friend_profile import score_event
            from agents.consensus import _run_consensus

            friend_agents = get_all_friend_agents(group_id)
            all_votes = []
            for n, fagent in friend_agents:
                profile = next((m for m in members if m.get("name") == n), None)
                if not profile:
                    continue
                scores = [score_event(event, profile) for event in ranked]
                all_votes.append({
                    "member_name": n,
                    "agent_address": fagent.address,
                    "scores": scores,
                })

            result = _run_consensus(all_votes, ranked)
            meta["vote_result"] = result
            meta["ranked_events"] = [r["event"] for r in result["rankings"]]
            meta["vote_result"]["clean_summary"] = result["summary"] + "\n\nReply with a number to pick a different event."

            return (
                f"Removed {actual_name}. Re-ran voting with {len(members)} remaining member(s).\n\n"
                f"{result['summary']}"
            )

    expected = meta.get("expected_members", 0)
    return (
        f"Removed {actual_name} from the group. "
        f"({len(members)}/{expected} members now)"
    )


def _group_status_with_readiness(group_id: str) -> str:
    summary = get_group_summary(group_id)
    meta = group_meta.get(group_id, {})
    expected = meta.get("expected_members", 0)
    current = len(groups.get(group_id, []))

    if expected > 0 and current < expected:
        summary += f"\n\nWaiting for {expected - current} more member(s) to submit their preferences."
    elif expected > 0 and current >= expected:
        status = meta.get("status", "")
        if status == "discovering":
            summary += "\n\nEveryone's in! Searching for events..."
        elif status == "voting":
            summary += "\n\nVoting in progress..."
        elif status == "voted":
            summary += "\n\nVoting complete! Ask me for 'results'."
        else:
            summary += "\n\nEveryone's in! Starting event search..."

    return summary


_WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}


def _extract_number(text: str) -> int | None:
    match = re.search(r"\d+", text)
    if match:
        return int(match.group())
    for word, num in _WORD_NUMBERS.items():
        if word in text.lower():
            return num
    return None


# ---------------------------------------------------------------------------
# Bureau setup + standalone runner
# ---------------------------------------------------------------------------

def create_bureau(discovery_agent=None) -> Bureau:
    global bureau
    bureau = Bureau(port=AGENT_PORT, endpoint=[AGENT_ENDPOINT])
    bureau.add(agent)
    bureau.add(consensus_agent)
    if discovery_agent:
        bureau.add(discovery_agent)
        logger.info("Discovery agent added to bureau: %s", discovery_agent.address)
    return bureau


if __name__ == "__main__":
    b = create_bureau()
    print(f"OrchestratorAgent: {agent.address}")
    print(f"ConsensusAgent:    {consensus_agent.address}")
    print(f"Endpoint:          {AGENT_ENDPOINT}")
    b.run()
