"""The loop that asks Fingerbank what each device is, one device at a time and within its limits.
It runs in the worker, beside the collectors and the threat-intelligence loop. It asks nothing
until the connection has been tested and works, and nothing while a limit holds: Fingerbank's
request to wait is not an error, and neither is a quiet network with nothing left to ask about.
"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.config import Settings
from app.fingerbank import lookup, queue, store
from app.fingerbank.queue import Wanted
from app.integrations import netguard, registry, service
from app.integrations.client import Recorder, Target
from app.integrations.probes import Verdict
from app.integrations.service import Status
from app.models import utcnow

logger = logging.getLogger(__name__)

DEFINITION = registry.FINGERBANK
CONNECTION = DEFINITION.connections[0]
# How often the loop asks whether it may look one up. Its own lookups are spaced further apart.
INTERVAL = timedelta(seconds=5)
# How long it leaves the devices alone when none is left to ask about.
IDLE = timedelta(minutes=1)


@dataclass
class Pace:
    """What the loop has learned that holds its lookups, kept while it runs: a limit Fingerbank
    set, or a time with nothing to ask about. Neither needs to outlive a restart."""

    until: datetime | None = None

    def holding(self, now: datetime) -> bool:
        return self.until is not None and now < self.until

    def hold(self, until: datetime) -> None:
        self.until = until


def incident_devices(target: Target) -> bool:
    """Whether the owner allowed the devices in incidents and threats to be asked about."""
    return target.options.get("incident_devices") == "yes"


def _start(
    new_session: Callable[[], Session], settings: Settings, pace: Pace
) -> tuple[Target, Wanted] | None:
    """Picks the device to ask about, if the connection works and the limits allow a request now.
    Returns the connection to ask with and the device."""
    with new_session() as db:
        now = utcnow()
        row = service.rows_for(db, DEFINITION.key).get(CONNECTION.key)
        if row is None or service.connection_status(row) is not Status.CONNECTED:
            return None
        if not queue.may_ask(db, now):
            return None
        try:
            target = service.load_target(db, settings, DEFINITION, CONNECTION, row)
        except service.Incomplete:
            return None
        wanted = queue.next_wanted(db, now, incidents=incident_devices(target))
        db.commit()
        if wanted is None:
            pace.hold(now + IDLE)
            return None
        return target, wanted


def _finish(
    new_session: Callable[[], Session],
    wanted: Wanted,
    answer: lookup.Identified | lookup.Unknown | lookup.Failed,
    now: datetime,
) -> None:
    with new_session() as db:
        if isinstance(answer, lookup.Failed):
            row = service.rows_for(db, DEFINITION.key).get(CONNECTION.key)
            if row is not None and answer.refused:
                service.record_attempt(row, Verdict(False, answer.message), now)
        else:
            store.save(db, wanted, answer, now)
        db.commit()


async def lookup_once(
    new_session: Callable[[], Session],
    settings: Settings,
    recorder: Recorder,
    pace: Pace | None = None,
) -> bool:
    """Asks Fingerbank about one device if the limits allow it, and keeps what came back. Returns
    whether a request was made."""
    pace = pace or Pace()
    if pace.holding(utcnow()):
        return False
    started = await asyncio.to_thread(_start, new_session, settings, pace)
    if started is None:
        return False
    target, wanted = started
    policy = service.policy_for(CONNECTION, netguard.HOME_NETWORK)
    asked_at = utcnow()
    answer = await lookup.ask(target, recorder, policy, wanted.mac, asked_at)
    if isinstance(answer, lookup.Throttled):
        pace.hold(answer.until)
        return True
    if isinstance(answer, lookup.Failed):
        logger.info("A Fingerbank lookup didn't give an answer: %s", answer.message)
        pace.hold(asked_at + (lookup.THROTTLE if answer.refused else lookup.RETRY))
    await asyncio.to_thread(_finish, new_session, wanted, answer, asked_at)
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
    pace = Pace()
    while True:
        if enabled:
            try:
                await lookup_once(new_session, settings, recorder, pace)
            except Exception:
                logger.exception("Couldn't ask Fingerbank about a device")
        await asyncio.sleep(interval.total_seconds())
