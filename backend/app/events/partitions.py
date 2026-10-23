"""The weekly partitions of the events table.

Each week (Monday to Sunday, UTC) of ``occurred_at`` is a table of its own, named for the day it
begins, so a week that has outlived its retention period goes by dropping a table, which is
instant and gives the disk back, where deleting its rows would take a while and leave dead rows
behind. A week is made when an event of that week is stored; nothing is made ahead of time.

Making and dropping partitions happen under one lock that storing events also takes, so a
partition is never dropped between an event choosing it and being written into it."""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta

from sqlalchemy import DDL, exists, select, text
from sqlalchemy.orm import Session

from app.models import Event

WEEK = timedelta(days=7)
# What the advisory lock is called, as a number the database can take: "ARES" in ASCII.
LOCK_KEY = 0x41524553
_NAME = re.compile(r"^events_p(\d{8})$")


@dataclass(frozen=True, order=True)
class Partition:
    """One week of events: from ``start`` up to, and not including, ``end``."""

    start: datetime

    @property
    def end(self) -> datetime:
        return self.start + WEEK

    @property
    def name(self) -> str:
        return f"events_p{self.start:%Y%m%d}"


def containing(moment: datetime) -> Partition:
    """The week a moment is in."""
    day = moment.astimezone(UTC).date()
    return Partition(datetime.combine(day - timedelta(days=day.weekday()), time.min, UTC))


def lock(db: Session) -> None:
    """Waits for the lock on the partitions, and keeps it until the transaction ends."""
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": LOCK_KEY})


def existing(db: Session) -> list[Partition]:
    """Every week that has a partition, oldest first. A table of another name that someone made
    under events isn't one of ours, and is left alone."""
    names = db.scalars(
        text(
            "SELECT child.relname FROM pg_inherits"
            " JOIN pg_class AS child ON child.oid = pg_inherits.inhrelid"
            " WHERE pg_inherits.inhparent = to_regclass('events')"
        )
    )
    found: list[Partition] = []
    for name in names:
        match = _NAME.match(name)
        if match is None:
            continue
        try:
            found.append(Partition(datetime.strptime(match[1], "%Y%m%d").replace(tzinfo=UTC)))
        except ValueError:
            # Digits that aren't a date, so not a name we made.
            continue
    return sorted(found)


def ensure(db: Session, wanted: Iterable[Partition]) -> None:
    """Makes the partitions that don't exist yet. The caller holds the lock."""
    for partition in sorted(set(wanted)):
        db.execute(
            DDL(
                "CREATE TABLE IF NOT EXISTS %(name)s PARTITION OF events"
                " FOR VALUES FROM ('%(start)s') TO ('%(end)s')",
                context={
                    "name": partition.name,
                    "start": partition.start.isoformat(),
                    "end": partition.end.isoformat(),
                },
            )
        )


def drop(db: Session, partition: Partition) -> None:
    """Drops a partition with the events in it. The caller holds the lock."""
    db.execute(DDL("DROP TABLE IF EXISTS %(name)s", context={"name": partition.name}))


def has_events(db: Session, partition: Partition) -> bool:
    return bool(
        db.scalar(
            select(
                exists().where(
                    Event.occurred_at >= partition.start, Event.occurred_at < partition.end
                )
            )
        )
    )
