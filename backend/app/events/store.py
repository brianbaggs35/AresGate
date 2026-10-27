"""Storing events: what collectors call with what they read."""

from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime, timedelta

from sqlalchemy import and_, or_, select
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


def record_unseen(
    db: Session, settings: Settings, events: Sequence[NewEvent], now: datetime
) -> int:
    """Stores the events whose identity isn't stored yet, whenever the one stored was dated, and
    returns how many were new. It is for events with no time of their own, such as a ban that
    stays in force until it runs out, which a collector dates by when it first saw it: read again
    a minute later it would be a new event every time, because the same event is told by its time
    as well as its identity. An event whose stored copy has been removed for its age is new
    again. The caller commits."""
    if not events:
        return 0
    # Under the lock before reading anything of events, not after: making the week of a new event
    # waits for everything that has read events to finish, so a reader waiting for the lock
    # behind it would wait for each other.
    EVENTS.lock(db)
    kept = retention.load(db, settings)
    wanted: dict[str, set[str]] = {}
    for event in events:
        wanted.setdefault(event.source, set()).add(event.fingerprint)
    # Each source is looked back over for as long as it keeps its events.
    known = set(
        db.execute(
            select(Event.source, Event.fingerprint).where(
                or_(
                    *(
                        and_(
                            Event.source == source,
                            Event.fingerprint.in_(fingerprints),
                            Event.occurred_at >= now - timedelta(days=kept.days(source)),
                        )
                        for source, fingerprints in wanted.items()
                    )
                )
            )
        ).tuples()
    )
    return record(db, settings, [e for e in events if (e.source, e.fingerprint) not in known], now)


def _when(occurred_at: datetime, now: datetime) -> datetime:
    return now if occurred_at > now + FUTURE_TOLERANCE else occurred_at
