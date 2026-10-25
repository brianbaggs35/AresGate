"""Storing samples: what collectors call with the numbers they read."""

import math
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import Settings
from app.metrics import retention
from app.metrics.sample import NewSample
from app.models import MetricSample, MetricSeries
from app.partitions import METRIC_SAMPLES

# A clock this far ahead of AresGate's is taken to be a little off. Further than that, a sample's
# time can't be trusted, and a time years ahead would make a week of its own to hold it.
FUTURE_TOLERANCE = timedelta(minutes=5)


def record(db: Session, settings: Settings, samples: Sequence[NewSample], now: datetime) -> int:
    """Stores the samples that aren't stored yet, and returns how many were new. A sample of the
    same series at the same moment as one already kept is skipped, so a collector can read the
    same moment twice; so is one that isn't a number, and one older than its source keeps
    samples, which the next purge would remove at once; and one that claims to be from the future
    is stored as of now. The caller commits."""
    kept = retention.load(db, settings)
    wanted = [
        sample
        for sample in samples
        if math.isfinite(sample.value)
        and sample.sampled_at >= now - timedelta(days=kept.days(sample.source))
    ]
    if not wanted:
        return 0
    # Under the lock, so a purge can't drop the week these go into, or the series they are of,
    # between making it and writing.
    METRIC_SAMPLES.lock(db)
    series = _series(db, wanted)
    rows: list[dict[str, Any]] = [
        {
            "series_id": series[sample.fingerprint],
            "sampled_at": _when(sample.sampled_at, now),
            "source": sample.source,
            "value": sample.value,
        }
        for sample in wanted
    ]
    METRIC_SAMPLES.ensure(db, {METRIC_SAMPLES.containing(row["sampled_at"]) for row in rows})
    statement = (
        insert(MetricSample)
        .on_conflict_do_nothing(index_elements=["series_id", "sampled_at"])
        .returning(MetricSample.series_id)
    )
    return len(db.execute(statement, rows).all())


def _series(db: Session, samples: Sequence[NewSample]) -> dict[str, int]:
    """The id of the series each sample is of, by fingerprint, making the ones that are new."""
    wanted = {
        sample.fingerprint: {
            "fingerprint": sample.fingerprint,
            "source": sample.source,
            "connection": sample.connection,
            "name": sample.name,
            "labels": sample.clean_labels,
        }
        for sample in samples
    }
    db.execute(
        insert(MetricSeries).on_conflict_do_nothing(index_elements=["fingerprint"]),
        list(wanted.values()),
    )
    found = db.execute(
        select(MetricSeries.fingerprint, MetricSeries.id).where(
            MetricSeries.fingerprint.in_(wanted)
        )
    )
    return {fingerprint: series_id for fingerprint, series_id in found}


def _when(sampled_at: datetime, now: datetime) -> datetime:
    return now if sampled_at > now + FUTURE_TOLERANCE else sampled_at
