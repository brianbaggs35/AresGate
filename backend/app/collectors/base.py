"""What a collector is: one regular job that reads from one kind of connection.

A collector holds no state. It is handed everything it needs for one run in a ``Context``: the
connection with its secrets opened, a client that checks the address, the certificate and logs
every request (the same one the settings pages use), and a way to write to the database."""

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import ClassVar

from sqlalchemy.orm import Session

from app.config import Settings
from app.devices import store as devices
from app.devices.sighting import NewSighting
from app.events import store as events
from app.events.event import NewEvent
from app.integrations.client import ApiClient, Target
from app.metrics import store as metrics
from app.metrics.sample import NewSample
from app.models import utcnow


class CollectorFailed(Exception):
    """A run that didn't work. The message says why, for whoever reads the status page, so it
    holds nothing secret."""


@dataclass(frozen=True)
class Outcome:
    """What a run that worked came to."""

    # How many things it collected, for a collector that counts them.
    items: int | None = None


@dataclass(frozen=True)
class Context:
    """Everything a collector gets for one run."""

    target: Target
    client: ApiClient
    # When the run began.
    now: datetime
    # When the connection's settings were last saved, as of loading them. A collector that keeps
    # what it learned about the connection checks that this still holds first, so an answer from
    # the old settings never lands on the new ones.
    settings_version: datetime
    new_session: Callable[[], Session]
    settings: Settings

    async def record(self, new: Sequence[NewEvent]) -> int:
        """Stores the events a run read, in a session of its own, and returns how many were new:
        one stored already, or older than its source keeps events, is skipped, so reading the
        same window twice is harmless."""
        return await self.save(lambda db: events.record(db, self.settings, new, utcnow()))

    async def record_unseen(self, new: Sequence[NewEvent]) -> int:
        """Stores the events a run read that have no time of their own, dated by this run, and
        returns how many were new: one whose identity is stored already is skipped, whenever
        that was, so reading the same thing every minute is harmless."""
        return await self.save(lambda db: events.record_unseen(db, self.settings, new, utcnow()))

    async def record_samples(self, samples: Sequence[NewSample]) -> int:
        """Stores the numbers a run measured, in a session of its own, and returns how many were
        new: a series read at the same moment twice, or at a moment older than its source keeps
        samples, is skipped, so reading the same moment twice is harmless."""
        return await self.save(lambda db: metrics.record(db, self.settings, samples, utcnow()))

    async def record_devices(self, sightings: Sequence[NewSighting]) -> int:
        """Remembers the devices a run saw, in a session of its own, and returns how many
        different ones there were. A device seen before is updated, so reading the same list
        twice is harmless."""
        return await self.save(lambda db: devices.record(db, sightings, utcnow()))

    async def save[T](self, work: Callable[[Session], T]) -> T:
        """Runs ``work`` with a session of its own, off the event loop, and commits it."""
        return await asyncio.to_thread(self._save, work)

    def _save[T](self, work: Callable[[Session], T]) -> T:
        with self.new_session() as db:
            result = work(db)
            db.commit()
            return result


class Collector(ABC):
    """A job to run on every connection it applies to."""

    # What its health record and the status page call it: lowercase words and hyphens.
    key: ClassVar[str]
    title: ClassVar[str]
    # One sentence on what it does, for the integration's page.
    summary: ClassVar[str]
    # How long after a run that worked the next one starts.
    interval: ClassVar[timedelta]
    # A run that takes longer than this is stopped and counts as a failure.
    timeout: ClassVar[timedelta]
    # Which connections it applies to; left out, it applies to every one.
    integration: ClassVar[str | None] = None
    connection: ClassVar[str | None] = None
    # The module it reads from. It doesn't run on a connection that has switched the module off.
    module: ClassVar[str | None] = None

    @classmethod
    def reads(cls, integration: str, connection: str) -> bool:
        return cls.integration in (None, integration) and cls.connection in (None, connection)

    @abstractmethod
    async def collect(self, context: Context) -> Outcome:
        """One run. Raises ``CollectorFailed`` when it can't do its job."""
