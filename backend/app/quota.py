"""Keeping the database within the size the owner allowed, by removing the oldest data.

Events and metric samples are what fills the database, and each is kept in one table for each
week. Over the quota, the oldest week of either is dropped, a whole table at a time, which gives
the disk back at once, until the database is under 95% of the quota, so that the next few
readings don't put it over again.

The week that is still being filled is never dropped, and nothing else is deleted. When that week
is all that is left and the database is still over, which is so when the quota is smaller than a
week of data and everything else AresGate keeps, nothing more is removed: the page says so, and
the quota has to be raised. Deleting rows from the week in progress would not give the disk back,
and doing it again at every check would only wear the newest data away.

Storing is never refused because of the quota: new events and samples are always kept, and this
makes room for them afterwards. Every step is safe to repeat, and takes the same lock the
retention purge and the writers of those tables do, so a week is never dropped between a row
choosing it and being written into it."""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.partitions import EVENTS, METRIC_SAMPLES, Partition, Weekly
from app.retention_policy import Policy

logger = logging.getLogger(__name__)

# The size the database is brought down to, as a share of the quota.
TARGET: Final = 0.95
# Weeks dropped in one run, at most: a run that can't get under the quota carries on at the next.
MAX_DROPS: Final = 200
TABLES: Final = (EVENTS, METRIC_SAMPLES)


@dataclass(frozen=True)
class Enforced:
    """What a run did: how big the database was before and after, against the limit."""

    limit: int
    before: int
    after: int
    weeks_dropped: int

    @property
    def over(self) -> bool:
        """Whether the database is over its quota with nothing more that may be removed."""
        return self.after > self.limit


def database_bytes(db: Session) -> int:
    """How much disk the database uses."""
    return int(db.scalar(text("SELECT pg_database_size(current_database())")) or 0)


def table_bytes(db: Session, weeks: Weekly) -> int:
    """How much disk the weeks of one table use, with their indexes."""
    return int(
        db.scalar(
            text(
                "SELECT COALESCE(sum(pg_total_relation_size(inhrelid)), 0) FROM pg_inherits"
                " WHERE inhparent = to_regclass(:table)"
            ),
            {"table": weeks.table},
        )
        or 0
    )


def _oldest(db: Session, now: datetime) -> tuple[Weekly, Partition] | None:
    """The oldest week of either table that is over, which is never the one still being filled."""
    found = [
        (partition.start, number, weeks, partition)
        for number, weeks in enumerate(TABLES)
        for partition in weeks.existing(db)
        if partition.end <= now
    ]
    if not found:
        return None
    _, _, weeks, partition = min(found, key=lambda item: item[:2])
    return weeks, partition


def enforce(db: Session, policy: Policy, now: datetime) -> Enforced | None:
    """Brings the database under its quota, or does nothing (None) when there is none, and when it
    isn't over. Commits."""
    limit = policy.quota_bytes
    if limit is None:
        return None
    before = size = database_bytes(db)
    if size <= limit:
        return Enforced(limit, before, size, 0)
    dropped = 0
    while size > int(limit * TARGET) and dropped < MAX_DROPS:
        for weeks in TABLES:
            weeks.lock(db)
        chosen = _oldest(db, now)
        if chosen is None:
            break
        weeks, partition = chosen
        weeks.drop(db, partition)
        db.commit()
        dropped += 1
        size = database_bytes(db)
    db.rollback()
    result = Enforced(limit, before, size, dropped)
    logger.warning(
        "The database was %d bytes, over its quota of %d. Dropped %d old weeks of events and "
        "samples, and it is now %d bytes%s",
        before,
        limit,
        dropped,
        size,
        ", still over: only the week in progress is left" if result.over else "",
    )
    return result
