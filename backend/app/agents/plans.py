"""The steps the response planner proposes, which wait for the owner.

The planner only advises. Each step it writes (what to do, and what that risks) is kept here as a
proposal; the owner approves or dismisses it on the Agents page. Approving records the decision,
and, for a step that is about an incident, puts it on that incident as a response task the owner
carries out themselves: nothing here, and no agent, changes anything on the network. A step that
was decided is not proposed again, and the ones nobody decided on are forgotten after a month.
"""

import hashlib
import re
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Final, NamedTuple

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import AgentPlanStep

# How long a decided step is kept, and how long one nobody decided on waits.
DECIDED_FOR: Final = 90
WAITING_FOR: Final = 30
MAX_TITLE: Final = 200
MAX_STEPS: Final = 8


class Planned(NamedTuple):
    """One step as the model wrote it: what to do, what it risks and the incident it is about, if
    it named one the run looked at."""

    title: str
    detail: str
    risk: str
    incident_id: int | None


class Settled(Exception):
    """The step has been decided already, and the message says how."""


def key_of(title: str, incident_id: int | None) -> str:
    """What makes the same step the same: its words, not their capitals or punctuation, and the
    incident it is about."""
    return hashlib.sha256(
        f"{incident_id}|{' '.join(re.findall(r'[a-z0-9]+', title.lower()))}".encode()
    ).hexdigest()[:40]


def record(
    db: Session, agent_id: int, run_id: int, planned: Sequence[Planned], now: datetime
) -> list[AgentPlanStep]:
    """Keeps what a run planned as steps waiting for the owner, except what was proposed before,
    however it went. Gives back the new ones."""
    known = set(db.scalars(select(AgentPlanStep.key).where(AgentPlanStep.agent_id == agent_id)))
    made: list[AgentPlanStep] = []
    for item in planned[:MAX_STEPS]:
        key = key_of(item.title, item.incident_id)
        if key in known:
            continue
        known.add(key)
        step = AgentPlanStep(
            agent_id=agent_id,
            run_id=run_id,
            key=key,
            title=item.title[:MAX_TITLE],
            detail=item.detail,
            risk=item.risk,
            incident_id=item.incident_id,
            status="pending",
            created_at=now,
        )
        db.add(step)
        made.append(step)
    db.flush()
    return made


def decide(step: AgentPlanStep, approve: bool, now: datetime) -> None:
    """Approves or dismisses a step. A step is decided once."""
    if step.status != "pending":
        raise Settled(f"This step has already been {step.status}.")
    step.status = "approved" if approve else "dismissed"
    step.decided_at = now


def forget(db: Session, now: datetime) -> None:
    """Forgets steps decided long ago, and ones nobody has decided on for a month."""
    db.execute(
        delete(AgentPlanStep).where(
            AgentPlanStep.status != "pending",
            AgentPlanStep.decided_at < now - timedelta(days=DECIDED_FOR),
        )
    )
    db.execute(
        delete(AgentPlanStep).where(
            AgentPlanStep.status == "pending",
            AgentPlanStep.created_at < now - timedelta(days=WAITING_FOR),
        )
    )
