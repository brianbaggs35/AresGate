"""What can be tidied among the incidents, found the same way every time.

Several programs report the same attack in their own words, scans repeat for days, and an AI that
has read an incident often knows it is noise. This finds three kinds of thing the owner would
otherwise do by hand, each only ever as a candidate: it changes nothing. Whoever acts on one
(app/agents/proposals.py) does so through the same bulk changes the incident list has
(app/incidents/bulk.py), so each can be previewed and taken back.

- *duplicates*: open incidents that say the same thing, of which the most serious stays and the
  rest are dismissed;
- *stale*: low-priority incidents nothing has touched for days, which are resolved;
- *benign*: incidents the AI read and is sure are noise, which get a "not suspicious" verdict.

Nothing serious is ever a candidate: an incident that is high or critical, or that AresGate is
sure about, is for the owner to decide.
"""

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.orm import Session

from app.events.event import Severity
from app.incidents import rules
from app.incidents.verdicts import MUTING, NOT_SUSPICIOUS
from app.models import AiTriage, Incident

DUPLICATES: Final = "duplicates"
STALE: Final = "stale"
BENIGN: Final = "benign"
KINDS: Final = (DUPLICATES, STALE, BENIGN)

# What is done to the incidents of a candidate: a status they are given, or a verdict.
DISMISS: Final = "dismiss"
RESOLVE: Final = "resolve"
VERDICT: Final = NOT_SUSPICIOUS

# An open incident nothing has touched for this long is stale.
STALE_AFTER: Final = timedelta(days=3)
# How sure the AI has to be that an incident is noise.
SURE: Final = 80
MAX_GROUPS: Final = 10
MAX_INCIDENTS: Final = 50
ACTIVE: Final = ("open", "investigating")


@dataclass(frozen=True)
class Candidate:
    """Something to tidy, and the incidents it would change. ``keep`` is the incident that stays
    when the rest of a group is dismissed. ``key`` is the same for the same thing found again."""

    kind: str
    key: str
    title: str
    detail: str
    action: str
    incidents: tuple[int, ...]
    keep: int | None
    confidence: int


def _key(kind: str, *parts: object) -> str:
    digest = hashlib.sha256("|".join(str(part) for part in (kind, *parts)).encode()).hexdigest()
    return f"{kind}-{digest[:16]}"


def _quiet() -> ColumnElement[bool]:
    """An incident that is fair to tidy: still open, not serious and not one AresGate is sure of,
    and not already quieted by a verdict."""
    return and_(
        Incident.status.in_(ACTIVE),
        Incident.severity < Severity.HIGH,
        Incident.confidence < rules.HIGH_FROM,
        or_(Incident.verdict.is_(None), Incident.verdict.not_in(MUTING)),
    )


def duplicates(db: Session) -> list[Candidate]:
    """Open incidents with the same title, however many programs or addresses they came from."""
    count = func.count().label("count")
    titles = db.scalars(
        select(Incident.title)
        .where(_quiet())
        .group_by(Incident.title)
        .having(count > 1)
        .order_by(count.desc(), Incident.title)
        .limit(MAX_GROUPS)
    ).all()
    found: list[Candidate] = []
    for title in titles:
        group = db.scalars(
            select(Incident)
            .where(_quiet(), Incident.title == title)
            .order_by(
                Incident.severity.desc(),
                Incident.confidence.desc(),
                Incident.last_seen_at.desc(),
                Incident.id,
            )
            .limit(MAX_INCIDENTS)
        ).all()
        keep, rest = group[0], group[1:]
        same = all(item.severity == keep.severity for item in rest)
        found.append(
            Candidate(
                kind=DUPLICATES,
                key=_key(DUPLICATES, title, *sorted(item.id for item in group)),
                title=f"{len(group)} open incidents say the same thing",
                detail=(
                    f"“{title}” is open {len(group)} times. Incident {keep.id} is the most "
                    f"serious and the most recent, so it stays; the other {len(rest)} would be "
                    "dismissed."
                ),
                action=DISMISS,
                incidents=tuple(item.id for item in rest),
                keep=keep.id,
                confidence=85 if same else 70,
            )
        )
    return found


def stale(db: Session, now: datetime) -> list[Candidate]:
    """Open incidents that nothing has touched for days and that were never serious."""
    old = db.scalars(
        select(Incident.id)
        .where(_quiet(), Incident.last_seen_at < now - STALE_AFTER)
        .order_by(Incident.id)
        .limit(MAX_INCIDENTS)
    ).all()
    if not old:
        return []
    days = STALE_AFTER.days
    noun = "incident" if len(old) == 1 else "incidents"
    return [
        Candidate(
            kind=STALE,
            key=_key(STALE, *old),
            title=f"{len(old)} old {noun} nothing has touched",
            detail=(
                f"None of these has had a new signal for {days} days and none was serious, so "
                "they would be marked resolved."
            ),
            action=RESOLVE,
            incidents=tuple(old),
            keep=None,
            confidence=90,
        )
    ]


def benign(db: Session) -> list[Candidate]:
    """Incidents the AI read and is sure are noise."""
    read = db.scalars(
        select(Incident.id)
        .join(AiTriage, AiTriage.incident_id == Incident.id)
        .where(_quiet(), AiTriage.classification == "noise", AiTriage.confidence >= SURE)
        .order_by(Incident.id)
        .limit(MAX_INCIDENTS)
    ).all()
    if not read:
        return []
    sure = db.scalar(select(func.min(AiTriage.confidence)).where(AiTriage.incident_id.in_(read)))
    return [
        Candidate(
            kind=BENIGN,
            key=_key(BENIGN, *read),
            title=(
                "1 incident the AI is sure is noise"
                if len(read) == 1
                else f"{len(read)} incidents the AI is sure are noise"
            ),
            detail=(
                "The AI read each of these and is at least "
                f"{sure or SURE}% sure it is noise, so each would get a “not suspicious” "
                "verdict, which keeps it out of your attention."
            ),
            action=VERDICT,
            incidents=tuple(read),
            keep=None,
            confidence=sure or SURE,
        )
    ]


def find(db: Session, now: datetime) -> list[Candidate]:
    """Everything that can be tidied now, the surest first."""
    found = [*duplicates(db), *stale(db, now), *benign(db)]
    return sorted(found, key=lambda item: (-item.confidence, item.kind, item.key))
