"""What is done to agents and their runs, apart from running them (app/agents/run.py): asking for
a run, starting the ones that are due, stopping one, and forgetting the old."""

from datetime import datetime, timedelta
from typing import Final

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.agents import catalog, proposals
from app.models import Agent, AgentRun

# How long a run is kept after it is over.
RETENTION: Final = timedelta(days=30)
WAITING: Final = ("queued", "running")


class Busy(Exception):
    """The agent already has a run that is waiting or going."""


class NotAllowed(Exception):
    """The agent may not run now, and the message says why."""


def active_run(db: Session, agent_id: int) -> AgentRun | None:
    return db.scalars(
        select(AgentRun)
        .where(AgentRun.agent_id == agent_id, AgentRun.status.in_(WAITING))
        .order_by(AgentRun.id.desc())
        .limit(1)
    ).first()


def next_run_at(enabled: bool, interval_minutes: int | None, now: datetime) -> datetime | None:
    """When the schedule starts the next run: one interval from now, if there is a schedule."""
    if not enabled or interval_minutes is None:
        return None
    return now + timedelta(minutes=interval_minutes)


def queue(db: Session, agent: Agent, trigger: str, now: datetime) -> AgentRun:
    """Asks for a run, which the worker starts. An agent that tests the network only runs when
    the owner has allowed it, and only when the owner asks."""
    template = catalog.template(agent.template)
    if template is not None and template.active:
        if trigger != "manual":
            raise NotAllowed("An agent that tests the network only runs when you start it.")
        if not agent.allow_active:
            raise NotAllowed("Allow this agent to test the network first.")
    if active_run(db, agent.id) is not None:
        raise Busy
    run = AgentRun(agent_id=agent.id, trigger=trigger, status="queued", requested_at=now)
    db.add(run)
    db.flush()
    return run


def schedule(db: Session, now: datetime) -> int:
    """Asks for a run of each agent whose time has come, and sets the time of the next. An agent
    that is still running its last is left alone this time. Gives back how many were asked for."""
    due = db.scalars(
        select(Agent).where(
            Agent.enabled.is_(True),
            Agent.interval_minutes.is_not(None),
            Agent.next_run_at <= now,
        )
    ).all()
    asked = 0
    for agent in due:
        agent.next_run_at = next_run_at(agent.enabled, agent.interval_minutes, now)
        try:
            queue(db, agent, "schedule", now)
        except Busy, NotAllowed:
            continue
        asked += 1
    return asked


def waiting(db: Session) -> list[int]:
    """The runs that wait for the worker, the oldest first."""
    return list(
        db.scalars(select(AgentRun.id).where(AgentRun.status == "queued").order_by(AgentRun.id))
    )


def cancel(run: AgentRun, now: datetime) -> None:
    """Stops a run: one that has not started never will, and one that is going stops before its
    next step."""
    if run.status == "queued":
        run.status = "cancelled"
        run.finished_at = now
    elif run.status == "running":
        run.cancel_requested = True


def interrupted(db: Session, now: datetime) -> int:
    """Ends the runs that were going when the worker stopped, which nobody is running now."""
    stopped = db.scalars(select(AgentRun).where(AgentRun.status == "running")).all()
    for run in stopped:
        run.status = "failed"
        run.finished_at = now
        run.node = None
        run.error = "It was interrupted when AresGate stopped."
    return len(stopped)


def prune(db: Session, now: datetime) -> None:
    """Forgets the runs that are over and older than they are kept, with their steps, and the
    suggestions that are old."""
    db.execute(
        delete(AgentRun).where(
            AgentRun.finished_at.is_not(None), AgentRun.finished_at < now - RETENTION
        )
    )
    proposals.forget(db, now)
