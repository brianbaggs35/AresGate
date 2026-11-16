"""What the agents hand to each other and to the owner: the hand-offs between agents, the steps the
response planner proposes (which the owner approves or dismisses) and the timeline of an
investigation, for a run or an incident. For someone signed in. Nothing here makes an agent
change anything: approving a step records the owner's decision."""

from datetime import datetime, timedelta
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import AwareDatetime, BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import catalog, handoffs, plans, timeline
from app.api.deps import Db, SignedIn, record_audit, signed_in
from app.audit import Action, Outcome
from app.models import Agent, AgentHandoff, AgentPlanStep, AgentRun
from app.models.base import utcnow

router = APIRouter(prefix="/agents", tags=["agents"], dependencies=[Depends(signed_in)])

# How many hand-offs and steps are listed, and how far back the decided ones are.
SHOWN = 30
RECENT_DAYS = 30
GONE = "An agent that is gone"


class HandoffOut(BaseModel):
    """One request from an agent to another kind of agent, and whether it was made."""

    id: int
    run_id: int
    from_agent_id: int
    from_agent: str
    to_kind: str
    to_agent_id: int | None
    to_agent: str
    to_run_id: int | None
    subject: str
    incident_id: int | None
    reason: str
    status: Literal["queued", "refused"]
    refusal: str | None
    depth: int
    created_at: AwareDatetime


class HandoffList(BaseModel):
    handoffs: list[HandoffOut]
    # The limits, so that the page can say what they are.
    max_depth: int
    per_day: int
    made_today: int


class StepOut(BaseModel):
    """One step the response planner proposes, and what the owner decided."""

    id: int
    agent_id: int
    agent_name: str
    run_id: int | None
    title: str
    detail: str
    risk: str
    incident_id: int | None
    status: Literal["pending", "approved", "dismissed"]
    created_at: AwareDatetime
    decided_at: AwareDatetime | None


class StepList(BaseModel):
    # Waiting for the owner, the newest first, and what was decided lately.
    pending: list[StepOut]
    recent: list[StepOut]


class MomentOut(BaseModel):
    at: AwareDatetime
    agent_id: int | None
    agent: str
    run_id: int | None
    kind: timeline.Kind
    title: str
    detail: str


def _names(db: Session) -> dict[int, str]:
    return {agent.id: agent.name for agent in db.scalars(select(Agent))}


def _handoff_out(item: AgentHandoff, names: dict[int, str]) -> HandoffOut:
    return HandoffOut(
        id=item.id,
        run_id=item.run_id,
        from_agent_id=item.from_agent_id,
        from_agent=names.get(item.from_agent_id, GONE),
        to_kind=item.to_kind,
        to_agent_id=item.to_agent_id,
        to_agent=names.get(item.to_agent_id or 0) or catalog.name_of(item.to_kind),
        to_run_id=item.to_run_id,
        subject=item.subject,
        incident_id=item.incident_id,
        reason=item.reason,
        status=cast("Literal['queued', 'refused']", item.status),
        refusal=item.refusal,
        depth=item.depth,
        created_at=item.created_at,
    )


def _step_out(item: AgentPlanStep, names: dict[int, str]) -> StepOut:
    return StepOut(
        id=item.id,
        agent_id=item.agent_id,
        agent_name=names.get(item.agent_id, GONE),
        run_id=item.run_id,
        title=item.title,
        detail=item.detail,
        risk=item.risk,
        incident_id=item.incident_id,
        status=cast("Literal['pending', 'approved', 'dismissed']", item.status),
        created_at=item.created_at,
        decided_at=item.decided_at,
    )


@router.get("/handoffs")
def list_handoffs(db: Db) -> HandoffList:
    """What the agents asked each other for in the last week, the newest first."""
    now = utcnow()
    names = _names(db)
    rows = db.scalars(
        select(AgentHandoff)
        .where(AgentHandoff.created_at >= now - timedelta(days=7))
        .order_by(AgentHandoff.id.desc())
        .limit(SHOWN)
    ).all()
    return HandoffList(
        handoffs=[_handoff_out(item, names) for item in rows],
        max_depth=handoffs.MAX_DEPTH,
        per_day=handoffs.PER_DAY,
        made_today=handoffs.made_today(db, now),
    )


@router.get("/plan-steps")
def list_steps(db: Db, incident_id: Annotated[int | None, Query(ge=1)] = None) -> StepList:
    """The steps the response planner proposes that wait for the owner, and what was decided
    lately, for all of them or for one incident."""
    names = _names(db)
    scope = [AgentPlanStep.incident_id == incident_id] if incident_id is not None else []
    waiting = db.scalars(
        select(AgentPlanStep)
        .where(AgentPlanStep.status == "pending", *scope)
        .order_by(AgentPlanStep.id.desc())
        .limit(SHOWN)
    ).all()
    decided = db.scalars(
        select(AgentPlanStep)
        .where(
            AgentPlanStep.status != "pending",
            AgentPlanStep.decided_at >= utcnow() - timedelta(days=RECENT_DAYS),
            *scope,
        )
        .order_by(AgentPlanStep.decided_at.desc(), AgentPlanStep.id.desc())
        .limit(SHOWN)
    ).all()
    return StepList(
        pending=[_step_out(item, names) for item in waiting],
        recent=[_step_out(item, names) for item in decided],
    )


def _decide(db: Db, request: Request, auth: SignedIn, step_id: int, approve: bool) -> StepOut:
    found = db.get(AgentPlanStep, step_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There is no such step.")
    now: datetime = utcnow()
    try:
        plans.decide(found, approve, now)
    except plans.Settled as settled:
        raise HTTPException(status.HTTP_409_CONFLICT, str(settled)) from settled
    record_audit(
        db,
        request,
        Action.AGENT_PLAN_APPROVED if approve else Action.AGENT_PLAN_DISMISSED,
        Outcome.SUCCESS,
        user=auth.user,
        detail={
            "step": found.id,
            "agent": found.agent_id,
            "incident": found.incident_id or 0,
            "title": found.title,
        },
    )
    out = _step_out(found, _names(db))
    db.commit()
    return out


@router.post("/plan-steps/{step_id}/approve")
def approve_step(
    step_id: int,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
) -> StepOut:
    """Records that the owner will take a step, and puts it on its incident as a task."""
    return _decide(db, request, auth, step_id, True)


@router.post("/plan-steps/{step_id}/dismiss")
def dismiss_step(
    step_id: int,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
) -> StepOut:
    """Turns a step down, so that the planner does not propose it again."""
    return _decide(db, request, auth, step_id, False)


def _moments(items: list[timeline.Moment]) -> list[MomentOut]:
    return [MomentOut(**item.__dict__) for item in items]


@router.get("/timeline")
def incident_timeline(db: Db, incident_id: Annotated[int, Query(ge=1)]) -> list[MomentOut]:
    """Which agents looked at an incident, what they asked of each other, what they concluded and
    what was decided about it, oldest first."""
    return _moments(timeline.for_incident(db, incident_id))


@router.get("/{agent_id}/runs/{run_id}/timeline")
def run_timeline(agent_id: int, run_id: int, db: Db) -> list[MomentOut]:
    """What one run did, who asked it and whom it asked, oldest first."""
    run = db.get(AgentRun, run_id)
    if run is None or run.agent_id != agent_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There is no such run.")
    return _moments(timeline.for_run(db, run))
