"""Agents: what the owner makes to look at the network for them, how each is doing and what it
found (see ``app/agents``). For someone signed in."""

from collections.abc import Callable
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents import catalog, graph, proposals, readiness, service
from app.agents import settings as agent_settings
from app.ai import catalog as ai_catalog
from app.ai import gateway, limits
from app.api.ai_usage import LimitOut
from app.api.deps import Db, SignedIn, record_audit, signed_in
from app.audit import Action, Outcome
from app.integrations.registry import SettingsError
from app.models import (
    MIN_INTERVAL_MINUTES,
    Agent,
    AgentProposal,
    AgentRun,
    AgentStep,
    AiProvider,
)
from app.models.base import utcnow

router = APIRouter(prefix="/agents", tags=["agents"], dependencies=[Depends(signed_in)])

MAX_INTERVAL_MINUTES = 7 * 24 * 60
RUNS_SHOWN = 30
# How many suggestions are listed, of each kind.
PROPOSALS_SHOWN = 30
# How many of an agent's last runs a card draws, and how far back its counts go.
RECENT = 14
WEEK = timedelta(days=7)
# How far back what the agents used of the AI is counted, which is how long a run is kept.
USAGE_DAYS = 30

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Interval = Annotated[int, Field(ge=MIN_INTERVAL_MINUTES, le=MAX_INTERVAL_MINUTES)]
# What an agent is doing: going, waiting to go, doing nothing, or kept from running by itself.
State = Literal["running", "queued", "idle", "paused"]
Status = Literal["queued", "running", "succeeded", "failed", "cancelled"]


class CheckOut(BaseModel):
    key: str
    ok: bool
    text: str
    # What to do when it is not there, and where in the web app to do it.
    fix: str
    link: str


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
    # What the kind needs to be useful, and whether each is there, and the steps to set it up.
    checks: list[CheckOut]
    ready: bool
    setup: list[str]
    # Whether it suggests tidying incidents, which the owner applies and can take back.
    proposes: bool


class EdgeOut(BaseModel):
    source: str
    target: str
    conditional: bool


class UsageOut(BaseModel):
    """What the AI was asked and what it cost: how many runs, requests, tokens (those in the cache
    among them) and millionths of a US dollar, and how many requests there was no price for."""

    runs: int
    calls: int
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    cost_micros: int
    unpriced_calls: int


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
    # What it used of the AI, and who answered last.
    usage: UsageOut
    provider: str | None
    model: str | None


class ProposalOut(BaseModel):
    """Something the cleanup agent suggests tidying, and what became of it."""

    id: int
    agent_id: int
    agent_name: str
    kind: str
    title: str
    detail: str
    # What is done to the incidents: dismiss them, resolve them or give them a verdict.
    action: str
    incident_ids: list[int]
    keep_id: int | None
    confidence: int
    status: Literal["pending", "applied", "dismissed", "undone"]
    decided_by: Literal["owner", "agent"] | None
    created_at: AwareDatetime
    decided_at: AwareDatetime | None


class ProposalList(BaseModel):
    # Waiting for the owner, the surest first, and what was decided lately, newest first.
    pending: list[ProposalOut]
    recent: list[ProposalOut]


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
    # What it used of the AI over the last 30 days.
    usage: UsageOut
    # How many of its suggestions wait for the owner.
    proposals: int


class FindingOut(BaseModel):
    severity: str
    title: str
    detail: str
    cites: list[dict[str, str]]
    # Whether the agent's last run said the same: new, or ongoing.
    status: str


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


class DayOut(BaseModel):
    day: date
    runs: int
    tokens: int
    cost_micros: int


class AgentDetail(AgentOut):
    template_info: TemplateOut
    runs: list[RunOut]
    graph: list[EdgeOut]
    # Each of the last 30 days, oldest first, with what the agent used of the AI.
    days: list[DayOut]
    # What it suggests tidying, and what was decided lately.
    suggestions: ProposalList


class Overview(BaseModel):
    agents: list[AgentOut]
    templates: list[TemplateOut]
    # Why the AI would not be asked now, or None if it would be. Agents still collect without it.
    ai: str | None
    # What all the agents used of the AI over the last 30 days, and the limits on what they spend.
    usage: UsageOut
    limits: list[LimitOut]
    # How many suggestions of the cleanup agents wait for the owner.
    proposals: int


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


def _template_out(db: Session, item: catalog.Template, now: datetime) -> TemplateOut:
    found = readiness.checks(db, now, item)
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
        checks=[
            CheckOut(key=check.key, ok=check.ok, text=check.text, fix=check.fix, link=check.link)
            for check in found
        ],
        ready=readiness.ready(found),
        setup=list(item.setup),
        proposes=item.proposes,
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
        usage=UsageOut(
            runs=1,
            calls=run.calls,
            input_tokens=run.input_tokens,
            output_tokens=run.output_tokens,
            cached_tokens=run.cached_tokens,
            cost_micros=run.cost_micros,
            unpriced_calls=run.unpriced_calls,
        ),
        provider=run.provider,
        model=run.model,
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


def _usage(db: Session, now: datetime, agent_id: int | None = None) -> UsageOut:
    """What the runs that ended in the last 30 days used of the AI, of one agent or of all."""
    query = select(
        func.count(),
        func.coalesce(func.sum(AgentRun.calls), 0),
        func.coalesce(func.sum(AgentRun.input_tokens), 0),
        func.coalesce(func.sum(AgentRun.output_tokens), 0),
        func.coalesce(func.sum(AgentRun.cached_tokens), 0),
        func.coalesce(func.sum(AgentRun.cost_micros), 0),
        func.coalesce(func.sum(AgentRun.unpriced_calls), 0),
    ).where(AgentRun.finished_at >= now - timedelta(days=USAGE_DAYS))
    if agent_id is not None:
        query = query.where(AgentRun.agent_id == agent_id)
    runs, calls, received, written, cached, cost, unpriced = db.execute(query).one()
    return UsageOut(
        runs=runs,
        calls=int(calls),
        input_tokens=int(received),
        output_tokens=int(written),
        cached_tokens=int(cached),
        cost_micros=int(cost),
        unpriced_calls=int(unpriced),
    )


def _days(db: Session, now: datetime, agent_id: int) -> list[DayOut]:
    """Each of the last 30 days (UTC), oldest first, with what the agent's runs of that day used
    of the AI."""
    since = now - timedelta(days=USAGE_DAYS - 1)
    day = func.date(func.timezone("UTC", AgentRun.finished_at))
    rows = db.execute(
        select(
            day,
            func.count(),
            func.coalesce(
                func.sum(AgentRun.input_tokens + AgentRun.output_tokens + AgentRun.cached_tokens), 0
            ),
            func.coalesce(func.sum(AgentRun.cost_micros), 0),
        )
        .where(
            AgentRun.agent_id == agent_id,
            AgentRun.finished_at
            >= datetime(since.year, since.month, since.day, tzinfo=since.tzinfo),
        )
        .group_by(day)
    ).all()
    found = {when: (runs, int(tokens), int(cost)) for when, runs, tokens, cost in rows}
    first = since.date()
    return [
        DayOut(
            day=first + timedelta(days=offset),
            runs=found.get(first + timedelta(days=offset), (0, 0, 0))[0],
            tokens=found.get(first + timedelta(days=offset), (0, 0, 0))[1],
            cost_micros=found.get(first + timedelta(days=offset), (0, 0, 0))[2],
        )
        for offset in range(USAGE_DAYS)
    ]


def _waiting(db: Session) -> dict[int, int]:
    """How many suggestions wait for the owner, for each agent that has any."""
    rows = db.execute(
        select(AgentProposal.agent_id, func.count())
        .where(AgentProposal.status == "pending")
        .group_by(AgentProposal.agent_id)
    ).all()
    return dict(rows)


def _agent_out(db: Db, agent: Agent, waiting: dict[int, int] | None = None) -> AgentOut:
    suggested = _waiting(db) if waiting is None else waiting
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
        usage=_usage(db, utcnow(), agent.id),
        proposals=suggested.get(agent.id, 0),
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


class AskingOut(BaseModel):
    """Who the agents ask now: the provider and its model, and whether it charges by the token."""

    provider: str
    label: str
    model: str
    charges: bool


class AgentSettingsOut(BaseModel):
    # Which AI the agents ask: what Settings > AI chose, one of their own, or none.
    ai_source: Literal["shared", "own", "off"]
    provider: str | None
    model: str | None
    # Whether the cleanup agent only suggests tidying, or does the surest of it too.
    cleanup_mode: Literal["suggest", "auto"]
    # Who they ask now, or None with the reason why not.
    asking: AskingOut | None
    reason: str | None
    limits: list[LimitOut]


class AgentSettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ai_source: Literal["shared", "own", "off"]
    provider: str | None = Field(default=None, max_length=32)
    model: str | None = Field(default=None, max_length=128)
    # Left out, it stays as it was.
    cleanup_mode: Literal["suggest", "auto"] | None = None
    # What the agents may spend, in US dollars, or None for no limit.
    daily: Annotated[Decimal | None, Field(gt=0, le=limits.MAX_DOLLARS, decimal_places=2)] = None
    monthly: Annotated[Decimal | None, Field(gt=0, le=limits.MAX_DOLLARS, decimal_places=2)] = None


def _limit_out(item: limits.Limit) -> LimitOut:
    return LimitOut(
        period=item.period,
        limit_micros=item.limit_micros,
        spent_micros=item.spent_micros,
        state=item.state,
    )


def _settings_out(db: Session, now: datetime) -> AgentSettingsOut:
    chosen = agent_settings.get(db, now)
    picked = agent_settings.pick(db, now)
    asking: AskingOut | None = None
    reason = picked.reason
    row = db.get(AiProvider, picked.provider) if picked.provider else None
    definition = ai_catalog.provider(picked.provider) if picked.provider else None
    if row is not None and definition is not None and (picked.model or row.model):
        asking = AskingOut(
            provider=definition.key,
            label=definition.label,
            model=picked.model or row.model,
            charges=definition.kind is ai_catalog.Kind.HOSTED,
        )
    elif reason is None:
        reason = "The AI provider the agents ask is gone. Choose one under Settings > Agents."
    return AgentSettingsOut(
        ai_source=cast("Literal['shared', 'own', 'off']", chosen.ai_source),
        provider=chosen.provider,
        model=chosen.model,
        cleanup_mode=cast("Literal['suggest', 'auto']", chosen.cleanup_mode),
        asking=asking,
        reason=reason,
        limits=[_limit_out(item) for item in agent_settings.status(db, now)],
    )


def _proposal_out(proposal: AgentProposal, names: dict[int, str]) -> ProposalOut:
    return ProposalOut(
        id=proposal.id,
        agent_id=proposal.agent_id,
        agent_name=names.get(proposal.agent_id, "An agent that is gone"),
        kind=proposal.kind,
        title=proposal.title,
        detail=proposal.detail,
        action=proposal.action,
        incident_ids=proposal.incident_ids,
        keep_id=proposal.keep_id,
        confidence=proposal.confidence,
        status=cast("Literal['pending', 'applied', 'dismissed', 'undone']", proposal.status),
        decided_by=cast("Literal['owner', 'agent'] | None", proposal.decided_by),
        created_at=proposal.created_at,
        decided_at=proposal.decided_at,
    )


def _suggestions(db: Session, agent_id: int | None = None) -> ProposalList:
    """What waits for the owner, the surest first, and what was decided in the last 30 days."""
    names = {agent.id: agent.name for agent in db.scalars(select(Agent))}
    scope = [AgentProposal.agent_id == agent_id] if agent_id is not None else []
    waiting = db.scalars(
        select(AgentProposal)
        .where(AgentProposal.status == "pending", *scope)
        .order_by(AgentProposal.confidence.desc(), AgentProposal.id.desc())
        .limit(PROPOSALS_SHOWN)
    ).all()
    decided = db.scalars(
        select(AgentProposal)
        .where(
            AgentProposal.status != "pending",
            AgentProposal.decided_at >= utcnow() - timedelta(days=30),
            *scope,
        )
        .order_by(AgentProposal.decided_at.desc(), AgentProposal.id.desc())
        .limit(PROPOSALS_SHOWN)
    ).all()
    return ProposalList(
        pending=[_proposal_out(item, names) for item in waiting],
        recent=[_proposal_out(item, names) for item in decided],
    )


@router.get("/proposals")
def list_proposals(db: Db) -> ProposalList:
    """What the cleanup agents suggest tidying and what was decided about it lately."""
    return _suggestions(db)


def _proposal(db: Db, proposal_id: int) -> AgentProposal:
    found = db.get(AgentProposal, proposal_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There is no such suggestion.")
    return found


def _decide(
    db: Db,
    request: Request,
    auth: SignedIn,
    proposal_id: int,
    action: Action,
    change: Callable[[AgentProposal, datetime], int],
) -> ProposalOut:
    found = _proposal(db, proposal_id)
    now = utcnow()
    try:
        changed = change(found, now)
    except proposals.Settled as settled:
        raise HTTPException(status.HTTP_409_CONFLICT, str(settled)) from settled
    record_audit(
        db,
        request,
        action,
        Outcome.SUCCESS,
        user=auth.user,
        detail={
            "proposal": found.id,
            "agent": found.agent_id,
            "kind": found.kind,
            "incidents": changed,
        },
    )
    out = _proposal_out(found, {agent.id: agent.name for agent in db.scalars(select(Agent))})
    db.commit()
    return out


@router.post("/proposals/{proposal_id}/apply")
def apply_proposal(
    proposal_id: int,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
) -> ProposalOut:
    """Does what a suggestion says, in a way that can be taken back."""
    return _decide(
        db,
        request,
        auth,
        proposal_id,
        Action.AGENT_PROPOSAL_APPLIED,
        lambda found, now: proposals.apply(db, found, "owner", now),
    )


@router.post("/proposals/{proposal_id}/dismiss")
def dismiss_proposal(
    proposal_id: int,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
) -> ProposalOut:
    """Turns a suggestion down, so that the agent does not make it again."""

    def turn_down(found: AgentProposal, now: datetime) -> int:
        proposals.dismiss(found, now)
        return 0

    return _decide(db, request, auth, proposal_id, Action.AGENT_PROPOSAL_DISMISSED, turn_down)


@router.post("/proposals/{proposal_id}/undo")
def undo_proposal(
    proposal_id: int,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
) -> ProposalOut:
    """Takes back what a suggestion did."""
    return _decide(
        db,
        request,
        auth,
        proposal_id,
        Action.AGENT_PROPOSAL_UNDONE,
        lambda found, now: proposals.undo(db, found, now),
    )


@router.get("/settings")
def get_settings(db: Db) -> AgentSettingsOut:
    """Which AI the agents ask and what they may spend."""
    return _settings_out(db, utcnow())


@router.put("/settings")
def change_settings(
    body: AgentSettingsIn,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
) -> AgentSettingsOut:
    """Chooses which AI the agents ask (the one chosen under Settings > AI, one of their own, or
    none) and what they may spend."""
    now = utcnow()
    try:
        agent_settings.save(
            db,
            source=body.ai_source,
            provider=body.provider,
            model=body.model,
            daily=body.daily,
            monthly=body.monthly,
            now=now,
            cleanup=body.cleanup_mode,
        )
    except SettingsError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            [
                {"type": "value_error", "loc": ["body", name], "msg": message}
                for name, message in error.problems.items()
            ],
        ) from error
    record_audit(
        db,
        request,
        Action.AGENT_SETTINGS_CHANGED,
        Outcome.SUCCESS,
        user=auth.user,
        detail={
            "ai_source": body.ai_source,
            "provider": body.provider or "none",
            "cleanup": body.cleanup_mode or "unchanged",
        },
    )
    out = _settings_out(db, now)
    db.commit()
    return out


@router.get("")
def list_agents(db: Db) -> Overview:
    """Every agent, what each is doing, and what one can be made from."""
    agents = db.scalars(select(Agent).order_by(Agent.created_at, Agent.id)).all()
    now = utcnow()
    waiting = _waiting(db)
    return Overview(
        agents=[_agent_out(db, agent, waiting) for agent in agents],
        templates=[_template_out(db, item, now) for item in catalog.TEMPLATES],
        ai=gateway.availability(db, now, agent_settings.PURPOSE),
        usage=_usage(db, now),
        limits=[_limit_out(item) for item in agent_settings.status(db, now)],
        proposals=sum(waiting.values()),
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
        template_info=_template_out(db, item or catalog.THREAT_HUNTER, utcnow()),
        runs=[_run_out(run) for run in runs],
        graph=[
            EdgeOut(source=e.source, target=e.target, conditional=e.conditional)
            for e in graph.structure()
        ],
        days=_days(db, utcnow(), agent.id),
        suggestions=_suggestions(db, agent.id),
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
                status="ongoing" if item.get("status") == "ongoing" else "new",
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
