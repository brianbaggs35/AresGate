"""What the scheduler keeps in the database: which collectors are wanted, how each run went and
that the worker is alive. These are plain functions of a session, and the caller commits."""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.collectors.base import Collector
from app.collectors.health import WORKER
from app.integrations import registry
from app.integrations.registry import ConnectionDef, IntegrationDef, ModuleState
from app.models import CollectorHealth, IntegrationConnection, WorkerBeat

MAX_ERROR = 500

type JobKey = tuple[str, str, str]


@dataclass(frozen=True)
class Wanted:
    """One collector that should be running on one connection."""

    collector: Collector
    definition: IntegrationDef
    connection: ConnectionDef
    # When the connection's settings were last saved, so a change is noticed.
    version: datetime

    @property
    def key(self) -> JobKey:
        return (self.collector.key, self.definition.key, self.connection.key)


def wanted(db: Session, collectors: Iterable[Collector]) -> list[Wanted]:
    """Every collector that applies to a saved connection, in a steady order. A connection that
    is no longer one AresGate knows (the integration was dropped from the product) is skipped,
    and so is a module that has been switched off or that testing the connection found isn't
    installed. A module nobody has tested yet gets its collectors, which say what's wrong."""
    result: list[Wanted] = []
    rows = db.scalars(
        select(IntegrationConnection).order_by(
            IntegrationConnection.integration, IntegrationConnection.connection
        )
    )
    for row in rows:
        definition = registry.INTEGRATIONS.get(row.integration)
        connection = definition.connection(row.connection) if definition else None
        if definition is None or connection is None:
            continue
        result.extend(
            Wanted(item, definition, connection, row.updated_at)
            for item in collectors
            if item.reads(row.integration, row.connection)
            and item.module not in row.disabled_modules
            and row.module_states.get(item.module or "") != ModuleState.NOT_INSTALLED
        )
    return result


def _find(db: Session, key: JobKey) -> CollectorHealth | None:
    collector, integration, connection = key
    return db.scalar(
        select(CollectorHealth).where(
            CollectorHealth.collector == collector,
            CollectorHealth.integration == integration,
            CollectorHealth.connection == connection,
        )
    )


def sync(db: Session, items: Sequence[Wanted], now: datetime) -> None:
    """Gives every wanted collector a health record, and deletes the records of the ones that
    are not wanted any more, such as those of a connection that was disconnected."""
    kept = {
        (row.collector, row.integration, row.connection): row
        for row in db.scalars(select(CollectorHealth))
    }
    for item in items:
        interval = int(item.collector.interval.total_seconds())
        row = kept.pop(item.key, None)
        if row is None:
            db.add(_new(item.key, interval, now))
        else:
            row.interval_seconds = interval
    for stale in kept.values():
        db.delete(stale)


def _new(key: JobKey, interval: int, now: datetime) -> CollectorHealth:
    collector, integration, connection = key
    return CollectorHealth(
        collector=collector,
        integration=integration,
        connection=connection,
        interval_seconds=interval,
        consecutive_failures=0,
        updated_at=now,
    )


def finish(
    db: Session,
    item: Wanted,
    started: datetime,
    finished: datetime,
    error: str | None,
    items: int | None,
    delay_after: Callable[[int], timedelta],
) -> int:
    """Keeps how a run went and when the next one is due, and returns how many runs in a row
    have failed. ``delay_after`` says how long to wait, given that number."""
    row = _find(db, item.key)
    if row is None:
        # Its record was deleted while it ran, and it is wanted again.
        row = _new(item.key, int(item.collector.interval.total_seconds()), finished)
        db.add(row)
    row.last_started_at = started
    row.last_finished_at = finished
    row.last_duration_ms = int((finished - started).total_seconds() * 1000)
    if error is None:
        row.last_success_at = finished
        row.last_items = items
        row.last_error = None
        row.consecutive_failures = 0
    else:
        row.last_error = audit.clean(error, MAX_ERROR)
        row.consecutive_failures += 1
    row.next_run_at = finished + delay_after(row.consecutive_failures)
    row.updated_at = finished
    return row.consecutive_failures


def beat(db: Session, started_at: datetime, now: datetime) -> None:
    """Says the worker is alive."""
    row = db.get(WorkerBeat, WORKER)
    if row is None:
        db.add(WorkerBeat(name=WORKER, started_at=started_at, beat_at=now))
    else:
        row.started_at = started_at
        row.beat_at = now
