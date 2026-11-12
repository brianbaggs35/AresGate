"""The loop that asks each threat-intelligence service (VirusTotal, AlienVault OTX) about the
internet addresses of recent incidents, one lookup at a time and within that service's limits. It
runs in the worker, beside the collectors. It asks a service nothing until its connection has been
tested and has worked, and nothing while the service's own limit holds. Each service is asked for
what it has not answered yet, so an address is asked of each of them once.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.config import Settings
from app.integrations import netguard, registry, service
from app.integrations.client import Recorder, Target
from app.integrations.netguard import AddressPolicy
from app.integrations.registry import ConnectionDef, IntegrationDef
from app.intel import budget, candidates, connection, otx, store, subjects, virustotal
from app.intel.answers import Answer, Failed
from app.intel.subjects import Subject
from app.models import IntegrationConnection, utcnow

logger = logging.getLogger(__name__)

# How often the loop asks whether it may look one up. Its own lookups are spaced further apart by
# the access level (four minutes on the free key), so most of these checks find that it may not.
INTERVAL = timedelta(seconds=15)


@dataclass(frozen=True)
class Feed:
    """One service the loop asks: its integration, how to ask it, and the limits its settings
    choose."""

    name: str
    provider: str
    definition: IntegrationDef
    ask: Callable[[Target, Recorder, AddressPolicy, Subject, datetime], Awaitable[Answer]]
    level_of: Callable[[Mapping[str, str | int]], budget.Level]
    # What an answer says of the connection, kept on it: only VirusTotal's limits do.
    remember: Callable[[IntegrationConnection, Answer, datetime], None] | None = None

    @property
    def connection(self) -> ConnectionDef:
        return self.definition.connections[0]


VIRUSTOTAL = Feed(
    name="VirusTotal",
    provider=virustotal.PROVIDER,
    definition=registry.VIRUSTOTAL,
    ask=virustotal.ask,
    level_of=budget.level_of,
    remember=lambda row, answer, now: connection.remember(row, answer, now),
)
ALIENVAULT_OTX = Feed(
    name="AlienVault OTX",
    provider=otx.PROVIDER,
    definition=registry.ALIENVAULT_OTX,
    ask=otx.ask,
    level_of=budget.otx_level_of,
)
FEEDS: tuple[Feed, ...] = (VIRUSTOTAL, ALIENVAULT_OTX)
# VirusTotal is the one a person searches by hand, so the pages that do speak of it alone.
DEFINITION = VIRUSTOTAL.definition
CONNECTION = VIRUSTOTAL.connection


def _start(
    new_session: Callable[[], Session], settings: Settings, feed: Feed
) -> tuple[Target, Subject, int] | None:
    """Picks the address to ask the service about, and keeps that a request is about to be made if
    the limits allow one now. Returns the connection to ask with, what is asked about and the
    lookup's id."""
    with new_session() as db:
        now = utcnow()
        store.prune(db, feed.provider, now)
        row = service.rows_for(db, feed.definition.key).get(feed.connection.key)
        if row is None or row.last_success_at is None:
            db.commit()
            return None
        if budget.paused(db, feed.provider, now) is not None:
            db.commit()
            return None
        address = candidates.next_address(db, feed.provider, now)
        if address is None:
            db.commit()
            return None
        try:
            target = service.load_target(db, settings, feed.definition, feed.connection, row)
            lookup_id = budget.reserve(
                db,
                feed.provider,
                feed.level_of(row.options),
                now,
                background=True,
                address=address,
            )
        except service.Incomplete, budget.Wait:
            db.commit()
            return None
        db.commit()
        return target, subjects.of_address(address), lookup_id


def _finish(
    new_session: Callable[[], Session],
    feed: Feed,
    lookup_id: int,
    subject: Subject,
    answer: Answer,
    asked_at: datetime,
) -> None:
    with new_session() as db:
        store.finish(db, lookup_id, subject, answer, asked_at)
        row = service.rows_for(db, feed.definition.key).get(feed.connection.key)
        if row is not None and feed.remember is not None:
            feed.remember(row, answer, utcnow())
        db.commit()


async def lookup_once(
    new_session: Callable[[], Session],
    settings: Settings,
    recorder: Recorder,
    feed: Feed = VIRUSTOTAL,
) -> bool:
    """Asks the service about one address if the limits allow it, and keeps what came back. Returns
    whether a lookup was made."""
    started = await asyncio.to_thread(_start, new_session, settings, feed)
    if started is None:
        return False
    target, subject, lookup_id = started
    policy = service.policy_for(feed.connection, netguard.HOME_NETWORK)
    asked_at = utcnow()
    answer = await feed.ask(target, recorder, policy, subject, asked_at)
    if isinstance(answer, Failed):
        logger.info("A %s lookup didn't give a report: %s", feed.name, answer.message)
    await asyncio.to_thread(_finish, new_session, feed, lookup_id, subject, answer, asked_at)
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
    because it must never stop the worker, and one service's failure doesn't hold up the other.
    When collecting is off nothing is asked."""
    while True:
        if enabled:
            for feed in FEEDS:
                try:
                    await lookup_once(new_session, settings, recorder, feed)
                except Exception:
                    logger.exception("Couldn't ask %s about an address", feed.name)
        await asyncio.sleep(interval.total_seconds())
