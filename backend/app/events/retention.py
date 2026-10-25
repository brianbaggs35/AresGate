"""How long events are kept, for each source, and removing the ones past it.

A source keeps its events for the days set for it, or else for ``ARESGATE_EVENT_RETENTION_DAYS``.
How that works, and how the old ones go, is in ``app/retained.py``."""

from app.models import Event, EventRetention
from app.partitions import EVENTS
from app.retained import MAX_DAYS, MIN_DAYS, Purged, Retained, Retention, Stored

__all__ = [
    "MAX_DAYS",
    "MIN_DAYS",
    "Purged",
    "Retention",
    "Stored",
    "load",
    "purge_expired",
    "set_days",
    "stored",
]

_EVENTS = Retained(
    weeks=EVENTS,
    model=Event,
    time=Event.occurred_at,
    source=Event.source,
    policy=EventRetention,
    default_days=lambda settings: settings.event_retention_days,
)

load = _EVENTS.load
set_days = _EVENTS.set_days
stored = _EVENTS.stored
purge_expired = _EVENTS.purge_expired
