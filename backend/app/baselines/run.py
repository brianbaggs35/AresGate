"""The loop that learns what is normal and says what is not, running in the worker beside the
collectors and the incident engine."""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.orm import Session

from app.baselines import destinations, devices, traffic
from app.config import Settings
from app.events import store
from app.models import utcnow

logger = logging.getLogger(__name__)

# Often enough that a new device or a place a device has not been to is an incident within
# minutes, and seldom enough that it is a small share of the database's time.
INTERVAL = timedelta(minutes=5)


@dataclass(frozen=True)
class Result:
    """What a run found: how many deviations of each kind were stored."""

    traffic: int = 0
    destinations: int = 0
    devices: int = 0

    @property
    def total(self) -> int:
        return self.traffic + self.destinations + self.devices


def learn_once(new_session: Callable[[], Session], settings: Settings) -> Result:
    """One run, saved: what the stored metrics, events and devices say is normal is learned again
    where it is time to, and what deviates is stored as events for the incident engine."""
    now = utcnow()
    with new_session() as db:
        traffic.learn(db, now)
        found = traffic.detect(db, now)
        spoken = destinations.run(db, now)
        appeared = devices.run(db, now)
        stored = store.record(db, settings, [*found, *spoken, *appeared], now)
        db.commit()
    result = Result(len(found), len(spoken), len(appeared))
    if stored:
        logger.info(
            "Learned baselines found %d deviations: %d traffic, %d destinations, %d devices",
            result.total,
            result.traffic,
            result.destinations,
            result.devices,
        )
    return result


async def run(
    new_session: Callable[[], Session],
    settings: Settings,
    *,
    enabled: bool = True,
    interval: timedelta = INTERVAL,
) -> None:
    """Learns, waits and learns again until cancelled. A failure is logged and tried again next
    time, because it must never stop the worker. Turned off, it learns nothing."""
    while True:
        if enabled:
            try:
                await asyncio.to_thread(learn_once, new_session, settings)
            except Exception:
                logger.exception("Couldn't learn what is normal on the network")
        await asyncio.sleep(interval.total_seconds())
