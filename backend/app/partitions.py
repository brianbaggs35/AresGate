"""Tables split into one partition for each week, and making and dropping the weeks.

Each week (Monday to Sunday, UTC) of a table's time column is a table of its own, named for the
table and the day the week begins, so a week that has outlived its retention period goes by
dropping a table, which is instant and gives the disk back, where deleting its rows would take a
while and leave dead rows behind. A week is made when a row of that week is stored; nothing is
made ahead of time.

Making and dropping partitions happen under one lock for each table that storing rows takes too,
so a partition is never dropped between a row choosing it and being written into it."""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta

from sqlalchemy import DDL, exists, select, text
from sqlalchemy import table as named_table
from sqlalchemy.orm import Session

WEEK = timedelta(days=7)


@dataclass(frozen=True, order=True)
class Partition:
    """One week of a table: from ``start`` up to, and not including, ``end``."""

    table: str
    start: datetime

    @property
    def end(self) -> datetime:
        return self.start + WEEK

    @property
    def name(self) -> str:
        return f"{self.table}_p{self.start:%Y%m%d}"


@dataclass(frozen=True)
class Weekly:
    """A table that is partitioned by week, with the number its lock is taken by in the database
    (any number that no other lock uses; these are ASCII)."""

    table: str
    lock_key: int

    @property
    def pattern(self) -> re.Pattern[str]:
        """What the name of one of this table's partitions looks like."""
        return re.compile(rf"^{re.escape(self.table)}_p(\d{{8}})$")

    def containing(self, moment: datetime) -> Partition:
        """The week a moment is in."""
        day = moment.astimezone(UTC).date()
        return Partition(
            self.table, datetime.combine(day - timedelta(days=day.weekday()), time.min, UTC)
        )

    def lock(self, db: Session) -> None:
        """Waits for the lock on this table's partitions, and keeps it until the transaction
        ends."""
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": self.lock_key})

    def existing(self, db: Session) -> list[Partition]:
        """Every week that has a partition, oldest first. A table of another name that someone
        made under this one isn't one of ours, and is left alone."""
        names = db.scalars(
            text(
                "SELECT child.relname FROM pg_inherits"
                " JOIN pg_class AS child ON child.oid = pg_inherits.inhrelid"
                " WHERE pg_inherits.inhparent = to_regclass(:table)"
            ),
            {"table": self.table},
        )
        found: list[Partition] = []
        for name in names:
            match = self.pattern.match(name)
            if match is None:
                continue
            try:
                start = datetime.strptime(match[1], "%Y%m%d").replace(tzinfo=UTC)
            except ValueError:
                # Digits that aren't a date, so not a name we made.
                continue
            found.append(Partition(self.table, start))
        return sorted(found)

    def ensure(self, db: Session, wanted: Iterable[Partition]) -> None:
        """Makes the partitions that don't exist yet. The caller holds the lock."""
        for partition in sorted(set(wanted)):
            db.execute(
                DDL(
                    "CREATE TABLE IF NOT EXISTS %(name)s PARTITION OF %(table)s"
                    " FOR VALUES FROM ('%(start)s') TO ('%(end)s')",
                    context={
                        "name": partition.name,
                        "table": partition.table,
                        "start": partition.start.isoformat(),
                        "end": partition.end.isoformat(),
                    },
                )
            )

    def drop(self, db: Session, partition: Partition) -> None:
        """Drops a partition with the rows in it. The caller holds the lock."""
        db.execute(DDL("DROP TABLE IF EXISTS %(name)s", context={"name": partition.name}))

    def has_rows(self, db: Session, partition: Partition) -> bool:
        return bool(db.scalar(select(exists().select_from(named_table(partition.name)))))


# The weeks of the events that collectors read, and of the numbers they measure.
EVENTS = Weekly("events", lock_key=0x41524553)
METRIC_SAMPLES = Weekly("metric_samples", lock_key=0x4D455452)
ALL = (EVENTS, METRIC_SAMPLES)
