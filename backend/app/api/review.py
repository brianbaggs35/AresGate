"""Reviewing what the AI decided: the decisions to look at, agreeing or disagreeing with them (and
why), and how much of it the owner wants to look at first. For someone signed in."""

from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app.api.dashboard import SEVERITY_NAMES, SeverityName
from app.api.deps import Db, SignedIn, record_audit, signed_in
from app.audit import Action, Outcome
from app.events.event import Severity
from app.models import ReviewSettings
from app.review import service, settings
from app.threats import calls

router = APIRouter(prefix="/review", tags=["review"], dependencies=[Depends(signed_in)])

Mode = Literal["all", "uncertain", "auto"]
Subject = Literal["incident", "family"]
State = Literal["waiting", "decided", "answered"]
Review = Literal["pending", "auto", "agreed", "disagreed"]
Kind = Literal["compromise", "attack", "probe", "noise", "unclear"]
Suggestion = Literal["not_suspicious", "low_priority", "threat"]
PAGE = 20
MAX_BULK = 100


class DecisionOut(BaseModel):
    """One thing the AI decided, and where the owner's review of it stands."""

    subject: Subject
    id: int
    # An incident, or a kind of incident: ``id`` is of the one or the other.
    review: Review
    kind: Kind
    confidence: int
    title: str
    why: str
    # What the AI suggested the owner say about it, if it did.
    suggestion: Suggestion | None
    decided_at: AwareDatetime
    reviewed_at: AwareDatetime | None
    incidents: int
    active: int
    severity: SeverityName | None
    provider: str | None
    model: str | None
    # What the owner said of it, if they gave a reason.
    reason: str | None
    # Whether it counts now: a decision that waits counts only if it raises the alarm.
    counting: bool
    # What it does, in a line.
    effect: str


class CountsOut(BaseModel):
    waiting: int
    decided: int
    answered: int


class StandingOut(BaseModel):
    """How often the owner has agreed with the AI, and whether that is enough to let it decide."""

    agreed: int
    disagreed: int
    # None until they have answered anything.
    rate: float | None
    trusted: bool
    # How many answers it takes before the AI can be called trusted, and how often they agree.
    trust_after: int
    trust_rate: float


class ReviewOut(BaseModel):
    state: State
    total: int
    items: list[DecisionOut]
    counts: CountsOut
    standing: StandingOut
    mode: Mode


class SummaryOut(BaseModel):
    waiting: int


class AnswerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: Literal["agree", "disagree", "undo"]
    reason: str | None = Field(default=None, max_length=service.MAX_REASON)
    # Of a family that was set aside: keep it so (when agreeing) or in front of the owner (when
    # not), whatever the AI says next.
    keep_kind: bool = False

    @field_validator("reason")
    @classmethod
    def _plain(cls, value: str | None) -> str | None:
        return " ".join(value.split()) or None if value else None


class ItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: Subject
    id: int = Field(ge=1)


class AgreeAllIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ItemIn] = Field(min_length=1, max_length=MAX_BULK)


class AgreedOut(BaseModel):
    agreed: int


class SettingsOut(BaseModel):
    mode: Mode
    auto_from: int
    learn: bool
    default_mode: Mode
    default_auto_from: int
    min_auto_from: int
    updated_at: AwareDatetime | None


class SettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Mode
    auto_from: int = Field(ge=settings.MIN_AUTO_FROM, le=100)
    learn: bool


def _effect(item: service.Decision) -> str:
    """What the decision does, in a line, said of what it is about."""
    quiet = item.kind in calls.QUIET
    if item.subject == "family":
        many = f"{item.active} {'incident' if item.active == 1 else 'incidents'} going on"
        if quiet:
            return f"Sets aside {many}, and any more of this kind."
        return f"Raises {many}, and any more of this kind."
    return "Sets this incident aside." if quiet else "Calls this incident a real attack."


def _decision(item: service.Decision) -> DecisionOut:
    return DecisionOut(
        subject=item.subject,
        id=item.id,
        review=cast(Review, item.review),
        kind=cast(Kind, item.kind),
        confidence=item.confidence,
        title=item.title,
        why=item.why,
        suggestion=cast(Suggestion | None, item.suggestion),
        decided_at=item.decided_at,
        reviewed_at=item.reviewed_at,
        incidents=item.incidents,
        active=item.active,
        severity=SEVERITY_NAMES[Severity(item.severity)] if item.severity is not None else None,
        provider=item.provider,
        model=item.model,
        reason=item.reason,
        counting=calls.counts(item.review, item.kind),
        effect=_effect(item),
    )


def _standing(found: service.Standing) -> StandingOut:
    return StandingOut(
        agreed=found.agreed,
        disagreed=found.disagreed,
        rate=found.rate,
        trusted=found.trusted,
        trust_after=service.TRUST_AFTER,
        trust_rate=service.TRUST_RATE,
    )


@router.get("")
def list_decisions(
    db: Db,
    state: State = "waiting",
    limit: Annotated[int, Query(ge=1, le=100)] = PAGE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ReviewOut:
    """The decisions in one state, with how many there are in each. What waits is in the order to
    look at it (what raises an alarm, then what would set aside the most), the rest newest
    first."""
    items, total = service.queue(db, state, limit, offset)
    tally = service.counts(db)
    return ReviewOut(
        state=state,
        total=total,
        items=[_decision(item) for item in items],
        counts=CountsOut(
            waiting=tally.waiting, decided=tally.decided, answered=tally.agreed + tally.disagreed
        ),
        standing=_standing(service.standing(db)),
        mode=cast(Mode, settings.load(db).mode),
    )


@router.get("/summary")
def summary(db: Db) -> SummaryOut:
    """How many decisions wait for the owner, for the menu and the dashboard."""
    return SummaryOut(waiting=service.waiting(db))


def _settings(db: Db) -> SettingsOut:
    policy = settings.load(db)
    row = db.get(ReviewSettings, 1)
    return SettingsOut(
        mode=cast(Mode, policy.mode),
        auto_from=policy.auto_from,
        learn=policy.learn,
        default_mode=cast(Mode, settings.DEFAULT_MODE),
        default_auto_from=settings.DEFAULT_AUTO_FROM,
        min_auto_from=settings.MIN_AUTO_FROM,
        updated_at=row.updated_at if row else None,
    )


@router.get("/settings")
def get_settings(db: Db) -> SettingsOut:
    """How much of what the AI decides waits for the owner, or what it is until they say."""
    return _settings(db)


@router.put("/settings")
def change_settings(
    body: SettingsIn,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
) -> SettingsOut:
    """Sets them. A decision the AI made before counts as it did; the new setting applies to what
    it decides from now on."""
    was = settings.load(db)
    asked = settings.Policy(body.mode, body.auto_from, body.learn)
    if settings.save(db, asked):
        record_audit(
            db,
            request,
            Action.REVIEW_SETTINGS_CHANGED,
            Outcome.SUCCESS,
            user=auth.user,
            detail={
                "mode": asked.mode,
                "from_mode": was.mode,
                "auto_from": asked.auto_from,
                "learn": asked.learn,
            },
        )
        db.commit()
    return _settings(db)


@router.post("/agree")
def agree_all(
    body: AgreeAllIn,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
) -> AgreedOut:
    """Agrees with each decision given that is still waiting."""
    agreed = service.agree_all(db, [(item.subject, item.id) for item in body.items])
    if agreed:
        record_audit(
            db,
            request,
            Action.REVIEW_AGREED_ALL,
            Outcome.SUCCESS,
            user=auth.user,
            detail={"count": agreed},
        )
        db.commit()
    return AgreedOut(agreed=agreed)


@router.post(
    "/{subject}/{subject_id}",
    responses={404: {"description": "That decision is not there."}},
)
def answer(
    subject: Subject,
    subject_id: int,
    body: AnswerIn,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
) -> DecisionOut:
    """Says that the owner agrees or disagrees with a decision, with a reason if they like, or
    takes the answer back. An answer applies at once: an agreed decision counts, a disagreed one
    does not. What the owner wrote as the reason is kept for the AI to learn from, and is not in
    the activity log."""
    try:
        decided = service.answer(
            db, subject, subject_id, body.answer, body.reason, keep_kind=body.keep_kind
        )
    except service.NotFound:
        raise HTTPException(status_code=404, detail="That decision is not there.") from None
    record_audit(
        db,
        request,
        Action.REVIEW_ANSWERED,
        Outcome.SUCCESS,
        user=auth.user,
        detail={
            "subject": subject,
            "id": subject_id,
            "answer": body.answer,
            "reason_given": body.reason is not None,
        },
    )
    db.commit()
    return _decision(decided)
