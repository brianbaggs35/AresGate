"""Threats: what is a real threat and what is background noise, the kinds of incident that
background is made of, and what an AI and the owner make of each kind. For someone signed in.

The incidents themselves are listed and shown by ``/incidents`` (ask for a lane there); this is the
view that tells the lanes apart and lets the owner overrule how a whole kind is treated."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from sqlalchemy import select

from app import dashboard
from app.ai import families as judging
from app.api import incidents as incident_api
from app.api.ai import AiContext
from app.api.dashboard import SEVERITY_NAMES, SeverityName, WindowOut
from app.api.deps import Db, SignedIn, record_audit, signed_in
from app.audit import Action, Outcome
from app.events.event import Severity
from app.incidents import attention, filters, response
from app.incidents.attention import Lane
from app.models import Incident, IncidentFamily, utcnow
from app.threats import calls, drift, overview
from app.threats import settings as threat_settings

router = APIRouter(prefix="/threats", tags=["threats"], dependencies=[Depends(signed_in)])

FamilyId = Annotated[int, Path(ge=1, le=2**63 - 1)]
Judged = Literal["ai", "owner", "waiting"]
MAX_PAGE = 100
SAMPLE = 20
NO_SUCH_KIND = "There's no such kind of incident."


class FunnelOut(BaseModel):
    """From what programs reported to what needs a person."""

    reports: int
    duplicates: int
    repeats: int
    alerts: int
    incidents: int
    families: int
    threats: int
    suspects: int
    background: int
    muted: int
    handled: int


class CoverageOut(BaseModel):
    """How many of the kinds of incident that are going on an AI has judged."""

    families: int
    judged: int
    owned: int
    waiting: int


class FamilyOut(incident_api.FamilyBrief):
    """A kind of incident and what the incidents of it that are going on come to."""

    alerts: int
    # How many different addresses (or rules) they are about.
    actors: int
    worst: SeverityName
    first_seen_at: AwareDatetime
    last_seen_at: AwareDatetime
    threats: int
    suspects: int
    background: int
    # When the kind was first seen to differ from what it was when it was judged, and how, in
    # words, a line each (see app/threats/drift.py): none while it is as it was.
    changed_at: AwareDatetime | None
    changes: list[str]


class FamilyPage(BaseModel):
    total: int
    items: list[FamilyOut]


class OverviewOut(BaseModel):
    window: WindowOut
    funnel: FunnelOut
    coverage: CoverageOut
    # Whether an AI is watching, and the number a threat takes (the owner's settings).
    watching: bool
    threat_from: int
    # The kinds of incident there are most of, so a person can see what was set aside.
    families: list[FamilyOut]


class FamilyDetail(FamilyOut):
    # Who judged it, with what, and why it is what it is.
    provider: str | None
    model: str | None
    owner_call_at: AwareDatetime | None
    why: list[str]
    # The incidents of it going on, the most recent first (``total`` is how many there are).
    sample: list[incident_api.IncidentOut]


class CallIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # background: set the kind aside. watch: never set it aside. None: take the owner's word back.
    call: Literal["background", "watch"] | None = Field(default=None)


class JudgeOut(BaseModel):
    """What came of asking the AI about a kind of incident: when it could not be asked, ``reason``
    says why in words for whoever asked, and the family is as it was."""

    ok: bool
    reason: str | None
    family: FamilyDetail


def _family(item: overview.Kind, incidents: int | None = None) -> FamilyOut:
    brief = incident_api.brief_of(item.family, item.incidents if incidents is None else incidents)
    return FamilyOut(
        **brief.model_dump(),
        alerts=item.alerts,
        actors=item.actors,
        worst=SEVERITY_NAMES[item.worst],
        first_seen_at=item.first_at,
        last_seen_at=item.last_at,
        threats=item.threats,
        suspects=item.suspects,
        background=item.background,
        changed_at=item.family.changed_at,
        changes=drift.lines_of(item.family),
    )


def _why(family: IncidentFamily) -> list[str]:
    """What is behind a kind's call, a fact to a line."""
    lines: list[str] = []
    if family.owner_call == "background":
        lines.append("You said this kind is background, so every incident of it is set aside.")
    elif family.owner_call == "watch":
        lines.append("You asked to keep an eye on this kind, so none of it is set aside.")
    if family.ai_class is not None:
        lines.append(
            f"The AI judged it {family.ai_class}, {family.ai_confidence}% sure"
            + (f": {family.ai_reason}" if family.ai_reason else ".")
        )
    elif family.owner_call is None:
        lines.append("No AI has judged this kind yet.")
    return lines


def _kind(db: Db, family_id: int) -> overview.Kind:
    floor = filters.load(db).confidence_floor
    found = overview.kinds(db, floor, threat_settings.load(db), limit=1, family_id=family_id).items
    if found:
        return found[0]
    family = db.get(IncidentFamily, family_id)
    if family is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NO_SUCH_KIND)
    # Nothing of it is going on now.
    now = utcnow()
    return overview.Kind(family, 0, 0, 0, Severity.INFO, family.created_at, now, 0, 0, 0)


def _detail(db: Db, family_id: int) -> FamilyDetail:
    item = _kind(db, family_id)
    judgement = incident_api.Judging(filters.load(db).confidence_floor, threat_settings.load(db))
    members = list(
        db.scalars(
            select(Incident)
            .where(Incident.family_id == family_id, Incident.status.in_(attention.ACTIVE))
            .order_by(Incident.last_seen_at.desc(), Incident.id.desc())
            .limit(SAMPLE)
        )
    )
    done = response.of(db, members)
    family = item.family
    return FamilyDetail(
        **_family(item).model_dump(),
        provider=family.provider,
        model=family.model,
        owner_call_at=family.owner_call_at,
        why=_why(family),
        sample=[
            incident_api._incident(incident, done[incident.id], judgement)  # pyright: ignore[reportPrivateUsage]
            for incident in members
        ],
    )


@router.get("/overview")
def get_overview(
    db: Db,
    window: Annotated[Literal["24h", "7d"], Query(description="How far back to look.")] = "24h",
) -> OverviewOut:
    """How the reports of the window came to threats, suspects and background, and the kinds of
    incident there are most of."""
    now = utcnow()
    win = dashboard.window(window, now)
    floor = filters.load(db).confidence_floor
    tuning = threat_settings.load(db)
    found = overview.funnel(db, win, floor, tuning)
    covered = overview.coverage(db)
    top = overview.kinds(db, floor, tuning, limit=6)
    return OverviewOut(
        window=WindowOut(
            key=win.key,
            start=win.start,
            end=win.end,
            buckets=win.buckets(),
            traffic_buckets=win.buckets(win.traffic_bucket),
        ),
        funnel=FunnelOut(**vars(found)),
        coverage=CoverageOut(**vars(covered)),
        watching=threat_settings.watching(db),
        threat_from=tuning.threat_from,
        families=[_family(item) for item in top.items],
    )


@router.get("/families")
def list_families(
    db: Db,
    lane: Annotated[
        Literal["threat", "suspect", "background"] | None,
        Query(description="Only kinds with an incident in this lane."),
    ] = None,
    judged: Annotated[
        Judged | None,
        Query(description="Only those an AI has judged, the owner has called, or neither yet."),
    ] = None,
    q: Annotated[str, Query(max_length=100, description="Words in what the kind says.")] = "",
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> FamilyPage:
    """The kinds of incident that have one going on, those with threats first."""
    found = overview.kinds(
        db,
        filters.load(db).confidence_floor,
        threat_settings.load(db),
        lane=Lane(lane) if lane else None,
        judged=judged,
        text=q.strip(),
        limit=limit,
        offset=offset,
    )
    return FamilyPage(total=found.total, items=[_family(item) for item in found.items])


@router.get("/families/{family_id}")
def get_family(family_id: FamilyId, db: Db) -> FamilyDetail:
    """One kind of incident, what is thought of it and the incidents of it going on."""
    return _detail(db, family_id)


@router.put("/families/{family_id}/call")
def call_family(
    family_id: FamilyId,
    body: CallIn,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
) -> FamilyDetail:
    """Says what the owner makes of a whole kind: background (all of it is set aside), watch (none
    of it is) or nothing, which leaves it to the AI. Their word comes before the AI's. It is told to
    every incident of the kind at once."""
    family = db.get(IncidentFamily, family_id)
    if family is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NO_SUCH_KIND)
    if family.owner_call != body.call:
        record_audit(
            db,
            request,
            Action.THREATS_FAMILY_CALLED,
            Outcome.SUCCESS,
            user=auth.user,
            detail={
                "family": family.id,
                "call": body.call or "none",
                "from_call": family.owner_call or "none",
            },
        )
        family.owner_call = body.call
        family.owner_call_at = utcnow() if body.call else None
        db.flush()
        calls.sync(db, family_id=family.id)
        db.commit()
    return _detail(db, family_id)


@router.post("/families/{family_id}/judge")
def judge_family(
    family_id: FamilyId,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
    context: AiContext,
) -> JudgeOut:
    """Has the AI judge a kind of incident now, and keeps what it says. It sees what Settings > AI
    allows. It can take a minute."""
    if db.get(IncidentFamily, family_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NO_SUCH_KIND)
    outcome = judging.ask_now(db, context, [family_id])
    ok = isinstance(outcome, judging.Judged)
    record_audit(
        db,
        request,
        Action.THREATS_FAMILY_JUDGED,
        Outcome.SUCCESS if ok else Outcome.FAILURE,
        user=auth.user,
        detail={"family": family_id},
    )
    db.commit()
    return JudgeOut(
        ok=ok,
        reason=None if ok else outcome.reason,
        family=_detail(db, family_id),
    )
