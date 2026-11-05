"""The loop that has the AI judge the kinds of incident and read the incidents as they come in,
running beside the one that files them.

It judges first: a family of incidents (app/ai/families.py) is one request for all of them, and
what it learns is what lets the incidents after it be set aside without being read one by one.
How much it does without being asked is the owner's choice (the usage level, see
``triage.POLICIES``). With AI off, or no provider chosen, it asks nothing.
"""

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.ai import families, gateway, triage
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


def _prepare_families(
    db: Session, context: Context, ids: list[int], now: datetime
) -> tuple[Prepared | Unavailable, list[families.Facts]]:
    question, found = families.question_for(db, ids)
    prepared = gateway.prepare(db, context, question, now)
    db.commit()
    return prepared, found


def _finish_families(
    db: Session, found: list[families.Facts], prepared: Prepared, sent: gateway.Sent
) -> families.Outcome:
    now = utcnow()
    answer = gateway.record(db, prepared, sent, now)
    # The request is kept whatever came of the answer.
    db.commit()
    outcome = families.keep(db, found, answer, now)
    db.commit()
    return outcome


async def judge_families(
    new_session: Callable[[], Session], context: Context, ids: list[int]
) -> families.Outcome:
    """Has the AI judge families and keeps what it said."""
    with new_session() as db:
        prepared, found = await asyncio.to_thread(_prepare_families, db, context, ids, utcnow())
        if isinstance(prepared, Unavailable):
            return families.NotJudged(prepared.reason)
        if not found:
            return families.NotJudged("None of those has an incident going on.")
        sent = await gateway.send(prepared, context)
        return await asyncio.to_thread(_finish_families, db, found, prepared, sent)


def _plan_families(new_session: Callable[[], Session]) -> list[int]:
    with new_session() as db:
        return families.plan(db, utcnow())


async def judge_once(new_session: Callable[[], Session], context: Context) -> int:
    """One run of judging: the families the usage level asks for, in one request. Gives back how
    many it judged."""
    ids = await asyncio.to_thread(_plan_families, new_session)
    if not ids:
        return 0
    outcome = await judge_families(new_session, context, ids)
    if isinstance(outcome, families.NotJudged):
        logger.warning("The AI didn't judge the families: %s", outcome.reason)
        return 0
    logger.info(
        "The AI judged %d families, an answer for %d incidents", outcome.families, outcome.incidents
    )
    return outcome.families


def _plan(new_session: Callable[[], Session]) -> list[int]:
    with new_session() as db:
        chosen = triage.plan(db, utcnow())
        db.commit()
    return chosen


async def read_once(new_session: Callable[[], Session], context: Context) -> int:
    """One run: judges the families the usage level asks for, then reads the incidents it asks
    for, most serious first, and gives back how many it did in all. It stops at the first that
    can't be read (the provider is down, or the answer was unusable), because the next would most
    likely fail the same way."""
    judged = await judge_once(new_session, context)
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
    return read + judged


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
