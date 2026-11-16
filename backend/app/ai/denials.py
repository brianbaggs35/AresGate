"""What the owner denied the assistant, so that it is not proposed to them again.

Pressing *Deny* on a proposal in the chat records it here, per incident: the kind of change (a
``status`` or a ``verdict``) and to what. It then stands for ``DAYS`` days, and for as long as the
incident has the status and verdict it had when it was denied, because an incident that moved on
makes the question a new one. While it stands, a proposal of the same change for the same
incident is dropped before it is stored, the model is told what was denied so that it stops
suggesting it, and a proposal already in a conversation shows as denied.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final, cast

from sqlalchemy import ColumnElement, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import AiDeniedProposal, Incident

DAYS: Final = 30
# How many denials the owner is shown, and how many the model is told of.
MAX_LISTED: Final = 100
MAX_TOLD: Final = 20

Standing = frozenset[tuple[str, str, int]]


@dataclass(frozen=True)
class Denial:
    """One standing denial, as the owner sees it."""

    id: int
    kind: str
    value: str
    incident_id: int
    title: str
    denied_at: datetime
    expires_at: datetime


def _state_of(status: str, verdict: str | None) -> str:
    """What an incident was, as far as a denial cares: its status and its verdict."""
    return f"{status}/{verdict or ''}"


def _standing_where(now: datetime) -> tuple[ColumnElement[bool], ColumnElement[bool]]:
    """What makes a denial stand: it is recent, and the incident has not moved on from it."""
    return (
        AiDeniedProposal.denied_at > now - timedelta(days=DAYS),
        AiDeniedProposal.state
        == func.concat(Incident.status, "/", func.coalesce(Incident.verdict, "")),
    )


def record(db: Session, kind: str, value: str, incident_ids: Iterable[int], now: datetime) -> int:
    """Records a proposal as denied for each of the incidents that exist, again if it already was,
    and says for how many. The caller commits."""
    found = db.execute(
        select(Incident.id, Incident.status, Incident.verdict).where(
            Incident.id.in_(set(incident_ids))
        )
    ).all()
    if not found:
        return 0
    statement = insert(AiDeniedProposal).values(
        [
            {
                "kind": kind,
                "value": value,
                "incident_id": incident_id,
                "state": _state_of(status, verdict),
                "denied_at": now,
            }
            for incident_id, status, verdict in found
        ]
    )
    db.execute(
        statement.on_conflict_do_update(
            index_elements=["kind", "value", "incident_id"],
            set_={"state": statement.excluded.state, "denied_at": statement.excluded.denied_at},
        )
    )
    return len(found)


def standing(db: Session, now: datetime) -> Standing:
    """The changes that stand denied: ``(kind, value, incident id)``."""
    rows = db.execute(
        select(AiDeniedProposal.kind, AiDeniedProposal.value, AiDeniedProposal.incident_id)
        .join(Incident, Incident.id == AiDeniedProposal.incident_id)
        .where(*_standing_where(now))
    ).all()
    return frozenset((kind, value, incident_id) for kind, value, incident_id in rows)


def listed(db: Session, now: datetime) -> list[Denial]:
    """The denials that stand, the latest first."""
    rows = db.execute(
        select(AiDeniedProposal, Incident.title)
        .join(Incident, Incident.id == AiDeniedProposal.incident_id)
        .where(*_standing_where(now))
        .order_by(AiDeniedProposal.denied_at.desc(), AiDeniedProposal.id.desc())
        .limit(MAX_LISTED)
    ).all()
    return [
        Denial(
            id=row.id,
            kind=row.kind,
            value=row.value,
            incident_id=row.incident_id,
            title=title,
            denied_at=row.denied_at,
            expires_at=row.denied_at + timedelta(days=DAYS),
        )
        for row, title in rows
    ]


def forget(db: Session, denial_id: int) -> bool:
    """Forgets one denial, whether or not it still stands. False if there is none. The caller
    commits."""
    return (
        db.scalar(
            delete(AiDeniedProposal)
            .where(AiDeniedProposal.id == denial_id)
            .returning(AiDeniedProposal.id)
        )
        is not None
    )


def forget_all(db: Session) -> int:
    """Forgets every denial, and says how many there were. The caller commits."""
    return len(db.scalars(delete(AiDeniedProposal).returning(AiDeniedProposal.id)).all())


def _incidents_of(action: Mapping[str, object]) -> list[int]:
    """The ids of the incidents a status or verdict proposal is about."""
    target, also = action.get("target_key"), action.get("also")
    keys: list[object] = [target, *(cast(list[object], also) if isinstance(also, list) else [])]
    return [int(key) for key in keys if isinstance(key, str) and key.isdigit()]


def is_denied(action: Mapping[str, object], denied: Standing) -> bool:
    """Whether a proposal is of a change that stands denied for every incident it is about."""
    kind, value = action.get("kind"), action.get("value")
    if kind not in ("status", "verdict") or not isinstance(value, str):
        return False
    ids = _incidents_of(action)
    return bool(ids) and all((str(kind), value, incident_id) in denied for incident_id in ids)


def without_denied[T: Mapping[str, object]](
    db: Session, actions: Sequence[T], now: datetime
) -> list[T]:
    """The proposals that are not of what the owner denied."""
    if not any(action.get("kind") in ("status", "verdict") for action in actions):
        return list(actions)
    denied = standing(db, now)
    return [action for action in actions if not is_denied(action, denied)]


def told(db: Session, now: datetime) -> str | None:
    """What to tell the model about what was denied, in a line, or None if nothing stands."""
    groups: dict[tuple[str, str], list[int]] = {}
    for kind, value, incident_id in sorted(standing(db, now), key=lambda item: item[2]):
        groups.setdefault((kind, value), []).append(incident_id)
    if not groups:
        return None
    parts = [
        f"{kind} {value.replace('_', ' ')} for incident "
        + ", ".join(str(item) for item in ids[:MAX_TOLD])
        for (kind, value), ids in sorted(groups.items())
    ]
    return (
        "The owner has denied these suggestions lately, so do not suggest them again unless "
        "something has changed: " + "; ".join(parts) + "."
    )
