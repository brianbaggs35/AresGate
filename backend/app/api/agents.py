"""Agents: what the owner makes to look at the network for them, how each is doing and what it
found (see ``app/agents``). For someone signed in."""

from datetime import timedelta
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import select

from app.agents import catalog, graph, service
from app.ai import gateway
from app.api.deps import Db, SignedIn, record_audit, signed_in
from app.audit import Action, Outcome
from app.models import MIN_INTERVAL_MINUTES, Agent, AgentRun, AgentStep
from app.models.base import utcnow

router = APIRouter(prefix="/agents", tags=["agents"], dependencies=[Depends(signed_in)])

MAX_INTERVAL_MINUTES = 7 * 24 * 60
RUNS_SHOWN = 30
# How many of an agent's last runs a card draws, and how far back its counts go.
RECENT = 14
WEEK = timedelta(days=7)

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Interval = Annotated[int, Field(ge=MIN_INTERVAL_MINUTES, le=MAX_INTERVAL_MINUTES)]
# What an agent is doing: going, waiting to go, doing nothing, or kept from running by itself.
State = Literal["running", "queued", "idle", "paused"]
Status = Literal["queued", "running", "succeeded", "failed", "cancelled"]


class TemplateOut(BaseModel):
    key: str
    name: str
    tagline: str
    description: str
    icon: str
    goal: str
    interval_minutes: int | None
    # Whether it tests the network, which it only does once allowed, and only by hand.
    active: bool
    tools: list[str]


class EdgeOut(BaseModel):
    source: str
    target: str
    conditional: bool


class RunOut(BaseModel):
    id: int
    trigger: Literal["manual", "schedule"]
    status: Status
    requested_at: AwareDatetime
    started_at: AwareDatetime | None
    finished_at: AwareDatetime | None
    # The step of the graph a running run is in.
    node: str | None
    summary: str
    # How many findings it has, and how serious the worst is.
    findings: int
    worst: str | None
    rounds: int
    error: str | None
    # Why the AI took no part, or empty if it did.
    ai: str


class AgentOut(BaseModel):
    id: int
    name: str
    template: str
    template_name: str
    icon: str
    active: bool
    goal: str
    enabled: bool
    interval_minutes: int | None
    allow_active: bool
    next_run_at: AwareDatetime | None
    created_at: AwareDatetime
    state: State
    last_run: RunOut | None
    # The outcomes of its last runs, oldest first, for a glance at how it is going.
    recent: list[Status]


class FindingOut(BaseModel):
    severity: str
    title: str
    detail: str
    cites: list[dict[str, str]]


class StepOut(BaseModel):
    seq: int
    at: AwareDatetime
    node: str
    title: str
    detail: dict[str, object]


class RunDetail(RunOut):
    findings_list: list[FindingOut]
    steps: list[StepOut]
    call_ids: list[int]


class AgentDetail(AgentOut):
    template_info: TemplateOut
    runs: list[RunOut]
    graph: list[EdgeOut]


class Overview(BaseModel):
    agents: list[AgentOut]
    templates: list[TemplateOut]
    # Why the AI would not be asked now, or None if it would be. Agents still collect without it.
    ai: str | None


class AgentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template: str
    name: Name
    goal: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] = ""
    interval_minutes: Interval | None = None
    enabled: bool = True
    allow_active: bool = False


class AgentChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name
    goal: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
    interval_minutes: Interval | None
    enabled: bool
    allow_active: bool


def _template_out(item: catalog.Template) -> TemplateOut:
    return TemplateOut(
        key=item.key,
        name=item.name,
        tagline=item.tagline,
        description=item.description,
        icon=item.icon,
        goal=item.goal,
        interval_minutes=item.interval_minutes,
        active=item.active,
        tools=list(item.asks),
    )


def _run_out(run: AgentRun) -> RunOut:
    findings = run.findings
    worst = next(
        (
            level
            for level in ("critical", "high", "medium", "low", "info")
            if any(item.get("severity") == level for item in findings)
        ),
        None,
    )
    return RunOut(
        id=run.id,
        trigger="schedule" if run.trigger == "schedule" else "manual",
        status=_status(run.status),
        requested_at=run.requested_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        node=run.node,
        summary=run.summary,
        findings=len(findings),
        worst=worst,
        rounds=run.rounds,
        error=run.error,
        ai=run.ai,
    )


def _status(value: str) -> Status:
    # The database holds only these, by a check on the column.
    return cast("Status", value)


def _state(agent: Agent, last: AgentRun | None) -> State:
    if last is not None and last.status in ("queued", "running"):
        return "queued" if last.status == "queued" else "running"
    if agent.interval_minutes is not None and not agent.enabled:
        return "paused"
    return "idle"


def _agent_out(db: Db, agent: Agent) -> AgentOut:
    runs = db.scalars(
        select(AgentRun)
        .where(AgentRun.agent_id == agent.id)
        .order_by(AgentRun.id.desc())
        .limit(RECENT)
    ).all()
    item = catalog.template(agent.template)
    last = runs[0] if runs else None
    return AgentOut(
        id=agent.id,
        name=agent.name,
        template=agent.template,
        template_name=item.name if item else agent.template,
        icon=item.icon if item else "bot",
        active=bool(item and item.active),
        goal=agent.goal,
        enabled=agent.enabled,
        interval_minutes=agent.interval_minutes,
        allow_active=agent.allow_active,
        next_run_at=agent.next_run_at,
        created_at=agent.created_at,
        state=_state(agent, last),
        last_run=_run_out(last) if last else None,
        recent=[_status(run.status) for run in reversed(runs)],
    )


def _agent(db: Db, agent_id: int) -> Agent:
    found = db.get(Agent, agent_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There is no such agent.")
    return found


def _template(key: str) -> catalog.Template:
    found = catalog.template(key)
    if found is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "That isn't a kind of agent.")
    return found


def _check(item: catalog.Template, interval_minutes: int | None) -> None:
    if item.active and interval_minutes is not None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "An agent that tests the network only runs when you start it.",
        )


@router.get("")
def list_agents(db: Db) -> Overview:
    """Every agent, what each is doing, and what one can be made from."""
    agents = db.scalars(select(Agent).order_by(Agent.created_at, Agent.id)).all()
    return Overview(
        agents=[_agent_out(db, agent) for agent in agents],
        templates=[_template_out(item) for item in catalog.TEMPLATES],
        ai=gateway.availability(db, utcnow()),
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_agent(
    body: AgentIn,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
) -> AgentOut:
    """Makes an agent from a template."""
    item = _template(body.template)
    _check(item, body.interval_minutes)
    now = utcnow()
    agent = Agent(
        name=body.name,
        template=item.key,
        goal=body.goal,
        enabled=body.enabled,
        interval_minutes=body.interval_minutes,
        allow_active=body.allow_active and item.active,
        next_run_at=service.next_run_at(body.enabled, body.interval_minutes, now),
        created_at=now,
        updated_at=now,
    )
    db.add(agent)
    db.flush()
    record_audit(
        db,
        request,
        Action.AGENT_CREATED,
        Outcome.SUCCESS,
        user=auth.user,
        detail={"agent": agent.id, "template": item.key},
    )
    db.commit()
    return _agent_out(db, agent)


@router.get("/{agent_id}")
def get_agent(agent_id: int, db: Db) -> AgentDetail:
    """One agent, with its last runs."""
    agent = _agent(db, agent_id)
    item = catalog.template(agent.template)
    out = _agent_out(db, agent)
    runs = db.scalars(
        select(AgentRun)
        .where(AgentRun.agent_id == agent.id)
        .order_by(AgentRun.id.desc())
        .limit(RUNS_SHOWN)
    ).all()
    return AgentDetail(
        **out.model_dump(),
        template_info=_template_out(item or catalog.THREAT_HUNTER),
        runs=[_run_out(run) for run in runs],
        graph=[
            EdgeOut(source=e.source, target=e.target, conditional=e.conditional)
            for e in graph.structure()
        ],
    )


@router.put("/{agent_id}")
def change_agent(
    agent_id: int,
    body: AgentChange,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
) -> AgentOut:
    """Changes an agent: its name, its instructions, its schedule and what it may do. A change to
    the schedule starts the count again from now."""
    agent = _agent(db, agent_id)
    item = catalog.template(agent.template)
    if item is not None:
        _check(item, body.interval_minutes)
    now = utcnow()
    if (agent.enabled, agent.interval_minutes) != (body.enabled, body.interval_minutes):
        agent.next_run_at = service.next_run_at(body.enabled, body.interval_minutes, now)
    agent.name = body.name
    agent.goal = body.goal
    agent.enabled = body.enabled
    agent.interval_minutes = body.interval_minutes
    agent.allow_active = body.allow_active and bool(item and item.active)
    agent.updated_at = now
    record_audit(
        db,
        request,
        Action.AGENT_CHANGED,
        Outcome.SUCCESS,
        user=auth.user,
        detail={"agent": agent.id, "template": agent.template},
    )
    db.commit()
    return _agent_out(db, agent)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agent(
    agent_id: int,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
) -> Response:
    """Removes an agent, with its runs and what they found."""
    agent = _agent(db, agent_id)
    record_audit(
        db,
        request,
        Action.AGENT_DELETED,
        Outcome.SUCCESS,
        user=auth.user,
        detail={"agent": agent.id, "template": agent.template},
    )
    db.delete(agent)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{agent_id}/runs", status_code=status.HTTP_201_CREATED)
def start_run(
    agent_id: int,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
) -> RunOut:
    """Asks for a run now. The worker starts it within a few seconds."""
    agent = _agent(db, agent_id)
    try:
        run = service.queue(db, agent, "manual", utcnow())
    except service.Busy:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This agent already has a run waiting or going."
        ) from None
    except service.NotAllowed as refused:
        raise HTTPException(status.HTTP_409_CONFLICT, str(refused)) from None
    record_audit(
        db,
        request,
        Action.AGENT_RUN_REQUESTED,
        Outcome.SUCCESS,
        user=auth.user,
        detail={"agent": agent.id, "run": run.id},
    )
    db.commit()
    return _run_out(run)


def _run(db: Db, agent_id: int, run_id: int) -> AgentRun:
    found = db.get(AgentRun, run_id)
    if found is None or found.agent_id != agent_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There is no such run.")
    return found


@router.get("/{agent_id}/runs/{run_id}")
def get_run(agent_id: int, run_id: int, db: Db) -> RunDetail:
    """One run, with every step it took so far."""
    run = _run(db, agent_id, run_id)
    steps = db.scalars(
        select(AgentStep).where(AgentStep.run_id == run.id).order_by(AgentStep.seq)
    ).all()
    return RunDetail(
        **_run_out(run).model_dump(),
        findings_list=[
            FindingOut(
                severity=str(item.get("severity", "info")),
                title=str(item.get("title", "")),
                detail=str(item.get("detail", "")),
                cites=cast("list[dict[str, str]]", item.get("cites") or []),
            )
            for item in run.findings
        ],
        steps=[
            StepOut(seq=step.seq, at=step.at, node=step.node, title=step.title, detail=step.detail)
            for step in steps
        ],
        call_ids=run.call_ids,
    )


@router.post("/{agent_id}/runs/{run_id}/cancel")
def cancel_run(
    agent_id: int,
    run_id: int,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
) -> RunOut:
    """Stops a run: one that is waiting never starts, and one that is going stops before its next
    step. A run that is over is as it was."""
    run = _run(db, agent_id, run_id)
    if run.status in service.WAITING:
        service.cancel(run, utcnow())
        record_audit(
            db,
            request,
            Action.AGENT_RUN_CANCELLED,
            Outcome.SUCCESS,
            user=auth.user,
            detail={"agent": agent_id, "run": run.id},
        )
        db.commit()
    return _run_out(run)
