"""The first collector: testing each connection every few minutes, as the Test button does, so
the integration's status and which of its services run stay current without anyone looking."""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collectors.base import Collector, CollectorFailed, Context, Outcome
from app.integrations import probes, service
from app.integrations.client import Target
from app.integrations.probes import Verdict
from app.models import IntegrationConnection


class ConnectionCheck(Collector):
    key = "connection-check"
    title = "Connection check"
    summary = (
        "Tests the connection every few minutes: that it answers, that the credentials still "
        "work and which of its services are running."
    )
    interval = timedelta(minutes=5)
    # A probe makes a handful of requests, each with a deadline of its own.
    timeout = timedelta(minutes=2)

    async def collect(self, context: Context) -> Outcome:
        target = context.target
        verdict = await probes.run(
            probes.PROBES[(target.integration, target.connection)], context.client, target
        )
        await context.save(
            lambda db: remember(db, target, verdict, context.now, context.settings_version)
        )
        if not verdict.ok:
            raise CollectorFailed(verdict.message)
        return Outcome()


def remember(
    db: Session, target: Target, verdict: Verdict, now: datetime, settings_version: datetime
) -> None:
    """Keeps how the check went on the connection, unless its settings were saved while the
    check ran: what it found out is about the old ones."""
    row = db.scalar(
        select(IntegrationConnection).where(
            IntegrationConnection.integration == target.integration,
            IntegrationConnection.connection == target.connection,
        )
    )
    if row is not None and row.updated_at == settings_version:
        service.record_attempt(row, verdict, now)
