"""Storing events: what collectors call with what they read."""

from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime, timedelta

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import Settings
from app.events import retention
from app.events.event import NewEvent
from app.models import Event
from app.partitions import EVENTS

# A clock this far ahead of AresGate's is taken to be a little off. Further than that, an event's
# time can't be trusted, and a time years ahead would make a week of its own to hold it.
FUTURE_TOLERANCE = timedelta(minutes=5)


def record(db: Session, settings: Settings, events: Sequence[NewEvent], now: datetime) -> int:
    """Stores the events that aren't stored yet, and returns how many were new. An event the
    same as one already kept is skipped, so a collector can read the same window twice; so is
    one older than its source keeps events, which the next purge would remove at once; and one
    that claims to be from the future is stored as of now. The caller commits."""
    kept = retention.load(db, settings)
    rows = [
        replace(event, occurred_at=_when(event.occurred_at, now)).row(now)
        for event in events
        if event.occurred_at >= now - timedelta(days=kept.days(event.source))
    ]
    if not rows:
        return 0
    # Under the lock, so a purge can't drop the week these go into between making it and writing.
    EVENTS.lock(db)
    EVENTS.ensure(db, {EVENTS.containing(row["occurred_at"]) for row in rows})
    statement = (
        insert(Event)
        .on_conflict_do_nothing(index_elements=["source", "fingerprint", "occurred_at"])
        .returning(Event.id)
    )
    return len(db.execute(statement, rows).all())


def _when(occurred_at: datetime, now: datetime) -> datetime:
    return now if occurred_at > now + FUTURE_TOLERANCE else occurred_at
