"""The incidents the threat hunter has flagged: those a finding of its last finished run, that is
serious enough to need the owner, names as what it is based on.

An incident is not changed by it. The hunter only reads, so what it says is shown beside the
incident (on its card, its page and the Threats page, and ``hunted:yes`` finds them), with what it
said and what to do, and the owner decides. A finding stays only as long as it is in the hunter's
last run, so an incident it no longer names stops being flagged by itself.
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final, cast

from sqlalchemy import ColumnElement, String, and_, exists, func, or_, select
from sqlalchemy import cast as sql_cast
from sqlalchemy.dialects.postgresql import JSONPATH
from sqlalchemy.orm import Session, aliased

from app.agents import catalog
from app.agents.attention import WORTH, latest
from app.incidents.attention import ACTIVE
from app.models import Agent, AgentRun, Incident

# What a finding says of an incident: its cites, as the chat names them, are {kind, key}.
KIND: Final = "incident"
_SEVERITIES: Final = " || ".join(f'@.severity == "{name}"' for name in WORTH)
_PATH: Final = f'$[*] ? ({_SEVERITIES}).cites[*] ? (@.kind == "{KIND}" && @.key == $key)'


@dataclass(frozen=True)
class Flag:
    """One finding of the threat hunter that names an incident, and the run that made it."""

    agent_id: int
    agent_name: str
    run_id: int
    finished_at: datetime
    severity: str
    title: str
    action: str
    confidence: str


def clause() -> ColumnElement[bool]:
    """Whether the hunter's last finished run has a finding worth acting on that names the
    incident (for a search over ``Incident``)."""
    run = aliased(AgentRun)
    newer = (
        exists()
        .where(
            AgentRun.agent_id == run.agent_id,
            AgentRun.status == "succeeded",
            or_(
                AgentRun.finished_at > run.finished_at,
                and_(AgentRun.finished_at == run.finished_at, AgentRun.id > run.id),
            ),
        )
        .correlate(run)
    )
    return (
        exists()
        .where(
            Agent.id == run.agent_id,
            Agent.template == catalog.THREAT_HUNTER.key,
            run.status == "succeeded",
            run.finished_at.is_not(None),
            ~newer,
            func.jsonb_path_exists(
                run.findings,
                sql_cast(_PATH, JSONPATH),
                func.jsonb_build_object("key", sql_cast(Incident.id, String)),
            ),
        )
        .correlate(Incident)
    )


def of_incidents(db: Session, ids: Sequence[int]) -> dict[int, list[Flag]]:
    """What the hunter flagged, by incident, for these incidents."""
    wanted = {str(each) for each in ids}
    found: dict[int, list[Flag]] = defaultdict(list)
    if not wanted:
        return found
    for agent, run in latest(db):
        if agent.template != catalog.THREAT_HUNTER.key or run.finished_at is None:
            continue
        for item in run.findings:
            if item.get("severity") not in WORTH:
                continue
            raised = Flag(
                agent.id,
                agent.name,
                run.id,
                run.finished_at,
                str(item.get("severity")),
                str(item.get("title", "")),
                str(item.get("action") or ""),
                str(item.get("confidence") or "medium"),
            )
            cites = item.get("cites")
            for cite in cast("list[object]", cites) if isinstance(cites, list) else []:
                named = cast("dict[str, str]", cite) if isinstance(cite, dict) else {}
                if named.get("kind") == KIND and named.get("key") in wanted:
                    found[int(named["key"])].append(raised)
    return found


def going_on(db: Session, limit: int) -> tuple[int, list[tuple[Incident, Flag]]]:
    """The incidents going on that the hunter has flagged, the most serious and most recent first
    (the most serious of what it said of each), and how many there are in all."""
    where = (Incident.status.in_(ACTIVE), clause())
    total = db.scalar(select(func.count()).select_from(Incident).where(*where)) or 0
    shown = list(
        db.scalars(
            select(Incident)
            .where(*where)
            .order_by(Incident.severity.desc(), Incident.last_seen_at.desc(), Incident.id)
            .limit(limit)
        )
    )
    said = of_incidents(db, [incident.id for incident in shown])
    return total, [
        (incident, min(said[incident.id], key=lambda each: WORTH.index(each.severity)))
        for incident in shown
        if said[incident.id]
    ]
