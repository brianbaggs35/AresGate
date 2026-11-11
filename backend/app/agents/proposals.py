"""What the cleanup agent suggests, and what is done with it.

The agent never changes an incident itself in the middle of a run. It finds what can be tidied
(app/incidents/cleanup.py), keeps each as a suggestion, and the owner applies it, turns it down or,
once it is applied, takes it back. With the agents set to do the surest of it themselves (Settings
> Agents), a suggestion the agent is very sure of is applied as soon as it is made, and says so.
Either way it is the incident list's own bulk change that does it, so it can be undone, and it
only ever touches AresGate's own records: nothing here reaches the network or a program that
reports to AresGate.
"""

from collections.abc import Collection, Sequence
from datetime import datetime, timedelta
from typing import Final, cast

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import audit
from app.audit import Action, Outcome
from app.incidents import bulk, engine
from app.incidents import cleanup as tidy
from app.incidents.cleanup import Candidate
from app.incidents.verdicts import NOT_SUSPICIOUS
from app.models import AgentProposal, Incident

# How sure the agent has to be for it to act without being asked, when it may.
AUTO_FROM: Final = 80
# How long a decided suggestion is kept (so that it is not made again), and how long one nobody
# has decided on waits.
DECIDED_FOR: Final = 90
WAITING_FOR: Final = 30
NOTE: Final = "Set by the cleanup agent."
STATUS_OF: Final = {tidy.DISMISS: "dismissed", tidy.RESOLVE: "resolved"}


class Settled(Exception):
    """The suggestion has been decided already, and the message says how."""


def _incidents(db: Session, ids: Collection[int]) -> list[Incident]:
    """The incidents of a suggestion that are still open, because the owner may have dealt with
    some of them since."""
    return list(
        db.scalars(
            select(Incident)
            .where(Incident.id.in_(ids), Incident.status.in_(tidy.ACTIVE))
            .order_by(Incident.id)
        )
    )


def record(
    db: Session,
    agent_id: int,
    run_id: int,
    found: Sequence[Candidate],
    rejected: Collection[str],
    now: datetime,
    *,
    auto: bool,
) -> tuple[list[AgentProposal], list[AgentProposal]]:
    """Keeps what a run found as suggestions, except what the model said to leave alone and what
    was suggested before, however it went. Gives back the new ones and, of them, the ones it
    applied, when it may."""
    known = set(db.scalars(select(AgentProposal.key).where(AgentProposal.agent_id == agent_id)))
    made: list[AgentProposal] = []
    done: list[AgentProposal] = []
    for item in found:
        if item.key in rejected or item.key in known:
            continue
        proposal = AgentProposal(
            agent_id=agent_id,
            run_id=run_id,
            kind=item.kind,
            key=item.key,
            title=item.title,
            detail=item.detail,
            action=item.action,
            incident_ids=list(item.incidents),
            keep_id=item.keep,
            confidence=item.confidence,
            status="pending",
            created_at=now,
        )
        db.add(proposal)
        made.append(proposal)
    db.flush()
    if auto:
        for proposal in made:
            if proposal.confidence >= AUTO_FROM and apply(db, proposal, "agent", now) > 0:
                done.append(proposal)
                audit.record(
                    db,
                    Action.AGENT_PROPOSAL_APPLIED,
                    Outcome.SUCCESS,
                    detail={
                        "proposal": proposal.id,
                        "agent": agent_id,
                        "by": "agent",
                        "kind": proposal.kind,
                        "incidents": len(proposal.incident_ids),
                    },
                    now=now,
                )
    return made, done


def apply(db: Session, proposal: AgentProposal, by: str, now: datetime) -> int:
    """Does what the suggestion says, and notes how to take it back. Gives back how many
    incidents it changed; a suggestion whose incidents have all been dealt with since is only
    closed. The caller commits."""
    if proposal.status != "pending":
        raise Settled(f"This suggestion has already been {proposal.status}.")
    incidents = _incidents(db, proposal.incident_ids)
    undo: dict[str, object] = {}
    changed = 0
    if incidents and proposal.action in STATUS_OF:
        done = bulk.set_status(incidents, STATUS_OF[proposal.action], now=now, apply=True)
        undo = {"statuses": done.statuses}
        changed = done.changed
    elif incidents:
        engine.hold(db)
        done = bulk.give_verdict(db, incidents, NOT_SUSPICIOUS, NOTE, apply=True)
        undo = {"rules": [[rule_id, replaced] for rule_id, replaced in done.rules]}
        changed = done.changed
        engine.reapply(db)
    proposal.status = "applied" if changed else "dismissed"
    proposal.decided_by = by
    proposal.decided_at = now
    proposal.undo = undo
    return changed


def dismiss(db: Session, proposal: AgentProposal, now: datetime) -> None:
    """Turns a suggestion down, so that it is not made again."""
    if proposal.status != "pending":
        raise Settled(f"This suggestion has already been {proposal.status}.")
    proposal.status = "dismissed"
    proposal.decided_by = "owner"
    proposal.decided_at = now


def undo(db: Session, proposal: AgentProposal, now: datetime) -> int:
    """Takes back what applying a suggestion did. Gives back how many incidents were put back or
    verdicts removed."""
    if proposal.status != "applied":
        raise Settled("Only a suggestion that was applied can be taken back.")
    statuses = cast("dict[str, list[int]]", proposal.undo.get("statuses") or {})
    rules = [
        (cast("int", rule_id), cast("str | None", replaced))
        for rule_id, replaced in cast("list[list[object]]", proposal.undo.get("rules") or [])
    ]
    if rules:
        engine.hold(db)
    restored, changed = bulk.take_back(db, statuses, rules, now=now)
    if changed:
        engine.reapply(db)
    proposal.status = "undone"
    proposal.decided_at = now
    return restored + changed


def forget(db: Session, now: datetime) -> None:
    """Forgets suggestions decided long ago, and ones nobody has decided on for a month."""
    db.execute(
        delete(AgentProposal).where(
            AgentProposal.status != "pending",
            AgentProposal.decided_at < now - timedelta(days=DECIDED_FOR),
        )
    )
    db.execute(
        delete(AgentProposal).where(
            AgentProposal.status == "pending",
            AgentProposal.created_at < now - timedelta(days=WAITING_FOR),
        )
    )
