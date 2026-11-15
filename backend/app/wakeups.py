"""Telling the worker that there is something to do, so that it doesn't wait out its interval.

The loops in the worker look for work every few seconds or so. A change that one of them is
waiting for says so through PostgreSQL's ``NOTIFY``, and the worker, which ``LISTEN``s on one
connection of its own, wakes the loop that is waiting for it. The note is sent inside the
transaction that stores the change, so it reaches the worker only once the change is committed and
never for one that was rolled back.

A note is only a nudge. It carries nothing, and a loop that is woken looks in the database for what
there is, as it does when its interval runs out. The intervals stay as they were, so a note that is
lost (the connection was down, or the worker was not running) costs no more than the wait there was
before, and with notes turned off everything works as it did.
"""

import asyncio
import logging
from datetime import timedelta
from typing import Final

import psycopg
from psycopg import sql
from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.config import Settings

logger = logging.getLogger(__name__)

# Events were stored, and so signals may be waiting to be filed.
EVENTS: Final = "ag_events"
# Incidents were filed or changed, and so alerts may be due.
INCIDENTS: Final = "ag_incidents"
# An agent was asked to run.
AGENT_RUNS: Final = "ag_agent_runs"
CHANNELS: Final = (EVENTS, INCIDENTS, AGENT_RUNS)

# How long to wait before trying to listen again, from one failure to the next.
FIRST_RETRY: Final = 1.0
LONGEST_RETRY: Final = 30.0


def notify(db: Session, channel: str) -> None:
    """Tells the listening worker, once the caller commits, that there is something to do."""
    db.execute(select(func.pg_notify(channel, "")))


class Signal:
    """What a loop waits on: it ends the wait early when it is set."""

    def __init__(self) -> None:
        self._event = asyncio.Event()

    def set(self) -> None:
        self._event.set()

    async def wait(self, interval: timedelta) -> bool:
        """Waits for the signal for at most ``interval``, and says whether it came. A signal that
        came while the loop was busy ends the wait at once, and counts once however many there
        were."""
        try:
            async with asyncio.timeout(interval.total_seconds()):
                await self._event.wait()
        except TimeoutError:
            return False
        self._event.clear()
        return True


async def pause(signal: Signal | None, interval: timedelta) -> bool:
    """What a loop does between one look and the next: waits out its interval, or less if its
    signal comes. Without one it only waits. Says whether the signal came."""
    if signal is None:
        await asyncio.sleep(interval.total_seconds())
        return False
    return await signal.wait(interval)


class Wakeups:
    """The signals of the loops, by what they wait for."""

    def __init__(self) -> None:
        self.events = Signal()
        self.incidents = Signal()
        self.agent_runs = Signal()
        self._by_channel = {
            EVENTS: self.events,
            INCIDENTS: self.incidents,
            AGENT_RUNS: self.agent_runs,
        }

    def wake(self, channel: str) -> None:
        signal = self._by_channel.get(channel)
        if signal is not None:
            signal.set()

    def wake_all(self) -> None:
        for signal in self._by_channel.values():
            signal.set()


async def listen(
    settings: Settings,
    wakeups: Wakeups,
    *,
    first_retry: float = FIRST_RETRY,
    longest_retry: float = LONGEST_RETRY,
) -> None:
    """Listens for notes and wakes the loops they are for, until cancelled. When the connection
    is lost it is made again after a wait that doubles up to ``longest_retry``, and what was missed
    in between is made up for by waking every loop. The loss is logged once, and so is the
    recovery, however long it lasts."""
    url = make_url(settings.database_url)
    _, options = url.get_dialect()().create_connect_args(url)
    delay = first_retry
    lost = False
    while True:
        try:
            async with await psycopg.AsyncConnection.connect(**options, autocommit=True) as link:
                for channel in CHANNELS:
                    await link.execute(sql.SQL("LISTEN {}").format(sql.Identifier(channel)))
                if lost:
                    logger.info("Listening for what the worker waits for again")
                    lost = False
                delay = first_retry
                wakeups.wake_all()
                async for note in link.notifies():
                    wakeups.wake(note.channel)
        except Exception:
            if not lost:
                logger.warning(
                    "Can't listen for what the worker waits for; the loops go by their intervals"
                    " until it can",
                    exc_info=True,
                )
            lost = True
        await asyncio.sleep(delay)
        delay = min(delay * 2, longest_retry)
