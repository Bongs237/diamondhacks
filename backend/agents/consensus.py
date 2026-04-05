"""ConsensusAgent — internal uAgent that runs ranked-choice voting.

Receives individual vote results from FriendProfileAgents, aggregates
them, eliminates vetoed events, and ranks the rest by total score.

Not registered on Agentverse — runs internally in the same process.
"""

import json
import logging

from uagents import Agent, Context, Model

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Message schemas
# ---------------------------------------------------------------------------

class ConsensusRequest(Model):
    """Orchestrator → ConsensusAgent: run voting with these ballots."""
    group_id: str
    all_votes_json: str  # JSON list of {member_name, scores: [{event_name, score, vetoed, reasons}]}
    events_json: str     # JSON list of event dicts


class ConsensusResult(Model):
    """ConsensusAgent → Orchestrator: the voting results."""
    group_id: str
    winner_json: str     # JSON of winning event dict, or "null"
    rankings_json: str   # JSON of full rankings
    summary: str         # Human-readable result


# ---------------------------------------------------------------------------
# Consensus logic
# ---------------------------------------------------------------------------

def _run_consensus(all_votes: list[dict], events: list[dict]) -> dict:
    """Aggregate votes and rank events.

    all_votes: [{"member_name": "Alex", "scores": [{"event_name": ..., "score": ..., "vetoed": ...}]}]
    events: [{"name": ..., "cost": ..., ...}]

    Returns {"winner", "rankings", "vetoed", "summary"}
    """
    event_lookup = {e["name"]: e for e in events}
    event_totals: dict[str, int] = {}
    event_votes: dict[str, list[dict]] = {}
    vetoed_events: dict[str, list[str]] = {}  # event_name → list of members who vetoed
    veto_reasons: dict[str, list[str]] = {}

    for ballot in all_votes:
        member = ballot["member_name"]
        for score_entry in ballot["scores"]:
            ename = score_entry["event_name"]

            if score_entry["vetoed"]:
                vetoed_events.setdefault(ename, []).append(member)
                veto_reasons.setdefault(ename, []).extend(score_entry.get("reasons", []))
            else:
                event_totals[ename] = event_totals.get(ename, 0) + score_entry["score"]
                event_votes.setdefault(ename, []).append({
                    "member": member,
                    "score": score_entry["score"],
                    "reasons": score_entry.get("reasons", []),
                })

    # Remove any event that was vetoed by anyone
    for vetoed_name in vetoed_events:
        event_totals.pop(vetoed_name, None)
        event_votes.pop(vetoed_name, None)

    # Rank surviving events
    rankings = sorted(
        [
            {
                "event": event_lookup.get(name, {"name": name}),
                "total_score": total,
                "votes": event_votes.get(name, []),
            }
            for name, total in event_totals.items()
        ],
        key=lambda r: r["total_score"],
        reverse=True,
    )

    vetoed_list = [
        {
            "event": event_lookup.get(name, {"name": name}),
            "vetoed_by": members,
            "reasons": veto_reasons.get(name, []),
        }
        for name, members in vetoed_events.items()
    ]

    winner = rankings[0]["event"] if rankings else None

    # Build summary
    lines = []
    if winner:
        lines.append(f"1. Winner: {winner['name']} (score: {rankings[0]['total_score']})")
        lines.append(f"   Cost: ${winner.get('cost', '?')} | Time: {winner.get('time', '?')}")
    else:
        lines.append("No events survived — every option was vetoed by at least one member.")

    if len(rankings) > 1:
        lines.append("\nOther options:\n")
        for i, r in enumerate(rankings[1:], start=2):
            e = r["event"]
            cost = f"${e.get('cost', '?')}" if e.get('cost') else "Free"
            lines.append(f"{i}. {e['name']} — {cost}")
        lines.append("\nSay 'info 3' for details on any event, or pick a number to choose it.")

    if vetoed_list:
        lines.append(f"\nVetoed ({len(vetoed_list)}):")
        for v in vetoed_list:
            who = ", ".join(v["vetoed_by"])
            lines.append(f"  - {v['event']['name']} (vetoed by {who})")

    return {
        "winner": winner,
        "rankings": rankings,
        "vetoed": vetoed_list,
        "summary": "\n".join(lines),
    }


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

consensus_agent = Agent(
    name="EventPulseConsensus",
    seed="eventpulse consensus agent internal seed",
    port=None,  # Internal only — no HTTP server
)


@consensus_agent.on_message(ConsensusRequest, replies=ConsensusResult)
async def handle_consensus(ctx: Context, sender: str, msg: ConsensusRequest):
    """Receive all ballots, run ranked-choice, return results."""
    all_votes = json.loads(msg.all_votes_json)
    events = json.loads(msg.events_json)

    result = _run_consensus(all_votes, events)

    logger.info(
        "Consensus for group %s: winner=%s",
        msg.group_id,
        result["winner"]["name"] if result["winner"] else "none",
    )

    await ctx.send(
        sender,
        ConsensusResult(
            group_id=msg.group_id,
            winner_json=json.dumps(result["winner"]),
            rankings_json=json.dumps(result["rankings"], default=str),
            summary=result["summary"],
        ),
    )
