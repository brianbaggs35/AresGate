"""The review queue for what the AI cleared: the verdicts it gave and the ones it suggests, for the
owner to confirm or take back, singly or many at once. For someone signed in. How it works is
``app/ai/review_queue.py``."""

from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, Query, Request
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import clearing_settings, review_queue
from app.api import verdicts as verdicts_api
from app.api.dashboard import SEVERITY_NAMES, SeverityName
from app.api.deps import Db, SignedIn, record_audit, signed_in
from app.audit import Action, Outcome
from app.events.event import Severity
from app.models import AiTriage, Incident, VerdictRule, utcnow
from app.threats import settings as threat_settings

router = APIRouter(prefix="/ai/cleared", tags=["ai"], dependencies=[Depends(signed_in)])

State = Literal["waiting", "cleared"]
Verdict = Literal["not_suspicious", "low_priority"]
MAX_ITEMS = 100
PAGE = 20
MAX_PAGE = 100


class CountsOut(BaseModel):
    """How many are in each list: suggestions waiting for the owner, and verdicts the AI gave that
    the owner has not confirmed."""

    waiting: int
    cleared: int


class IncidentRef(BaseModel):
    id: int
    title: str
    severity: SeverityName
    status: str
    subject: str
    last_seen_at: AwareDatetime


class ItemOut(BaseModel):
    """One suggestion or one verdict, with why the AI thinks it is nothing and what it read."""

    kind: State
    # A verdict's id for a cleared one; the incident's id for one that waits.
    id: int
    incident: IncidentRef | None
    verdict: Verdict
    reason: str | None
    confidence: int | None
    classification: str | None
    provider: str | None
    model: str | None
    # When it was cleared, or when the AI read the incident it suggests clearing.
    at: AwareDatetime
    # What the AI looked at: its account, the checks it made and what it observed.
    story: str | None
    checks: list[str]
    observations: list[str]


class QueueOut(BaseModel):
    state: State
    counts: CountsOut
    total: int
    items: list[ItemOut]
    # What it does now: off, suggest or automatic. Off lists nothing waiting.
    mode: Literal["off", "suggest", "automatic"]
    # Why it is not clearing by itself right now (its cap for the day or the spending limit), if so.
    held: str | None


class Pick(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: State
    id: int = Field(ge=1, le=2**63 - 1)


class Change(BaseModel):
    """What to do to some of the queue. ``verdict`` applies to suggestions that are confirmed, and
    says another verdict than the AI suggested."""

    model_config = ConfigDict(extra="forbid")

    items: list[Pick] = Field(min_length=1, max_length=MAX_ITEMS)
    verdict: Verdict | None = None


class Changed(BaseModel):
    """How many were done, and how many were no longer there to do it to."""

    done: int
    skipped: int
    counts: CountsOut


def _ref(incident: Incident | None) -> IncidentRef | None:
    if incident is None:
        return None
    return IncidentRef(
        id=incident.id,
        title=incident.title,
        severity=SEVERITY_NAMES[Severity(incident.severity)],
        status=incident.status,
        subject=incident.subject,
        last_seen_at=incident.last_seen_at,
    )


def _waiting_item(found: review_queue.Waiting) -> ItemOut:
    reading = found.reading
    return ItemOut(
        kind="waiting",
        id=found.incident.id,
        incident=_ref(found.incident),
        verdict=cast(Verdict, reading.verdict),
        reason=reading.verdict_reason or reading.headline,
        confidence=reading.confidence,
        classification=reading.classification,
        provider=reading.provider,
        model=reading.model,
        at=reading.read_at,
        story=reading.story,
        checks=list(reading.checks),
        observations=list(reading.observations),
    )


def _cleared_item(found: review_queue.Cleared) -> ItemOut:
    """A verdict the AI gave. What it read is shown where the incident and its reading are still
    there to say."""
    rule, reading = found.rule, found.reading
    return ItemOut(
        kind="cleared",
        id=rule.id,
        incident=_ref(found.incident),
        verdict=cast(Verdict, rule.verdict),
        reason=rule.note,
        confidence=rule.ai_confidence,
        classification=reading.classification if reading else None,
        provider=rule.ai_provider,
        model=rule.ai_model,
        at=rule.created_at,
        story=reading.story if reading else None,
        checks=list(reading.checks) if reading else [],
        observations=list(reading.observations) if reading else [],
    )


def counts(db: Session) -> CountsOut:
    """How many suggestions wait, and how many verdicts of the AI's have not been confirmed."""
    waiting, cleared = review_queue.counts(db)
    return CountsOut(waiting=waiting, cleared=cleared)


@router.get("")
def get_queue(
    db: Db,
    state: State = "waiting",
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = PAGE,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
) -> QueueOut:
    """One list of the queue, newest first, with how many each list has."""
    policy = clearing_settings.load(db)
    tuning = threat_settings.load(db)
    suggested = review_queue.waiting(db, policy, tuning)
    given = review_queue.cleared(db)
    if state == "waiting":
        found = [_waiting_item(item) for item in suggested]
    else:
        found = [_cleared_item(item) for item in given]
    return QueueOut(
        state=state,
        counts=CountsOut(waiting=len(suggested), cleared=len(given)),
        total=len(found),
        items=found[offset : offset + limit],
        mode=cast(Literal["off", "suggest", "automatic"], policy.mode),
        held=clearing_settings.held(db, policy, utcnow()),
    )


@router.get("/summary")
def get_summary(db: Db) -> CountsOut:
    """How many are in each list, for the banner and the menu."""
    return counts(db)


@router.post("/confirm")
def confirm(
    body: Change,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
) -> Changed:
    """Makes what the AI cleared the owner's, and gives the verdicts it suggests as the owner's."""
    now = utcnow()
    done = 0
    for pick in body.items:
        if pick.kind == "cleared":
            rule = db.get(VerdictRule, pick.id)
            facts = review_queue.confirm_cleared(rule, now) if rule is not None else None
            if facts is not None:
                record_audit(
                    db,
                    request,
                    Action.AI_CLEAR_CONFIRMED,
                    Outcome.SUCCESS,
                    user=auth.user,
                    detail=facts,
                )
                done += 1
            continue
        incident = db.get(Incident, pick.id)
        reading = db.get(AiTriage, pick.id)
        if incident is None or reading is None or incident.verdict is not None:
            continue
        given = review_queue.confirm_suggestion(db, incident, reading, body.verdict, now)
        if given is not None:
            record_audit(
                db,
                request,
                Action.AI_SUGGESTION_CONFIRMED,
                Outcome.SUCCESS,
                user=auth.user,
                detail=given[1],
            )
            done += 1
    db.commit()
    return Changed(done=done, skipped=len(body.items) - done, counts=counts(db))


@router.post("/take-back")
def take_back(
    body: Change,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
) -> Changed:
    """Takes back what the AI cleared (the incident is judged again, and the AI is told not to
    clear that match again) and turns down what it suggests (and it does not suggest that again)."""
    done = 0
    for pick in body.items:
        if pick.kind == "cleared":
            rule = db.scalars(
                select(VerdictRule).where(VerdictRule.id == pick.id, VerdictRule.given_by == "ai")
            ).first()
            if rule is not None:
                verdicts_api.take_back(db, request, auth.user, rule)
                done += 1
            continue
        incident = db.get(Incident, pick.id)
        facts = review_queue.dismiss_suggestion(db, incident) if incident is not None else None
        if facts is not None:
            record_audit(
                db,
                request,
                Action.AI_SUGGESTION_DISMISSED,
                Outcome.SUCCESS,
                user=auth.user,
                detail=facts,
            )
            done += 1
    db.commit()
    return Changed(done=done, skipped=len(body.items) - done, counts=counts(db))
