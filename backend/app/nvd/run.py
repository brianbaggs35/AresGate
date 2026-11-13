"""The loop that asks NVD about the CVEs that incidents name, one at a time and inside its limits.
It runs in the worker, beside the collectors and the threat-intelligence loop, and asks nothing
until the connection has been tested and has worked.

NVD allows 5 requests in a rolling 30 seconds without a key and 50 with one, and suggests waiting
six seconds between requests. A request goes out at most every ``SPACING_WITHOUT_KEY`` without a
key (three of the five, which leaves room for the connection test) and every ``SPACING_WITH_KEY``
with one. When nothing is wanted the queue isn't read again for ``IDLE``, and a CVE whose lookup
failed isn't tried again for ``RETRY``.
"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.config import Settings
from app.integrations import netguard, registry, service
from app.integrations.client import Recorder, Target
from app.models import utcnow
from app.nvd import lookup, queue, store

logger = logging.getLogger(__name__)

DEFINITION = registry.NVD
CONNECTION = DEFINITION.connections[0]
# How often the loop asks whether it may look one up. Lookups are spaced further apart than this.
INTERVAL = timedelta(seconds=2)
SPACING_WITHOUT_KEY = timedelta(seconds=10)
SPACING_WITH_KEY = timedelta(seconds=3)
IDLE = timedelta(minutes=5)
RETRY = timedelta(hours=1)


def spacing_of(target: Target) -> timedelta:
    """How long to wait after a request, by whether the key is sent."""
    return (
        SPACING_WITH_KEY if lookup.access_of(target.options) == lookup.KEY else SPACING_WITHOUT_KEY
    )


@dataclass
class Pace:
    """When the next lookup may go, and which CVEs failed and are left alone until then. Kept in
    the worker's memory: after a restart the first lookup goes at once, which is no more than one
    request."""

    not_before: datetime | None = None
    left_alone: dict[str, datetime] = field(default_factory=dict[str, datetime])

    def waiting(self, now: datetime) -> bool:
        return self.not_before is not None and now < self.not_before

    def skipping(self, now: datetime) -> frozenset[str]:
        self.left_alone = {cve: until for cve, until in self.left_alone.items() if until > now}
        return frozenset(self.left_alone)


def _start(
    new_session: Callable[[], Session], settings: Settings, pace: Pace
) -> tuple[Target, str] | None:
    """Picks the CVE to ask about, if the limits and the queue allow one now. Returns the
    connection to ask with and the CVE."""
    now = utcnow()
    if pace.waiting(now):
        return None
    with new_session() as db:
        row = service.rows_for(db, DEFINITION.key).get(CONNECTION.key)
        if row is None or row.last_success_at is None:
            return None
        cve_id = queue.next_wanted(db, now, skip=pace.skipping(now))
        if cve_id is None:
            pace.not_before = now + IDLE
            return None
        try:
            target = service.load_target(db, settings, DEFINITION, CONNECTION, row)
        except service.Incomplete:
            return None
    pace.not_before = now + spacing_of(target)
    return target, cve_id


def _finish(
    new_session: Callable[[], Session], cve_id: str, answer: lookup.Answer, asked_at: datetime
) -> None:
    with new_session() as db:
        store.keep(db, cve_id, answer, asked_at)
        db.commit()


async def lookup_once(
    new_session: Callable[[], Session], settings: Settings, recorder: Recorder, pace: Pace
) -> bool:
    """Asks NVD about one CVE if the limits allow it, and keeps what came back. Returns whether a
    lookup was made."""
    started = await asyncio.to_thread(_start, new_session, settings, pace)
    if started is None:
        return False
    target, cve_id = started
    policy = service.policy_for(CONNECTION, netguard.HOME_NETWORK)
    asked_at = utcnow()
    answer = await lookup.ask(target, recorder, policy, cve_id, asked_at)
    if isinstance(answer, lookup.Throttled):
        pace.not_before = max(pace.not_before or answer.until, answer.until)
    elif isinstance(answer, lookup.Failed):
        logger.info("An NVD lookup didn't give a record: %s", answer.message)
        pace.left_alone[cve_id] = asked_at + RETRY
    await asyncio.to_thread(_finish, new_session, cve_id, answer, asked_at)
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
                logger.exception("Couldn't ask NVD about a CVE")
        await asyncio.sleep(interval.total_seconds())
