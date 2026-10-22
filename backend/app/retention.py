"""Deleting what has outlived its retention period, once when the API starts and again every
few hours after that."""

import asyncio
import logging
from collections.abc import Callable
from datetime import timedelta

from sqlalchemy.orm import Session

from app import audit
from app.config import Settings
from app.models import utcnow

logger = logging.getLogger(__name__)

# Often enough that the log never holds much more than the retention period asks for.
INTERVAL = timedelta(hours=6)


def purge_once(settings: Settings, new_session: Callable[[], Session]) -> int:
    """Deletes the audit events past their retention period, and returns how many there were."""
    with new_session() as db:
        return audit.purge_expired(db, settings, utcnow())


async def run(
    settings: Settings, new_session: Callable[[], Session], interval: timedelta = INTERVAL
) -> None:
    """Purges, waits, and purges again until cancelled. A failure (the database isn't up yet, or
    was restarted) is logged and tried again next time, because it must never stop the API."""
    while True:
        try:
            await asyncio.to_thread(purge_once, settings, new_session)
        except Exception:
            logger.exception("Couldn't delete the audit events past their retention period")
        await asyncio.sleep(interval.total_seconds())
