"""How long what the integrations report is kept, for each source, and removing what is past it.

A source keeps its rows for the days set for it, or else for the default the table's setting
gives. Removing them is done in two ways: a week that ended before even the longest retention
period began is dropped whole, and the rest is deleted by source and time. A past week left with
nothing after that is dropped too."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import ColumnElement, and_, delete, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import SQLColumnExpression

from app.config import Settings
from app.models import Base, SourceRetention
from app.partitions import Weekly

MIN_DAYS = 1
MAX_DAYS = 3650


@dataclass(frozen=True)
class Retention:
    """How many days each source keeps its rows."""

    default: int
    # The sources that have a setting of their own.
    own: Mapping[str, int]

    def days(self, source: str) -> int:
        return self.own.get(source, self.default)

    @property
    def longest(self) -> int:
        return max([self.default, *self.own.values()])


@dataclass(frozen=True)
class Stored:
    """What is kept of one source's rows."""

    rows: int
    oldest: datetime | None


@dataclass(frozen=True)
class Purged:
    deleted: int
    partitions_dropped: int


@dataclass(frozen=True)
class Retained:
    """A table in weekly partitions whose rows each source keeps for its own number of days."""

    weeks: Weekly
    model: type[Base]
    # The columns that say when a row is from and which source reported it.
    time: SQLColumnExpression[datetime]
    source: SQLColumnExpression[str]
    # The table of the sources that keep theirs for a time of their own, and the default for the
    # rest.
    policy: type[SourceRetention]
    default_days: Callable[[Settings], int]
    # Run once the expired rows are gone, still under the lock and before the commit, by a table
    # with something that outlives its rows.
    tidy: Callable[[Session], None] | None = None

    def load(self, db: Session, settings: Settings) -> Retention:
        own = {row.source: row.days for row in db.scalars(select(self.policy))}
        return Retention(self.default_days(settings), own)

    def set_days(self, db: Session, source: str, days: int | None) -> None:
        """Keeps a source's rows for this many days, or for the default again when ``days`` is
        None. The caller commits."""
        row = db.get(self.policy, source)
        if days is None:
            if row is not None:
                db.delete(row)
        elif row is None:
            db.add(self.policy(source=source, days=days))
        else:
            row.days = days

    def stored(self, db: Session) -> dict[str, Stored]:
        """How many rows each source has, and when the oldest is from."""
        rows = db.execute(
            select(self.source, func.count(), func.min(self.time)).group_by(self.source)
        )
        return {source: Stored(count, oldest) for source, count, oldest in rows}

    def purge_expired(self, db: Session, settings: Settings, now: datetime) -> Purged:
        """Removes the rows past their retention period. Commits."""
        retention = self.load(db, settings)
        self.weeks.lock(db)
        dropped = 0
        # Every row in a week that ended before the longest period began is past its own.
        over = now - timedelta(days=retention.longest)
        for partition in self.weeks.existing(db):
            if partition.end <= over:
                self.weeks.drop(db, partition)
                dropped += 1
        deleted = (
            db.connection()
            .execute(delete(self.model).where(self._expired(retention, now)))
            .rowcount
        )
        # A week in the past that the delete emptied has no use, and is made again if a row of
        # that week turns up.
        for partition in self.weeks.existing(db):
            if partition.end <= now and not self.weeks.has_rows(db, partition):
                self.weeks.drop(db, partition)
                dropped += 1
        if self.tidy is not None:
            self.tidy(db)
        db.commit()
        return Purged(deleted, dropped)

    def _expired(self, retention: Retention, now: datetime) -> ColumnElement[bool]:
        """Rows older than their source keeps them."""
        others = self.time < now - timedelta(days=retention.default)
        if retention.own:
            others = and_(self.source.not_in(retention.own), others)
        return or_(
            others,
            *(
                and_(self.source == source, self.time < now - timedelta(days=days))
                for source, days in retention.own.items()
            ),
        )
