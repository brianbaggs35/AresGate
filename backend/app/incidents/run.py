"""The loop that files signals into incidents, running beside the collectors that store them."""

import asyncio
import logging
from collections.abc import Callable
from datetime import timedelta

from sqlalchemy.orm import Session

from app.incidents import engine
from app.models import utcnow

logger = logging.getLogger(__name__)

# Often enough that a new attack is an incident within a minute of its first alert.
INTERVAL = timedelta(seconds=30)


def correlate_once(new_session: Callable[[], Session]) -> engine.Result:
    """One run of the engine, saved."""
    with new_session() as db:
        result = engine.correlate(db, utcnow())
        db.commit()
    if result.events or result.merged:
        logger.info(
            "Filed %d signals: %d new incidents, %d updated, %d merged",
            result.events,
            result.created,
            result.updated,
            result.merged,
        )
    return result


async def run(
    new_session: Callable[[], Session],
    *,
    enabled: bool = True,
    interval: timedelta = INTERVAL,
) -> None:
    """Files signals, waits, and files again until cancelled. A failure (the database isn't up
    yet, or was restarted) is logged and tried again next time, because it must never stop the
    worker. When collecting is off nothing new is stored, so there is nothing to file."""
    while True:
        if enabled:
            try:
                # More than one run's worth waiting, such as after the worker was down: carry on.
                while (await asyncio.to_thread(correlate_once, new_session)).behind:
                    await asyncio.sleep(0)
            except Exception:
                logger.exception("Couldn't file the latest signals into incidents")
        await asyncio.sleep(interval.total_seconds())
