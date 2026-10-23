"""The API log: every request AresGate made to an integration, kept for a while so that when
an integration stops answering there is a record of what was asked and what came back."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.integrations.client import Call
from app.models import ApiCall

DEFAULT_PAGE = 50
MAX_PAGE = 200


class ApiLogRecorder:
    """Writes each call to the log in a session of its own, so an entry is kept even when the
    request that caused it is rolled back, and without holding up the event loop."""

    def __init__(self, new_session: Callable[[], Session]) -> None:
        self._new_session = new_session

    async def __call__(self, call: Call) -> None:
        await asyncio.to_thread(self._write, call)

    def _write(self, call: Call) -> None:
        with self._new_session() as db:
            db.add(
                ApiCall(
                    occurred_at=call.occurred_at,
                    integration=call.integration,
                    connection=call.connection,
                    method=call.method,
                    path=call.path,
                    status_code=call.status_code,
                    duration_ms=call.duration_ms,
                    error=call.error,
                )
            )
            db.commit()


@dataclass(frozen=True)
class Page:
    calls: list[ApiCall]
    # Pass this as ``before`` to get the page of older calls that follows, if there is one.
    next_before: int | None


def list_calls(
    db: Session,
    integration: str,
    *,
    connection: str | None = None,
    method: str | None = None,
    failed: bool | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    before: int | None = None,
    limit: int = DEFAULT_PAGE,
) -> Page:
    """An integration's calls, newest first. Each filter narrows the list, and ``before`` pages
    through it. A call failed if there is a reason recorded for it."""
    query = (
        select(ApiCall)
        .where(ApiCall.integration == integration)
        .order_by(ApiCall.id.desc())
        .limit(limit + 1)
    )
    if connection is not None:
        query = query.where(ApiCall.connection == connection)
    if method is not None:
        query = query.where(ApiCall.method == method.upper())
    if failed is not None:
        query = query.where(ApiCall.error.is_not(None) if failed else ApiCall.error.is_(None))
    if since is not None:
        query = query.where(ApiCall.occurred_at >= since)
    if until is not None:
        query = query.where(ApiCall.occurred_at < until)
    if before is not None:
        query = query.where(ApiCall.id < before)
    rows = list(db.scalars(query))
    if len(rows) <= limit:
        return Page(rows, None)
    kept = rows[:limit]
    return Page(kept, kept[-1].id)


def purge_expired(db: Session, settings: Settings, now: datetime) -> int:
    """Deletes the calls older than the retention period, and returns how many there were.
    Commits."""
    cutoff = now - timedelta(days=settings.api_log_retention_days)
    deleted = db.connection().execute(delete(ApiCall).where(ApiCall.occurred_at < cutoff)).rowcount
    db.commit()
    return deleted
