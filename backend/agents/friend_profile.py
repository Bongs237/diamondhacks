"""FriendProfileAgent — internal uAgent representing one group member.

Each friend gets their own agent instance at runtime when they join
a group. The agent holds their preferences and scores events
independently when asked to vote.

These agents are NOT registered on Agentverse — they run internally
in the same process as the orchestrator and communicate via ctx.send().
"""

import logging

from uagents import Agent, Context, Model

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Message schemas for orchestrator ↔ friend agent communication
# ---------------------------------------------------------------------------

class VoteRequest(Model):
    """Orchestrator → FriendAgent: score these events."""
    group_id: str
    events_json: str  # JSON-encoded list of event dicts


class VoteResponse(Model):
    """FriendAgent → Orchestrator: my scores for each event."""
    group_id: str
    member_name: str
    scores_json: str  # JSON-encoded list of score dicts


# ---------------------------------------------------------------------------
# Scoring logic
# ---------------------------------------------------------------------------

def _parse_budget(raw) -> float:
    """Extract max budget from form input. Handles '10-20', '50', 50, etc."""
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).strip().replace("$", "")
    if "-" in s:
        # Range like "10-20" — use the upper bound
        parts = s.split("-")
        try:
            return float(parts[-1].strip())
        except ValueError:
            return float("inf")
    try:
        return float(s)
    except ValueError:
        return float("inf")


def _parse_list(raw) -> list[str]:
    """Turn a string or list into a lowercase list of items."""
    if isinstance(raw, list):
        return [s.lower().strip() for s in raw if s.strip()]
    s = str(raw).strip().lower()
    if not s:
        return []
    # Split on commas if present, otherwise treat as single item
    if "," in s:
        return [item.strip() for item in s.split(",") if item.strip()]
    return [s]


def score_event(event: dict, profile: dict) -> dict:
    """Score a single event against this member's preferences.

    Profile fields come directly from the form:
      budget: "10-20" or "50" or 50
      available_times: "sat-evening" or "all the time"
      likes: "comedy" or ["comedy", "live-music"]
      dislikes: "improv" or ["improv"]

    Scoring:
      +3  category in likes
      -5  category in dislikes
      +2  cost ≤ budget
      -1 per $10 over budget (penalty, not veto)
      -3  time mismatch (penalty, not veto)
    """
    score = 0
    reasons = []

    event_cost = event.get("cost", 0)
    event_category = event.get("category", "").lower()
    event_time = event.get("time", "").lower()

    budget = _parse_budget(profile.get("budget", float("inf")))
    pref_time = str(profile.get("available_times", "")).lower().strip()
    likes = _parse_list(profile.get("likes", ""))
    dislikes = _parse_list(profile.get("dislikes", ""))

    # Budget: bonus if under, penalty if over (-1 per $10 over)
    if event_cost <= budget:
        score += 2
        reasons.append(f"within budget (+2)")
    else:
        over = event_cost - budget
        penalty = -max(1, int(over / 10))
        score += penalty
        reasons.append(f"${over:.0f} over budget ({penalty})")

    # Time: penalty if mismatch (not veto)
    no_time_constraint = not pref_time or "all" in pref_time
    if not no_time_constraint and event_time and event_time != pref_time:
        score -= 3
        reasons.append(f"time mismatch ({event_time} vs {pref_time}) (-3)")

    # Category likes/dislikes
    if event_category in likes:
        score += 3
        reasons.append(f"likes {event_category} (+3)")

    if event_category in dislikes:
        score -= 5
        reasons.append(f"dislikes {event_category} (-5)")

    return {"event_name": event["name"], "score": score, "vetoed": False, "reasons": reasons}


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------

# All created friend agents, keyed by "group_id:member_name"
_friend_agents: dict[str, Agent] = {}


def create_friend_agent(group_id: str, profile: dict) -> Agent:
    """Create an internal uAgent for a group member.

    Same code for every friend — different profile data per instance.
    The agent listens for VoteRequest and responds with VoteResponse.
    """
    import json

    name = profile.get("name", "unknown")
    agent_key = f"{group_id}:{name}"

    # Don't create duplicates
    if agent_key in _friend_agents:
        return _friend_agents[agent_key]

    agent = Agent(
        name=f"friend-{name}-{group_id}",
        seed=f"friend agent {agent_key} seed",
        port=None,  # No HTTP server — internal only
    )

    @agent.on_message(VoteRequest, replies=VoteResponse)
    async def handle_vote(ctx: Context, sender: str, msg: VoteRequest):
        """Score all events and return votes to the orchestrator."""
        events = json.loads(msg.events_json)
        scores = [score_event(event, profile) for event in events]

        logger.info(
            "FriendAgent %s scored %d events for group %s",
            name, len(events), msg.group_id,
        )

        await ctx.send(
            sender,
            VoteResponse(
                group_id=msg.group_id,
                member_name=name,
                scores_json=json.dumps(scores),
            ),
        )

    _friend_agents[agent_key] = agent
    logger.info("Created FriendAgent for %s in group %s — address: %s", name, group_id, agent.address)
    return agent


def get_friend_agent(group_id: str, name: str) -> Agent | None:
    """Look up an existing friend agent."""
    return _friend_agents.get(f"{group_id}:{name}")


def get_all_friend_agents(group_id: str) -> list[tuple[str, Agent]]:
    """Get all friend agents for a group. Returns [(name, agent), ...]."""
    prefix = f"{group_id}:"
    return [
        (key.split(":", 1)[1], agent)
        for key, agent in _friend_agents.items()
        if key.startswith(prefix)
    ]
