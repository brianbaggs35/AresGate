"""What the owner is asked to look at, what they said, and what the AI is told of it.

An AI decision that is worth a look is one that would change what the owner sees: it calls an
incident, or a whole family of them, noise or a probe (so they are set aside) or an attack or a
compromise (so they are raised). Each is either waiting for the owner (``pending``), counted at
once and listed to look at later (``auto``), or answered: agreed or disagreed with, with a reason
if they gave one. How a decision starts is the owner's setting (``app/review/settings.py``); what
a state means for the incident is in ``app/threats/calls.py``."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.redaction import Redactor
from app.incidents.attention import ACTIVE
from app.models import AiTriage, Incident, IncidentFamily, ReviewFeedback
from app.models.base import utcnow
from app.review import settings
from app.threats import calls

Subject = Literal["incident", "family"]
Answer = Literal["agree", "disagree", "undo"]
State = Literal["waiting", "decided", "answered"]

# What the AI can call a decision that is worth a look: not "unclear", which changes nothing.
REVIEWED: Final = (*calls.QUIET, *calls.LOUD)
MAX_REASON: Final = 300
LESSONS: Final = 5
# How many answers it takes, and how often the owner has agreed, before AresGate says the AI
# could be left to decide on its own.
TRUST_AFTER: Final = 20
TRUST_RATE: Final = 0.95
PENDING: Final = "pending"
AUTO: Final = "auto"
AGREED: Final = "agreed"
DISAGREED: Final = "disagreed"
ANSWERED: Final = (AGREED, DISAGREED)


class NotFound(Exception):
    """There is no such decision to review."""


@dataclass(frozen=True)
class Decision:
    """One thing the AI decided, as the Review page shows it."""

    subject: Subject
    id: int
    review: str
    kind: str
    confidence: int
    title: str
    why: str
    # What the AI suggested the owner say about it, if it did (readings only).
    suggestion: str | None
    decided_at: datetime
    reviewed_at: datetime | None
    # How many incidents it is about, and how many of them are still going on.
    incidents: int
    active: int
    # The worst of an incident's signals (readings) or of its family's.
    severity: int | None
    provider: str | None
    model: str | None
    # What the owner said of it last, if anything.
    reason: str | None


@dataclass(frozen=True)
class Standing:
    """How far the AI can be trusted, by what the owner has said."""

    agreed: int
    disagreed: int

    @property
    def answered(self) -> int:
        return self.agreed + self.disagreed

    @property
    def rate(self) -> float | None:
        return self.agreed / self.answered if self.answered else None

    @property
    def trusted(self) -> bool:
        """Whether the owner has agreed often enough, with enough answers, to leave it alone."""
        return self.answered >= TRUST_AFTER and self.rate is not None and self.rate >= TRUST_RATE


def starts(policy: settings.Policy, kind: str, confidence: int) -> str:
    """Where a new decision starts: only one that is worth a look can wait."""
    return policy.status(confidence) if kind in REVIEWED else AUTO


def carried(review: str, was_kind: str | None, kind: str, now_review: str) -> str:
    """Where a decision that replaces an earlier one starts: where the owner left the earlier one
    when it said the same, since asking again about what they have answered is no help."""
    if review in ANSWERED and was_kind == kind:
        return review
    return now_review


def _wanted(state: State | None) -> tuple[str, ...]:
    """The reviews a list holds: one state's, or every state's for ``None``."""
    if state is None:
        return (PENDING, AUTO, *ANSWERED)
    return {"waiting": (PENDING,), "decided": (AUTO,), "answered": ANSWERED}[state]


def _incident_rows(
    db: Session, state: State | None, limit: int, only: int | None = None
) -> list[Decision]:
    query = (
        select(AiTriage, Incident)
        .join(Incident, Incident.id == AiTriage.incident_id)
        .where(AiTriage.review.in_(_wanted(state)), AiTriage.classification.in_(REVIEWED))
        .order_by(AiTriage.reviewed_at.desc().nulls_last(), AiTriage.read_at.desc())
        .limit(limit)
    )
    if only is not None:
        query = query.where(Incident.id == only)
    rows = db.execute(query).all()
    reasons = _reasons(db, "incident", [triage.incident_id for triage, _ in rows])
    return [
        Decision(
            subject="incident",
            id=incident.id,
            review=triage.review,
            kind=triage.classification,
            confidence=triage.confidence,
            title=incident.title,
            why=triage.headline,
            suggestion=triage.verdict,
            decided_at=triage.read_at,
            reviewed_at=triage.reviewed_at,
            incidents=1,
            active=int(incident.status in ACTIVE),
            severity=incident.severity,
            provider=triage.provider,
            model=triage.model,
            reason=reasons.get(incident.id),
        )
        for triage, incident in rows
    ]


def _family_rows(
    db: Session, state: State | None, limit: int, only: int | None = None
) -> list[Decision]:
    size = (
        select(
            Incident.family_id.label("id"),
            func.count().label("total"),
            func.count().filter(Incident.status.in_(ACTIVE)).label("active"),
            func.max(Incident.severity).label("worst"),
        )
        .where(Incident.family_id.is_not(None))
        .group_by(Incident.family_id)
        .subquery()
    )
    query = (
        select(IncidentFamily, size.c.total, size.c.active, size.c.worst)
        .outerjoin(size, size.c.id == IncidentFamily.id)
        .where(
            IncidentFamily.review.in_(_wanted(state)),
            IncidentFamily.ai_class.in_(REVIEWED),
            IncidentFamily.judged_at.is_not(None),
        )
        .order_by(IncidentFamily.reviewed_at.desc().nulls_last(), IncidentFamily.judged_at.desc())
        .limit(limit)
    )
    if only is not None:
        query = query.where(IncidentFamily.id == only)
    rows = db.execute(query).all()
    reasons = _reasons(db, "family", [family.id for family, *_ in rows])
    return [
        Decision(
            subject="family",
            id=family.id,
            review=family.review,
            kind=family.ai_class or "unclear",
            confidence=family.ai_confidence or 0,
            title=family.label,
            why=family.ai_reason or "",
            suggestion=None,
            decided_at=family.judged_at or family.created_at,
            reviewed_at=family.reviewed_at,
            incidents=total or 0,
            active=active or 0,
            severity=worst,
            provider=family.provider,
            model=family.model,
            reason=reasons.get(family.id),
        )
        for family, total, active, worst in rows
    ]


def _reasons(db: Session, subject: Subject, ids: Sequence[int]) -> dict[int, str]:
    """What the owner last said of each, if they gave a reason."""
    if not ids:
        return {}
    found = db.execute(
        select(ReviewFeedback.subject_id, ReviewFeedback.reason)
        .where(
            ReviewFeedback.subject == subject,
            ReviewFeedback.subject_id.in_(ids),
            ReviewFeedback.reason.is_not(None),
        )
        .order_by(ReviewFeedback.id)
    )
    return {subject_id: reason for subject_id, reason in found if reason}


def _impact(item: Decision) -> tuple[int, int, float]:
    """What to look at first: what raises an alarm, then what would set aside the most."""
    loud = 0 if item.kind in calls.LOUD else 1
    return (loud, -item.active, -item.decided_at.timestamp())


def queue(db: Session, state: State, limit: int, offset: int = 0) -> tuple[list[Decision], int]:
    """The decisions in one state: what waits is in the order to look at it, the rest newest
    first. Also how many there are in all."""
    both = [*_incident_rows(db, state, offset + limit), *_family_rows(db, state, offset + limit)]
    if state == "waiting":
        both.sort(key=_impact)
    else:
        both.sort(key=lambda item: item.reviewed_at or item.decided_at, reverse=True)
    return both[offset : offset + limit], counts(db).of(state)


@dataclass(frozen=True)
class Tally:
    """How many decisions are in each state, and how many answers each way there have been."""

    waiting: int
    decided: int
    agreed: int
    disagreed: int

    def of(self, state: State) -> int:
        return {
            "waiting": self.waiting,
            "decided": self.decided,
            "answered": self.agreed + self.disagreed,
        }[state]


def counts(db: Session) -> Tally:
    """How many decisions are in each state."""
    found: dict[str, int] = {}
    for kind_column, review_column in (
        (AiTriage.classification, AiTriage.review),
        (IncidentFamily.ai_class, IncidentFamily.review),
    ):
        rows = db.execute(
            select(review_column, func.count())
            .where(kind_column.in_(REVIEWED))
            .group_by(review_column)
        )
        for review, number in rows:
            found[review] = found.get(review, 0) + number
    return Tally(
        waiting=found.get(PENDING, 0),
        decided=found.get(AUTO, 0),
        agreed=found.get(AGREED, 0),
        disagreed=found.get(DISAGREED, 0),
    )


def standing(db: Session) -> Standing:
    """How often the owner has agreed with the AI, by every answer they have given."""
    agreed, disagreed = db.execute(
        select(
            func.count().filter(ReviewFeedback.answer == "agree"),
            func.count().filter(ReviewFeedback.answer == "disagree"),
        )
    ).one()
    return Standing(agreed, disagreed)


def waiting(db: Session) -> int:
    """How many decisions wait for the owner."""
    return counts(db).waiting


def _row(db: Session, subject: Subject, subject_id: int) -> AiTriage | IncidentFamily:
    row = (
        db.get(AiTriage, subject_id)
        if subject == "incident"
        else db.get(IncidentFamily, subject_id)
    )
    kind = (
        row.classification
        if isinstance(row, AiTriage)
        else (row.ai_class if row is not None and row.judged_at is not None else None)
    )
    if row is None or kind not in REVIEWED:
        raise NotFound
    return row


def _title(db: Session, row: AiTriage | IncidentFamily) -> str:
    if isinstance(row, IncidentFamily):
        return row.label
    return db.scalars(select(Incident.title).where(Incident.id == row.incident_id)).one()


def _call(row: AiTriage | IncidentFamily) -> tuple[str, int]:
    if isinstance(row, AiTriage):
        return row.classification, row.confidence
    return row.ai_class or "unclear", row.ai_confidence or 0


def _sync(db: Session, subject: Subject, subject_id: int) -> None:
    if subject == "incident":
        calls.sync(db, [subject_id])
    else:
        calls.sync(db, family_id=subject_id)


def answer(
    db: Session,
    subject: Subject,
    subject_id: int,
    said: Answer,
    reason: str | None = None,
    *,
    keep_kind: bool = False,
    now: datetime | None = None,
) -> Decision:
    """Records what the owner said of one decision and applies it: an agreed one counts, a
    disagreed one doesn't, and taking an answer back sends it to wait again. ``keep_kind`` (of a
    family that was set aside) says whether to keep it so, or in front of them, from now on,
    whatever the AI says next. The caller commits."""
    row = _row(db, subject, subject_id)
    now = now or utcnow()
    kind, confidence = _call(row)
    if said == "undo":
        row.review = PENDING
        row.reviewed_at = None
        newest = db.scalars(
            select(ReviewFeedback)
            .where(ReviewFeedback.subject == subject, ReviewFeedback.subject_id == subject_id)
            .order_by(ReviewFeedback.id.desc())
            .limit(1)
        ).first()
        if newest is not None:
            db.delete(newest)
    else:
        row.review = AGREED if said == "agree" else DISAGREED
        row.reviewed_at = now
        db.add(
            ReviewFeedback(
                created_at=now,
                subject=subject,
                subject_id=subject_id,
                title=_title(db, row)[:200],
                ai_class=kind,
                ai_confidence=confidence,
                answer=said,
                reason=(reason or "").strip()[:MAX_REASON] or None,
            )
        )
        if keep_kind and isinstance(row, IncidentFamily) and kind in calls.QUIET:
            row.owner_call = "background" if said == "agree" else "watch"
            row.owner_call_at = now
    db.flush()
    _sync(db, subject, subject_id)
    return _one(db, subject, subject_id)


def _one(db: Session, subject: Subject, subject_id: int) -> Decision:
    """The decision of an incident or a kind as the page shows it, wherever it stands. It is
    there: ``answer`` has just checked that it can be reviewed."""
    if subject == "incident":
        return _incident_rows(db, None, 1, subject_id)[0]
    return _family_rows(db, None, 1, subject_id)[0]


def agree_all(
    db: Session, items: Iterable[tuple[Subject, int]], now: datetime | None = None
) -> int:
    """Agrees with each decision given that is still waiting, and says how many were. The caller
    commits."""
    done = 0
    for subject, subject_id in items:
        try:
            row = _row(db, subject, subject_id)
        except NotFound:
            continue
        if row.review != PENDING:
            continue
        answer(db, subject, subject_id, "agree", now=now)
        done += 1
    return done


# -- what the AI is told


def lessons(db: Session, redactor: Redactor, policy: settings.Policy) -> list[str]:
    """What the owner disagreed with most recently, and why, for the AI to be reminded of when it
    decides. None unless the owner lets it learn from them."""
    if not policy.learn:
        return []
    found = db.scalars(
        select(ReviewFeedback)
        .where(ReviewFeedback.answer == "disagree")
        .order_by(ReviewFeedback.id.desc())
        .limit(LESSONS)
    )
    lines: list[str] = []
    for each in found:
        line = (
            f"- You called {redactor.text(each.title, 160)} {each.ai_class} "
            f"({each.ai_confidence}% sure) and the owner disagreed"
        )
        lines.append(f"{line}: {redactor.text(each.reason, MAX_REASON)}" if each.reason else line)
    return lines
