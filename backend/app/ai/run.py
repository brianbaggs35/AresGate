"""The loop that has the AI read incidents as they come in, running beside the one that files them.

How much it reads without being asked is the owner's choice (the usage level in Settings > AI,
see ``triage.POLICIES``). With AI off, or no provider chosen, it reads nothing and asks nothing.
"""

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.ai import gateway, triage
from app.ai.gateway import Context, Prepared, Unavailable
from app.models import Incident, utcnow

logger = logging.getLogger(__name__)

# Often enough that a new attack is read within a minute or two of becoming an incident.
INTERVAL = timedelta(seconds=60)


def _prepare(
    db: Session, context: Context, incident_id: int, now: datetime
) -> Prepared | Unavailable | None:
    incident = db.get(Incident, incident_id)
    if incident is None:
        return None
    prepared = gateway.prepare(db, context, triage.question_for(db, incident), now)
    # Stand-ins made while preparing are kept, and the connection is let go while the AI thinks.
    db.commit()
    return prepared


def _finish(
    db: Session, incident_id: int, prepared: Prepared, sent: gateway.Sent
) -> triage.Outcome | None:
    now = utcnow()
    answer = gateway.record(db, prepared, sent, now)
    # What was asked is kept whatever became of the incident while the AI thought about it.
    db.commit()
    incident = db.get(Incident, incident_id, populate_existing=True)
    if incident is None:
        return None
    outcome = triage.keep(db, incident, answer, now)
    db.commit()
    return outcome


async def read_incident(
    new_session: Callable[[], Session], context: Context, incident_id: int
) -> triage.Outcome | None:
    """Has the AI read one incident and keeps what it said. None if the incident is gone."""
    with new_session() as db:
        prepared = await asyncio.to_thread(_prepare, db, context, incident_id, utcnow())
        if prepared is None:
            return None
        if isinstance(prepared, Unavailable):
            return triage.NotRead(prepared.reason)
        sent = await gateway.send(prepared, context)
        return await asyncio.to_thread(_finish, db, incident_id, prepared, sent)


def _plan(new_session: Callable[[], Session]) -> list[int]:
    with new_session() as db:
        chosen = triage.plan(db, utcnow())
        db.commit()
    return chosen


async def read_once(new_session: Callable[[], Session], context: Context) -> int:
    """One run: reads the incidents the usage level asks for, most serious first, and gives back
    how many it read. It stops at the first that can't be read (the provider is down, or the
    answer was unusable), because the next would most likely fail the same way."""
    read = 0
    for incident_id in await asyncio.to_thread(_plan, new_session):
        outcome = await read_incident(new_session, context, incident_id)
        if not isinstance(outcome, triage.Read):
            if outcome is not None:
                logger.warning("The AI didn't read incident %d: %s", incident_id, outcome.reason)
            break
        read += 1
    if read:
        logger.info("The AI read %d incidents", read)
    return read


async def run(
    new_session: Callable[[], Session],
    context: Context,
    *,
    enabled: bool = True,
    interval: timedelta = INTERVAL,
) -> None:
    """Reads, waits, and reads again until cancelled. A failure is logged and tried again next
    time, because it must never stop the worker. Where nothing is collected there are no
    incidents to read."""
    while True:
        if enabled:
            try:
                await read_once(new_session, context)
            except Exception:
                logger.exception("Couldn't have the AI read the latest incidents")
        await asyncio.sleep(interval.total_seconds())
