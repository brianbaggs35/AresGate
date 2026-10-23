"""How the collectors are doing, as the API and the status page tell it."""

from datetime import datetime

from pydantic import AwareDatetime, BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collectors import health
from app.collectors.health import State, WorkerState
from app.collectors.registry import find
from app.config import Settings
from app.integrations import registry
from app.integrations.registry import ConnectionDef, IntegrationDef
from app.models import CollectorHealth, WorkerBeat


class CollectorOut(BaseModel):
    collector: str
    title: str
    summary: str
    integration: str
    connection: str
    # Where it reads from, to say on a page that lists collectors of several integrations: the
    # integration's name, and the connection's too if the integration has more than one.
    source: str
    state: State
    interval_seconds: int
    last_started_at: AwareDatetime | None
    last_finished_at: AwareDatetime | None
    last_success_at: AwareDatetime | None
    last_duration_ms: int | None
    last_items: int | None
    last_error: str | None
    consecutive_failures: int
    next_run_at: AwareDatetime | None


class WorkerOut(BaseModel):
    state: WorkerState
    # When this run of the worker began, and when it last said it was alive.
    started_at: AwareDatetime | None
    seen_at: AwareDatetime | None


class CollectorsOut(BaseModel):
    worker: WorkerOut
    collectors: list[CollectorOut]


def _worker(db: Session, now: datetime, enabled: bool) -> WorkerOut:
    beat = db.get(WorkerBeat, health.WORKER)
    return WorkerOut(
        state=health.worker_state(beat, now, enabled),
        started_at=beat.started_at if beat else None,
        seen_at=beat.beat_at if beat else None,
    )


def _source(definition: IntegrationDef, connection: ConnectionDef) -> str:
    """Where a collector reads from, for a page that lists those of several integrations."""
    if len(definition.connections) > 1:
        return f"{definition.name} · {connection.label}"
    return definition.name


def _collector(row: CollectorHealth, now: datetime) -> CollectorOut | None:
    """A record as the API tells it, or None for one of something the product no longer has."""
    collector = find(row.collector)
    definition = registry.INTEGRATIONS.get(row.integration)
    connection = definition.connection(row.connection) if definition else None
    if collector is None or definition is None or connection is None:
        return None
    return CollectorOut(
        collector=row.collector,
        title=collector.title,
        summary=collector.summary,
        integration=row.integration,
        connection=row.connection,
        source=_source(definition, connection),
        state=health.state_of(row, now),
        interval_seconds=row.interval_seconds,
        last_started_at=row.last_started_at,
        last_finished_at=row.last_finished_at,
        last_success_at=row.last_success_at,
        last_duration_ms=row.last_duration_ms,
        last_items=row.last_items,
        last_error=row.last_error,
        consecutive_failures=row.consecutive_failures,
        next_run_at=row.next_run_at,
    )


def build(
    db: Session, settings: Settings, now: datetime, integration: str | None = None
) -> CollectorsOut:
    """The worker and each collector. With collecting turned off there are no collectors to
    report: what is left in the table is from before."""
    worker = _worker(db, now, settings.collectors_enabled)
    if not settings.collectors_enabled:
        return CollectorsOut(worker=worker, collectors=[])
    query = select(CollectorHealth).order_by(
        CollectorHealth.integration, CollectorHealth.connection, CollectorHealth.collector
    )
    if integration is not None:
        query = query.where(CollectorHealth.integration == integration)
    found = (_collector(row, now) for row in db.scalars(query))
    return CollectorsOut(worker=worker, collectors=[item for item in found if item])
