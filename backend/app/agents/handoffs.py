"""Agents asking each other for help.

An agent that has looked at the network (the Security orchestrator, Security triage) may ask
another kind of agent to look into something it saw: an incident, a device, an address. That is a
hand-off: a structured request, kept as it was made (who asked, which kind it asked for, what about
and why), that starts a run of the owner's agent of that kind, with the reason put in front of it
as what it was asked, not as an instruction.

A hand-off is limited so that agents cannot run away with it: it only goes ``MAX_DEPTH`` deep,
never comes back to an agent that is already part of the chain (no circles), at most ``PER_DAY``
are made in a day, an agent asks for at most ``PER_RUN`` in one run, and the agents' spending
limits still hold (Settings > Agents). A refused hand-off is kept with the reason. Nothing here
changes anything on the network: the agent that is asked only reads, like every agent.
"""

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Final, NamedTuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import audit
from app.agents import catalog, service
from app.agents import settings as agent_settings
from app.audit import Action, Outcome
from app.models import Agent, AgentHandoff, AgentRun

# How many hand-offs deep a run may be: an agent asks another, which may ask a third, and that is
# the end of it.
MAX_DEPTH: Final = 2
# How many hand-offs are made in a day, and how many one run asks for.
PER_DAY: Final = 10
PER_RUN: Final = 3
MAX_SUBJECT: Final = 200
MAX_REASON: Final = 500


class Asked(NamedTuple):
    """One hand-off as the model asked for it, before it is checked: the kind of agent, what it is
    about, why, and the incident that is, if it is one the run looked at."""

    kind: str
    subject: str
    reason: str
    incident_id: int | None
    # Whether the subject is something the run really looked at.
    seen: bool


def depth_of(db: Session, run_id: int) -> int:
    """How many hand-offs deep a run is: 0 for one the owner or a schedule started."""
    found = db.scalar(select(AgentHandoff.depth).where(AgentHandoff.to_run_id == run_id))
    return found or 0


def chain(db: Session, run_id: int) -> list[int]:
    """The agents that handed work down to this run, nearest first, and the agent of this run
    last."""
    agents: list[int] = []
    current: int | None = run_id
    # The depth limit bounds this, but a loop that cannot end is worse than a wrong answer.
    while current is not None and len(agents) <= MAX_DEPTH + 1:
        run = db.get(AgentRun, current)
        if run is None:  # pragma: no cover - the run was deleted while it asked
            break
        agents.append(run.agent_id)
        current = db.scalar(select(AgentHandoff.run_id).where(AgentHandoff.to_run_id == current))
    return agents


def made_today(db: Session, now: datetime) -> int:
    """How many hand-offs were made in the last day, which the limit is on."""
    return (
        db.scalar(
            select(func.count())
            .select_from(AgentHandoff)
            .where(
                AgentHandoff.status == "queued", AgentHandoff.created_at >= now - timedelta(days=1)
            )
        )
        or 0
    )


def _refusal(
    db: Session, run: AgentRun, asked: Asked, target: Agent | None, asked_so_far: int, now: datetime
) -> str | None:
    """Why this hand-off may not be made, or None if it may."""
    kind = catalog.template(asked.kind)
    if kind is None or asked.kind not in catalog.HANDOFF_KINDS:
        return (
            "That kind of agent cannot be asked: only the owner starts one that tests the network."
        )
    if not asked.seen:
        return "It named something it never looked at."
    if asked_so_far >= PER_RUN:
        return f"An agent asks for at most {PER_RUN} hand-offs in a run."
    if depth_of(db, run.id) >= MAX_DEPTH:
        return f"Hand-offs go {MAX_DEPTH} deep at most."
    if target is None:
        return f"You have no {kind.name} agent that is on."
    if target.id in chain(db, run.id):
        return f"{target.name} is already part of this chain, so it would go in a circle."
    if made_today(db, now) >= PER_DAY:
        return f"{PER_DAY} hand-offs have been made in the last day, which is the most."
    if (spent := agent_settings.reached(db, now)) is not None:
        return spent
    return None


def _target(db: Session, kind: str) -> Agent | None:
    """The owner's agent of a kind that is on: the oldest, if there are several."""
    return db.scalars(
        select(Agent)
        .where(Agent.template == kind, Agent.enabled.is_(True))
        .order_by(Agent.id)
        .limit(1)
    ).first()


def hand_off(
    db: Session, run: AgentRun, requests: Sequence[Asked], now: datetime
) -> list[AgentHandoff]:
    """Makes what a run asked for, or refuses it, and keeps each as it was asked. The caller
    commits."""
    made: list[AgentHandoff] = []
    for asked in requests:
        target = _target(db, asked.kind)
        refusal = _refusal(db, run, asked, target, len(made), now)
        record = AgentHandoff(
            run_id=run.id,
            from_agent_id=run.agent_id,
            to_kind=asked.kind,
            to_agent_id=target.id if target else None,
            subject=asked.subject[:MAX_SUBJECT],
            incident_id=asked.incident_id,
            reason=asked.reason[:MAX_REASON],
            status="refused" if refusal else "queued",
            refusal=refusal,
            depth=depth_of(db, run.id) + 1,
            created_at=now,
        )
        if refusal is None and target is not None:
            try:
                started = service.queue(db, target, "handoff", now)
            except service.Busy:
                record.status = "refused"
                record.refusal = f"{target.name} already has a run waiting or going."
            except service.NotAllowed as stopped:  # pragma: no cover - only kinds that test the net
                record.status = "refused"
                record.refusal = str(stopped)
            else:
                record.to_run_id = started.id
        db.add(record)
        db.flush()
        made.append(record)
        audit.record(
            db,
            Action.AGENT_HANDOFF,
            Outcome.SUCCESS if record.status == "queued" else Outcome.FAILURE,
            detail={
                "handoff": record.id,
                "from": run.agent_id,
                "to": record.to_agent_id or 0,
                "kind": record.to_kind,
                "run": run.id,
                "refusal": record.refusal or "",
            },
            now=now,
        )
    return made
