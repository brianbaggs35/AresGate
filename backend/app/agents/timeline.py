"""How a conclusion was reached: who looked at what, who asked whom, and what they decided.

An investigation is spread over runs of several agents. This puts what the record says in order,
for one run or for one incident, so that the owner can follow it from the first look to what was
concluded and what was done about it. It only reads what the agents and the owner already left:
the steps of each run, the hand-offs between them, the steps the response planner proposed and
what was decided about them.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.agents import catalog
from app.models import Agent, AgentHandoff, AgentPlanStep, AgentProposal, AgentRun, AgentStep

Kind = Literal[
    "asked_by",
    "began",
    "looked",
    "thought",
    "reported",
    "concluded",
    "handoff",
    "planned",
    "decided",
    "tidy",
]
# What a step of a run is, by the node of the graph it belongs to.
NODE_KINDS: Final[dict[str, Kind]] = {
    "plan": "began",
    "act": "looked",
    "think": "thought",
    "report": "reported",
}

# The most moments one timeline holds, and how many of a run's looks an incident's timeline shows.
LIMIT: Final = 200
LOOKS: Final = 6
SHORT: Final = 300

# What an agent is called once it has been deleted.
GONE: Final = "An agent that is gone"


@dataclass(frozen=True)
class Moment:
    """One thing that happened: when, which agent (None for the owner), in which run, and what."""

    at: datetime
    agent_id: int | None
    agent: str
    run_id: int | None
    kind: Kind
    title: str
    detail: str


def _names(db: Session) -> dict[int, str]:
    return {agent.id: agent.name for agent in db.scalars(select(Agent))}


def _said(value: object) -> str:
    return (audit.clean(value, SHORT) or "") if isinstance(value, str) else ""


def _of_step(step: AgentStep, run: AgentRun, names: dict[int, str]) -> Moment:
    return Moment(
        step.at,
        run.agent_id,
        names.get(run.agent_id, GONE),
        run.id,
        NODE_KINDS.get(step.node, "reported"),
        step.title,
        _said(step.detail.get("summary")),
    )


def _handoff(handoff: AgentHandoff, names: dict[int, str]) -> Moment:
    to = names.get(handoff.to_agent_id or 0) or catalog.name_of(handoff.to_kind)
    refused = f" Refused: {handoff.refusal}" if handoff.refusal else ""
    return Moment(
        handoff.created_at,
        handoff.from_agent_id,
        names.get(handoff.from_agent_id, GONE),
        handoff.run_id,
        "handoff",
        f"Asked {to} to look into {handoff.subject}",
        _said(f"{handoff.reason}{refused}"),
    )


def _asked_by(handoff: AgentHandoff, names: dict[int, str]) -> Moment:
    by = names.get(handoff.from_agent_id, GONE)
    return Moment(
        handoff.created_at,
        handoff.to_agent_id,
        names.get(handoff.to_agent_id or 0, catalog.name_of(handoff.to_kind)),
        handoff.to_run_id,
        "asked_by",
        f"Was asked by {by} to look into {handoff.subject}",
        _said(handoff.reason),
    )


def _conclusion(run: AgentRun, names: dict[int, str], only: str | None = None) -> Moment:
    """What a run that is over concluded: its summary, or, for an incident, what it said of it."""
    findings = [
        item
        for item in run.findings
        if only is None
        or any(
            f"{cite.get('kind')} {cite.get('key')}" == only
            for cite in cast("list[dict[str, str]]", item.get("cites") or [])
        )
    ]
    if only is None:
        title, detail = _said(run.summary) or "Finished", f"{len(run.findings)} findings"
    else:
        title = "; ".join(
            f"{item.get('severity', 'info')}: {item.get('title', '')}" for item in findings
        )
        detail = _said(findings[0].get("detail")) if findings else ""
    return Moment(
        run.finished_at or run.requested_at,
        run.agent_id,
        names.get(run.agent_id, GONE),
        run.id,
        "concluded",
        _said(title),
        detail,
    )


def _plan(step: AgentPlanStep, names: dict[int, str]) -> list[Moment]:
    who = names.get(step.agent_id, GONE)
    moments = [
        Moment(
            step.created_at,
            step.agent_id,
            who,
            step.run_id,
            "planned",
            f"Proposed a step: {step.title}",
            _said(step.risk and f"Risk: {step.risk}"),
        )
    ]
    if step.decided_at is not None:
        moments.append(
            Moment(
                step.decided_at,
                None,
                "You",
                step.run_id,
                "decided",
                f"{step.status.capitalize()} the step: {step.title}",
                "",
            )
        )
    return moments


def for_run(db: Session, run: AgentRun) -> list[Moment]:
    """What one run did, who asked it and whom it asked, and what became of its steps."""
    names = _names(db)
    moments = [
        _of_step(step, run, names)
        for step in db.scalars(select(AgentStep).where(AgentStep.run_id == run.id))
    ]
    moments += [
        _handoff(item, names)
        for item in db.scalars(select(AgentHandoff).where(AgentHandoff.run_id == run.id))
    ]
    moments += [
        _asked_by(item, names)
        for item in db.scalars(select(AgentHandoff).where(AgentHandoff.to_run_id == run.id))
    ]
    for step in db.scalars(select(AgentPlanStep).where(AgentPlanStep.run_id == run.id)):
        moments += _plan(step, names)
    if run.finished_at is not None:
        moments.append(_conclusion(run, names))
    return _ordered(moments)


def for_incident(db: Session, incident_id: int) -> list[Moment]:
    """Every agent's part in one incident: the runs that cited it and what they concluded, the
    hand-offs about it, the steps planned for it and what the owner decided."""
    names = _names(db)
    cite = {"kind": "incident", "key": str(incident_id)}
    runs = db.scalars(
        select(AgentRun)
        .where(AgentRun.findings.contains([{"cites": [cite]}]))
        .order_by(AgentRun.id.desc())
        .limit(20)
    ).all()
    moments: list[Moment] = []
    for run in runs:
        looks = db.scalars(
            select(AgentStep)
            .where(AgentStep.run_id == run.id, AgentStep.node == "act")
            .order_by(AgentStep.seq)
            .limit(LOOKS)
        )
        moments += [_of_step(step, run, names) for step in looks]
        moments.append(_conclusion(run, names, f"incident {incident_id}"))
    handoffs = db.scalars(select(AgentHandoff).where(AgentHandoff.incident_id == incident_id)).all()
    moments += [_handoff(item, names) for item in handoffs]
    moments += [_asked_by(item, names) for item in handoffs if item.to_run_id is not None]
    for step in db.scalars(select(AgentPlanStep).where(AgentPlanStep.incident_id == incident_id)):
        moments += _plan(step, names)
    for tidy in db.scalars(
        select(AgentProposal).where(AgentProposal.incident_ids.contains([incident_id]))
    ):
        moments.append(
            Moment(
                tidy.created_at,
                tidy.agent_id,
                names.get(tidy.agent_id, GONE),
                tidy.run_id,
                "tidy",
                f"Suggested tidying: {tidy.title}",
                f"{tidy.status}",
            )
        )
    return _ordered(moments)


def _ordered(moments: list[Moment]) -> list[Moment]:
    """The oldest first, and no more than the limit, which are the newest."""
    return sorted(moments, key=lambda item: item.at)[-LIMIT:]
