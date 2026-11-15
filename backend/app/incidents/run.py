"""The loop that files signals into incidents, running beside the collectors that store them."""

import asyncio
import logging
from collections.abc import Callable
from datetime import timedelta

from sqlalchemy.orm import Session

from app import wakeups
from app.incidents import engine, evidence
from app.models import utcnow
from app.threats import chains, drift, families

logger = logging.getLogger(__name__)

# Often enough that a new attack is an incident within a minute of its first alert.
INTERVAL = timedelta(seconds=30)


def correlate_once(new_session: Callable[[], Session]) -> engine.Result:
    """One run of the engine, saved."""
    with new_session() as db:
        result = engine.correlate(db, utcnow())
        # Signals filed before their evidence was kept get it, a batch at a time.
        evidence.read_pending(db)
        # The incidents it made or said differently join their families, and are told what those
        # have been judged.
        families.assign(db)
        # Incidents that are one attack across two devices are linked into a chain.
        chains.link(db, utcnow())
        # Kinds of incident that differ from what they were when judged are marked.
        drift.detect(db, utcnow())
        if result.created or result.updated or result.merged:
            wakeups.notify(db, wakeups.INCIDENTS)
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
    wake: wakeups.Signal | None = None,
    settle: timedelta = engine.SETTLE,
) -> None:
    """Files signals, waits, and files again until cancelled. Newly stored events wake it, and it
    then waits ``settle`` for them to settle before it files them, since the engine leaves alone
    what is newer. A failure (the database isn't up
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
        if await wakeups.pause(wake, interval):
            await asyncio.sleep(settle.total_seconds())
