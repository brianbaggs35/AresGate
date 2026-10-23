"""The status page: what AresGate and the programs under it are doing, for when something seems
wrong. It is for someone signed in, and says nothing that is secret."""

import time
from collections.abc import Mapping
from datetime import datetime

from fastapi import APIRouter, Depends, Request

from app import status as report
from app.api.deps import Db, SettingsDep, signed_in
from app.collectors import report as collectors
from app.collectors.health import State as CollectorState
from app.collectors.health import WorkerState
from app.config import Settings
from app.integrations import registry, service
from app.integrations.service import Status
from app.models import IntegrationConnection, utcnow

router = APIRouter(tags=["status"], dependencies=[Depends(signed_in)])

_STATES: Mapping[Status, report.State] = {
    Status.CONNECTED: "ok",
    Status.PROBLEM: "problem",
    Status.UNTESTED: "unknown",
    Status.NOT_CONNECTED: "off",
}
_DETAILS: Mapping[Status, str | None] = {
    Status.CONNECTED: None,
    Status.PROBLEM: None,
    Status.UNTESTED: "Saved, but not tested yet.",
    Status.NOT_CONNECTED: "Not connected.",
}


def _last_error(rows: Mapping[str, IntegrationConnection]) -> str | None:
    return next((row.last_error for row in rows.values() if row.last_error), None)


def integration_parts(db: Db) -> list[report.Part]:
    parts: list[report.Part] = []
    for definition in registry.INTEGRATIONS.values():
        rows = service.rows_for(db, definition.key)
        status = service.integration_status(rows)
        parts.append(
            report.Part(
                key=definition.key,
                name=definition.name,
                group="integration",
                state=_STATES[status],
                detail=_last_error(rows) if status == Status.PROBLEM else _DETAILS[status],
                last_success_at=service.last_success(rows),
                integration=definition.key,
            )
        )
    return parts


_WORKER_STATES: Mapping[WorkerState, report.State] = {
    WorkerState.RUNNING: "ok",
    WorkerState.STOPPED: "problem",
    WorkerState.UNKNOWN: "unknown",
    WorkerState.OFF: "off",
}
_WORKER_DETAILS: Mapping[WorkerState, str | None] = {
    WorkerState.RUNNING: None,
    WorkerState.STOPPED: "Hasn't reported in for a minute or more, so nothing is being collected.",
    WorkerState.UNKNOWN: "Hasn't reported in yet.",
    WorkerState.OFF: "Collecting is turned off (ARESGATE_COLLECTORS_ENABLED).",
}
_COLLECTOR_STATES: Mapping[CollectorState, report.State] = {
    CollectorState.OK: "ok",
    CollectorState.PROBLEM: "problem",
    CollectorState.LATE: "problem",
    CollectorState.WAITING: "unknown",
}
_COLLECTOR_DETAILS: Mapping[CollectorState, str | None] = {
    CollectorState.OK: None,
    CollectorState.PROBLEM: None,
    CollectorState.LATE: "Hasn't run when it should have. Is the collector worker running?",
    CollectorState.WAITING: "Hasn't run yet.",
}


def collector_parts(db: Db, settings: Settings, now: datetime) -> list[report.Part]:
    """The worker, then each collector on each connection."""
    found = collectors.build(db, settings, now)
    parts = [
        report.Part(
            key="worker",
            name="Collector worker",
            group="collector",
            state=_WORKER_STATES[found.worker.state],
            detail=_WORKER_DETAILS[found.worker.state],
            last_success_at=found.worker.seen_at,
        )
    ]
    for item in found.collectors:
        parts.append(
            report.Part(
                key=f"{item.collector}/{item.integration}/{item.connection}",
                name=f"{item.source}: {item.title}",
                group="collector",
                state=_COLLECTOR_STATES[item.state],
                detail=item.last_error
                if item.state == CollectorState.PROBLEM
                else _COLLECTOR_DETAILS[item.state],
                last_success_at=item.last_success_at,
                integration=item.integration,
            )
        )
    return parts


@router.get("/status")
def get_status(request: Request, db: Db, settings: SettingsDep) -> report.StatusReport:
    """How AresGate is doing: its version and uptime, the programs and database under it, the
    container's resources and each part's health, and the same as text for a bug report."""
    now = utcnow()
    result = report.StatusReport(
        aresgate=report.BuildInfo(
            version=settings.version,
            commit=settings.commit,
            built_at=settings.built_at,
            environment=settings.environment,
            started_at=request.app.state.started_at,
            uptime_seconds=int(time.monotonic() - request.app.state.started_monotonic),
        ),
        stack=report.StackInfo(
            python=report.python_version(),
            nginx=report.packaged_version("nginx-mainline"),
            database=report.database_info(db, report.migration_head()),
            certificate=report.certificate_info(settings.server_name, now=now),
        ),
        container=report.container_info(now),
        parts=[*integration_parts(db), *collector_parts(db, settings, now)],
        diagnostics="",
    )
    return result.model_copy(update={"diagnostics": report.diagnostics(result)})
