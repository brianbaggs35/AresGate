"""How long samples are kept, for each source, and removing the ones past it.

A source keeps its samples for the days set for it, or else for
``ARESGATE_METRIC_RETENTION_DAYS``. How that works, and how the old ones go, is in
``app/retained.py``. A series that has no samples left goes with them."""

from sqlalchemy import delete, exists
from sqlalchemy.orm import Session

from app.models import MetricRetention, MetricSample, MetricSeries
from app.partitions import METRIC_SAMPLES
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


def _forget_series_without_samples(db: Session) -> None:
    db.execute(
        delete(MetricSeries).where(~exists().where(MetricSample.series_id == MetricSeries.id))
    )


_METRICS = Retained(
    weeks=METRIC_SAMPLES,
    model=MetricSample,
    time=MetricSample.sampled_at,
    source=MetricSample.source,
    policy=MetricRetention,
    default_days=lambda settings: settings.metric_retention_days,
    tidy=_forget_series_without_samples,
)

load = _METRICS.load
set_days = _METRICS.set_days
stored = _METRICS.stored
purge_expired = _METRICS.purge_expired
