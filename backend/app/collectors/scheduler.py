"""Runs the collectors: one asyncio task for each collector on each connection, a pause between
its runs, a longer pause after each failure, and a limit on how many run at once.

Which connections exist is looked at again every few seconds, so connecting an integration
starts its collectors, disconnecting it stops them, and saving its settings again runs them
straight away. Every run goes through ``ApiClient``, so the address checks, the certificate
checks and the API log are the same as for the settings pages."""

import asyncio
import logging
import zlib
from collections.abc import Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collectors import health, store
from app.collectors.base import Collector, CollectorFailed, Context
from app.collectors.registry import COLLECTORS
from app.collectors.store import Wanted
from app.config import Settings
from app.integrations import service
from app.integrations.client import ApiClient, CallFailed, Recorder, Target
from app.integrations.netguard import AddressPolicy, Refused
from app.models import IntegrationConnection, utcnow

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Timing:
    """How often the scheduler does things. The tests make these small."""

    # How often it looks at which connections exist, and tells the status page it is alive.
    tick: timedelta = timedelta(seconds=15)
    # How long to wait after a collector's first failure; each one after doubles it.
    retry: timedelta = timedelta(seconds=30)
    # The first runs are spread over this long, so a restart doesn't ask every integration at once.
    spread: timedelta = timedelta(seconds=30)
    # How many collectors may run at the same time.
    slots: int = 4


@dataclass
class _Job:
    wanted: Wanted
    # Set to run again now, because the connection's settings were saved.
    wake: asyncio.Event = field(default_factory=asyncio.Event)
    # Made as soon as the job is, because it runs the job.
    task: asyncio.Task[None] = field(init=False)


class Scheduler:
    def __init__(
        self,
        settings: Settings,
        new_session: Callable[[], Session],
        recorder: Recorder,
        policy: AddressPolicy,
        *,
        enabled: bool = True,
        collectors: Sequence[Collector] = COLLECTORS,
        timing: Timing = Timing(),  # noqa: B008  # frozen, so one shared copy is safe
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._settings = settings
        self._new_session = new_session
        self._recorder = recorder
        self._policy = policy
        self._enabled = enabled
        self._collectors = collectors
        self._timing = timing
        self._clock = clock
        self._slots = asyncio.Semaphore(timing.slots)
        self._jobs: dict[store.JobKey, _Job] = {}
        self._started = clock()

    # ---- Running forever ----------------------------------------------------------------

    async def run(self) -> None:
        """Keeps the collectors running until cancelled, then stops them. When collecting is
        turned off it only says it is alive, which is how the status page can tell off from
        stopped."""
        try:
            while True:
                await self.tick()
                await asyncio.sleep(self._timing.tick.total_seconds())
        finally:
            await self._stop()

    async def tick(self) -> None:
        """Looks at which connections exist and says the worker is alive. A failure (the
        database isn't up yet, or was restarted) is logged and tried again next time, because
        it must never stop the worker."""
        try:
            if self._enabled:
                await self._refresh()
            await asyncio.to_thread(self._beat)
        except Exception:
            logger.exception("The collector scheduler couldn't reach the database")

    async def _refresh(self) -> None:
        items = {item.key: item for item in await asyncio.to_thread(self._sync)}
        for key in [key for key in self._jobs if key not in items]:
            await self._stop_job(self._jobs.pop(key))
        for key, item in items.items():
            job = self._jobs.get(key)
            if job is None:
                job = self._jobs[key] = _Job(item)
                job.task = asyncio.create_task(self._loop(job), name=f"collector {key}")
            elif job.wanted.version != item.version:
                # Its settings were saved: run again now with them.
                job.wanted = item
                job.wake.set()

    async def _stop(self) -> None:
        for job in self._jobs.values():
            await self._stop_job(job)
        self._jobs.clear()

    @staticmethod
    async def _stop_job(job: _Job) -> None:
        job.task.cancel()
        await asyncio.wait({job.task})

    async def _loop(self, job: _Job) -> None:
        await self._pause(job, self._stagger(job.wanted))
        while True:
            try:
                delay = await self._run(job.wanted, job.wake)
            except Exception:
                logger.exception("Couldn't keep how %s went", job.wanted.collector.key)
                delay = self._timing.retry
            await self._pause(job, delay)

    @staticmethod
    async def _pause(job: _Job, delay: timedelta) -> None:
        with suppress(TimeoutError):
            await asyncio.wait_for(job.wake.wait(), delay.total_seconds())

    def _stagger(self, item: Wanted) -> timedelta:
        """Where in the spread this job starts: the same for the same job every time, so a
        restart doesn't shuffle them, and different between jobs."""
        share = zlib.crc32("/".join(item.key).encode()) / 2**32
        return min(self._timing.spread, item.collector.interval) * share

    # ---- Running once -------------------------------------------------------------------

    async def run_once(self) -> None:
        """Runs every wanted collector once, now, and waits for them. For the end-to-end tests,
        which need a run to happen when they say."""
        items = await asyncio.to_thread(self._sync)
        await asyncio.gather(*(self._run(item, asyncio.Event()) for item in items))

    async def _run(self, item: Wanted, wake: asyncio.Event) -> timedelta:
        """One run of a collector, kept in its health record. Returns how long to wait."""
        # Cleared as the run begins, so settings saved while it runs make it run again.
        wake.clear()
        started = self._clock()
        async with self._slots:
            error, items = await self._attempt(item, started)
        finished = self._clock()

        def delay_after(failures: int) -> timedelta:
            return health.retry_delay(item.collector.interval, failures, self._timing.retry)

        failures = await asyncio.to_thread(
            self._finish, item, started, finished, error, items, delay_after
        )
        return delay_after(failures)

    async def _attempt(self, item: Wanted, started: datetime) -> tuple[str | None, int | None]:
        """Runs the collector. Returns why it failed, if it did, and how many things it found."""
        collector = item.collector
        try:
            async with asyncio.timeout(collector.timeout.total_seconds()):
                target, version = await asyncio.to_thread(self._load, item)
                async with ApiClient(target, self._recorder, self._policy) as client:
                    outcome = await collector.collect(
                        Context(target, client, started, version, self._new_session)
                    )
        except (CollectorFailed, service.Incomplete, Refused, CallFailed) as failure:
            return str(failure), None
        except TimeoutError:
            return f"Didn't finish within {collector.timeout.total_seconds():g} seconds.", None
        except Exception:
            logger.exception(
                "%s failed on %s/%s", collector.key, item.definition.key, item.connection.key
            )
            return "Ran into a problem. The log has the details.", None
        return None, outcome.items

    # ---- The database -------------------------------------------------------------------

    def _sync(self) -> list[Wanted]:
        with self._new_session() as db:
            items = store.wanted(db, self._collectors)
            store.sync(db, items, self._clock())
            db.commit()
            return items

    def _load(self, item: Wanted) -> tuple[Target, datetime]:
        """The connection as it is saved now, with its secrets opened."""
        with self._new_session() as db:
            row = db.scalar(
                select(IntegrationConnection).where(
                    IntegrationConnection.integration == item.definition.key,
                    IntegrationConnection.connection == item.connection.key,
                )
            )
            if row is None:
                raise CollectorFailed("The connection was removed.")
            target = service.load_target(db, self._settings, item.definition, item.connection, row)
            return target, row.updated_at

    def _finish(
        self,
        item: Wanted,
        started: datetime,
        finished: datetime,
        error: str | None,
        items: int | None,
        delay_after: Callable[[int], timedelta],
    ) -> int:
        with self._new_session() as db:
            failures = store.finish(db, item, started, finished, error, items, delay_after)
            db.commit()
            return failures

    def _beat(self) -> None:
        with self._new_session() as db:
            store.beat(db, self._started, self._clock())
            db.commit()
