"""The status page: what AresGate and the programs under it are doing, for when something seems
wrong. It is for someone signed in, and says nothing that is secret."""

import time
from collections.abc import Mapping

from fastapi import APIRouter, Depends, Request

from app import status as report
from app.api.deps import Db, SettingsDep, signed_in
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
        parts=integration_parts(db),
        diagnostics="",
    )
    return result.model_copy(update={"diagnostics": report.diagnostics(result)})
