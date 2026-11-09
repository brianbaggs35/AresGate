"""The loop that asks VirusTotal about the internet addresses of recent incidents, one lookup at a
time and within the access level's limits. It runs in the worker, beside the collectors. It asks
nothing until the connection has been tested and has worked.
"""

import asyncio
import logging
from collections.abc import Callable
from datetime import timedelta

from sqlalchemy.orm import Session

from app.config import Settings
from app.integrations import netguard, registry, service
from app.integrations.client import ApiClient, CallFailed, Recorder, Target
from app.intel import budget, candidates, store, virustotal
from app.intel.candidates import Address
from app.models import utcnow

logger = logging.getLogger(__name__)

# At most one lookup every 15 seconds: the free API's 4 a minute, with nothing to spare.
INTERVAL = timedelta(seconds=15)
DEFINITION = registry.VIRUSTOTAL
CONNECTION = DEFINITION.connections[0]


def _start(
    new_session: Callable[[], Session], settings: Settings
) -> tuple[Target, Address, int] | None:
    """Picks the address to ask about, if the limits allow one now, and keeps that a request is
    about to be made. Returns the connection to ask with, the address and the lookup's id."""
    with new_session() as db:
        now = utcnow()
        store.prune(db, virustotal.PROVIDER, now)
        row = service.rows_for(db, DEFINITION.key).get(CONNECTION.key)
        if row is None or row.last_success_at is None:
            db.commit()
            return None
        if not budget.may_look_up(db, virustotal.PROVIDER, budget.level_of(row.options), now):
            db.commit()
            return None
        address = candidates.next_address(db, virustotal.PROVIDER, now)
        if address is None:
            db.commit()
            return None
        try:
            target = service.load_target(db, settings, DEFINITION, CONNECTION, row)
        except service.Incomplete:
            db.commit()
            return None
        lookup_id = store.record(db, virustotal.PROVIDER, address, now)
        db.commit()
        return target, address, lookup_id


def _finish(new_session: Callable[[], Session], lookup_id: int, answer: virustotal.Answer) -> None:
    with new_session() as db:
        store.finish(db, lookup_id, answer)
        db.commit()


async def lookup_once(
    new_session: Callable[[], Session], settings: Settings, recorder: Recorder
) -> bool:
    """Asks about one address if the limits allow it, and keeps what came back. Returns whether a
    lookup was made."""
    started = await asyncio.to_thread(_start, new_session, settings)
    if started is None:
        return False
    target, address, lookup_id = started
    try:
        async with ApiClient(target, recorder, netguard.PUBLIC_INTERNET) as client:
            answer = await virustotal.look_up(client, target, address, utcnow())
    except CallFailed as failure:
        answer = virustotal.Failed(str(failure))
    if isinstance(answer, virustotal.Failed):
        logger.info("A VirusTotal lookup didn't give a report: %s", answer.message)
    await asyncio.to_thread(_finish, new_session, lookup_id, answer)
    return True


async def run(
    new_session: Callable[[], Session],
    settings: Settings,
    recorder: Recorder,
    *,
    enabled: bool = True,
    interval: timedelta = INTERVAL,
) -> None:
    """Asks, waits, and asks again until cancelled. A failure is logged and tried again next time,
    because it must never stop the worker. When collecting is off nothing is asked."""
    while True:
        if enabled:
            try:
                await lookup_once(new_session, settings, recorder)
            except Exception:
                logger.exception("Couldn't ask VirusTotal about an address")
        await asyncio.sleep(interval.total_seconds())
