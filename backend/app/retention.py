"""Deleting what has outlived its retention period, once when the API starts and again every
few hours after that."""

import asyncio
import logging
from collections.abc import Callable
from datetime import timedelta

from sqlalchemy.orm import Session

from app import audit, quota, retention_policy
from app.ai import retention as ai
from app.alerts import log as alerts
from app.config import Settings
from app.events import retention as events
from app.integrations import apilog
from app.metrics import retention as metrics
from app.models import utcnow

logger = logging.getLogger(__name__)

# Often enough that the log never holds much more than the retention period asks for.
INTERVAL = timedelta(hours=6)
# How often the database is measured against its quota, if there is one: a quick question that
# only does something when the database is over.
QUOTA_INTERVAL = timedelta(minutes=15)


def purge_once(settings: Settings, new_session: Callable[[], Session]) -> int:
    """Deletes the audit events, the API log entries, the record of AI requests and the
    integrations' events and samples past their retention periods, and returns how many audit
    events there were. Where the owner keeps everything forever (on the Retention page), nothing is
    deleted."""
    with new_session() as db:
        now = utcnow()
        chosen = retention_policy.load(db)
        if not chosen.deletes_by_age:
            return 0
        settings = chosen.apply(settings)
        apilog.purge_expired(db, settings, now)
        ai.purge_expired(db, settings, now)
        alerts.purge_expired(db, settings, now)
        purged = audit.purge_expired(db, settings, now)
        removed = events.purge_expired(db, settings, now)
        if removed.deleted or removed.partitions_dropped:
            logger.info(
                "Removed %d events past their retention period and dropped %d old weeks of events",
                removed.deleted,
                removed.partitions_dropped,
            )
        measured = metrics.purge_expired(db, settings, now)
        if measured.deleted or measured.partitions_dropped:
            logger.info(
                "Removed %d metric samples past their retention period and dropped %d old weeks"
                " of samples",
                measured.deleted,
                measured.partitions_dropped,
            )
        return purged


def enforce_quota(new_session: Callable[[], Session]) -> quota.Enforced | None:
    """Brings the database under the size the owner allowed, if they set one, by dropping the oldest
    weeks of events and samples."""
    with new_session() as db:
        return quota.enforce(db, retention_policy.load(db), utcnow())


async def run(
    settings: Settings,
    new_session: Callable[[], Session],
    interval: timedelta = INTERVAL,
    quota_interval: timedelta = QUOTA_INTERVAL,
) -> None:
    """Purges, then keeps the database within its quota and purges again after ``interval``, until
    cancelled. A failure (the database isn't up yet, or was restarted) is logged and tried again
    next time, because it must never stop the API, and one of the two failing doesn't stop the
    other."""
    loop = asyncio.get_running_loop()
    last_purge: float | None = None
    while True:
        if last_purge is None or loop.time() - last_purge >= interval.total_seconds():
            last_purge = loop.time()
            try:
                await asyncio.to_thread(purge_once, settings, new_session)
            except Exception:
                logger.exception("Couldn't delete the logs and events past their retention period")
        try:
            await asyncio.to_thread(enforce_quota, new_session)
        except Exception:
            logger.exception("Couldn't keep the database within its quota")
        await asyncio.sleep(min(interval, quota_interval).total_seconds())
