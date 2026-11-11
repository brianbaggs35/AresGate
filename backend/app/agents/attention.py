"""What the agents together say needs the owner: the findings of each agent's last finished run
that are worth acting on, the most serious first, and the briefing, if an agent writes one. A
finding stays here only as long as it is in the last run of the agent that raised it, so one the
agent no longer reports goes by itself."""

from dataclasses import dataclass
from datetime import datetime
from typing import Final

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from app.agents import catalog, probe
from app.models import Agent, AgentRun

# How serious a finding has to be to be listed, and how many are.
WORTH: Final = ("critical", "high", "medium")
SHOWN: Final = 8


@dataclass(frozen=True)
class Item:
    """One finding that needs the owner, and which agent run said so."""

    agent_id: int
    agent_name: str
    icon: str
    run_id: int
    finished_at: datetime
    severity: str
    title: str
    detail: str
    action: str
    status: str


@dataclass(frozen=True)
class Briefing:
    """What the daily briefing agent said the last time it finished."""

    agent_id: int
    agent_name: str
    run_id: int
    finished_at: datetime
    summary: str


@dataclass(frozen=True)
class Attention:
    items: list[Item]
    # How many findings need the owner in all, which may be more than the items shown.
    total: int
    briefing: Briefing | None


def _latest(db: Session) -> list[tuple[Agent, AgentRun]]:
    """Each agent's last run that finished well, if it has one."""
    latest = (
        select(AgentRun)
        .ext(distinct_on(AgentRun.agent_id))
        .where(AgentRun.status == "succeeded", AgentRun.finished_at.is_not(None))
        .order_by(AgentRun.agent_id, AgentRun.finished_at.desc(), AgentRun.id.desc())
        .subquery()
    )
    runs = db.scalars(select(AgentRun).join(latest, latest.c.id == AgentRun.id)).all()
    agents = {agent.id: agent for agent in db.scalars(select(Agent))}
    return [(agents[run.agent_id], run) for run in runs if run.agent_id in agents]


def gather(db: Session) -> Attention:
    items: list[Item] = []
    briefing: Briefing | None = None
    for agent, run in _latest(db):
        template = catalog.template(agent.template)
        finished = run.finished_at
        if finished is None:  # pragma: no cover - the query only takes runs that finished
            continue
        writes = template is not None and template.key == catalog.DAILY_BRIEFING.key
        if writes and run.summary and (briefing is None or finished > briefing.finished_at):
            briefing = Briefing(agent.id, agent.name, run.id, finished, run.summary)
        items += [
            Item(
                agent_id=agent.id,
                agent_name=agent.name,
                icon=template.icon if template else "bot",
                run_id=run.id,
                finished_at=finished,
                severity=str(found.get("severity")),
                title=str(found.get("title", "")),
                detail=str(found.get("detail", "")),
                action=str(found.get("action") or ""),
                status="ongoing" if found.get("status") == "ongoing" else "new",
            )
            for found in run.findings
            if found.get("severity") in WORTH
        ]
    items.sort(
        key=lambda item: (probe.SEVERITIES.index(item.severity), -item.finished_at.timestamp())
    )
    return Attention(items[:SHOWN], len(items), briefing)
