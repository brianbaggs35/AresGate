"""How long events are kept, for each source, and removing the ones past it.

A source keeps its events for the days set for it, or else for ``ARESGATE_EVENT_RETENTION_DAYS``.
Removing them is done in two ways: a week that ended before even the longest retention period
began is dropped whole, and the rest is deleted by source and time. A past week left with no
events after that is dropped too."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import ColumnElement, and_, delete, func, or_, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.events import partitions
from app.models import Event, EventRetention

MIN_DAYS = 1
MAX_DAYS = 3650


@dataclass(frozen=True)
class Retention:
    """How many days each source keeps its events."""

    default: int
    # The sources that have a setting of their own.
    own: Mapping[str, int]

    def days(self, source: str) -> int:
        return self.own.get(source, self.default)

    @property
    def longest(self) -> int:
        return max([self.default, *self.own.values()])


def load(db: Session, settings: Settings) -> Retention:
    own = {row.source: row.days for row in db.scalars(select(EventRetention))}
    return Retention(settings.event_retention_days, own)


def set_days(db: Session, source: str, days: int | None) -> None:
    """Keeps a source's events for this many days, or for the default again when ``days`` is
    None. The caller commits."""
    row = db.get(EventRetention, source)
    if days is None:
        if row is not None:
            db.delete(row)
    elif row is None:
        db.add(EventRetention(source=source, days=days))
    else:
        row.days = days


@dataclass(frozen=True)
class Stored:
    """What is kept of one source's events."""

    events: int
    oldest: datetime | None


def stored(db: Session) -> dict[str, Stored]:
    """How many events each source has, and when the oldest happened."""
    rows = db.execute(
        select(Event.source, func.count(), func.min(Event.occurred_at)).group_by(Event.source)
    )
    return {source: Stored(count, oldest) for source, count, oldest in rows}


@dataclass(frozen=True)
class Purged:
    deleted: int
    partitions_dropped: int


def _expired(retention: Retention, now: datetime) -> ColumnElement[bool]:
    """Events older than their source keeps them."""
    others = Event.occurred_at < now - timedelta(days=retention.default)
    if retention.own:
        others = and_(Event.source.not_in(retention.own), others)
    return or_(
        others,
        *(
            and_(Event.source == source, Event.occurred_at < now - timedelta(days=days))
            for source, days in retention.own.items()
        ),
    )


def purge_expired(db: Session, settings: Settings, now: datetime) -> Purged:
    """Removes the events past their retention period. Commits."""
    retention = load(db, settings)
    partitions.lock(db)
    dropped = 0
    # Every event in a week that ended before the longest period began is past its own.
    over = now - timedelta(days=retention.longest)
    for partition in partitions.existing(db):
        if partition.end <= over:
            partitions.drop(db, partition)
            dropped += 1
    deleted = db.connection().execute(delete(Event).where(_expired(retention, now))).rowcount
    # A week in the past that the delete emptied has no use, and is made again if an event of
    # that week turns up.
    for partition in partitions.existing(db):
        if partition.end <= now and not partitions.has_events(db, partition):
            partitions.drop(db, partition)
            dropped += 1
    db.commit()
    return Purged(deleted, dropped)
