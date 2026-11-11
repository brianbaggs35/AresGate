"""What an agent's runs say when they are read side by side: how long each finding has been
reported, and what the last run reported that this one no longer does. A finding is the same in two
runs when its words are (app/agents/graph.py ``same``)."""

from dataclasses import dataclass
from datetime import datetime
from typing import Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.graph import same
from app.models import AgentRun

# How many of an agent's earlier runs are looked back through, which bounds how long a streak
# can read.
LOOK_BACK: Final = 30


@dataclass(frozen=True)
class Gone:
    """A finding the run before reported and this one does not."""

    severity: str
    title: str


@dataclass(frozen=True)
class Streak:
    """How long a finding has been reported: since when, and in how many runs in a row."""

    since: datetime
    runs: int


def earlier(db: Session, run: AgentRun) -> list[AgentRun]:
    """The runs of the same agent that finished well before this one, the newest first."""
    return list(
        db.scalars(
            select(AgentRun)
            .where(
                AgentRun.agent_id == run.agent_id,
                AgentRun.id < run.id,
                AgentRun.status == "succeeded",
            )
            .order_by(AgentRun.id.desc())
            .limit(LOOK_BACK)
        )
    )


def _titles(run: AgentRun) -> set[str]:
    return {same(str(item.get("title", ""))) for item in run.findings}


def _when(run: AgentRun) -> datetime:
    return run.finished_at or run.requested_at


def streak(run: AgentRun, before: list[AgentRun], title: str) -> Streak:
    """How long the finding has been reported, counting back from this run until a run that did
    not report it."""
    wanted = same(title)
    since, count = _when(run), 1
    for old in before:
        if wanted not in _titles(old):
            break
        since, count = _when(old), count + 1
    return Streak(since, count)


def gone(run: AgentRun, previous: AgentRun) -> list[Gone]:
    """What the run before this one reported and this one does not."""
    now = _titles(run)
    return [
        Gone(str(item.get("severity", "info")), str(item.get("title", "")))
        for item in previous.findings
        if same(str(item.get("title", ""))) not in now
    ]
