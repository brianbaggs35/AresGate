"""How much passes through each interface in an hour, and when it is far more than usual.

The volume of an hour is what a counter that only rises (``interface.bytes_in``) gained during it.
What is usual for an hour of the day is the median of that over the last four weeks, with the
median absolute deviation, scaled to stand for a standard deviation, to say how far is far; a
weekday and a weekend day are learned apart once there are enough of each. An hour is a deviation
when it is well beyond both: several spreads above the median, several times the median, and
more than a floor that keeps a quiet link's trickle from ever mattering. The hours learned from
stop two hours before now, so the hour that is judged is never part of what it is judged against."""

import statistics
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Final

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import aggregate_order_by, insert
from sqlalchemy.orm import Session

from app import baselines
from app.events.event import NewEvent, Severity
from app.models import MetricSample, MetricSeries, SystemInfo, TrafficBaseline

# The counters whose gain is a volume, and what each says in a sentence.
DIRECTIONS: Final = {"interface.bytes_in": "received", "interface.bytes_out": "sent"}
# How far back what is usual is learned from.
WINDOW: Final = timedelta(weeks=4)
# An hour needs this many readings (about one a minute) to be counted.
MIN_READINGS: Final = 30
# Hours of a kind of day needed to learn from. With fewer, any day's hours stand in.
MIN_HOURS: Final = 8
# What makes an hour a deviation: more than this many spreads above the median, more than this
# many times the median, and more than this many bytes.
SPREADS: Final = 6.0
FACTOR: Final = 3.0
FLOOR: Final = 50 * 1024 * 1024
# Seen as this many times the median or more, it is worth more than a low severity.
SERIOUS_FACTOR: Final = 10.0
# The spread is never smaller than this share of the median, so a very steady link doesn't make
# the smallest rise look like a flood.
MIN_SPREAD_SHARE: Final = 0.1
# 1.4826 turns a median absolute deviation into a standard deviation, for a normal distribution.
SCALE: Final = 1.4826
# Learned again when it is this old, and the first hour judged is not further back than this.
REFRESH: Final = timedelta(hours=6)
LOOK_BACK: Final = timedelta(hours=3)
# Between the hours learned from and now.
HOLD_BACK: Final = timedelta(hours=2)

LEARNED_KEY: Final = "baselines.traffic_learned"
CHECKED_KEY: Final = "baselines.traffic_checked"
ANY_DAY: Final = 48


def bucket_of(hour: datetime) -> int:
    """The bucket of an hour: its hour of the day, 24 more for a weekend day."""
    return hour.hour + (24 if hour.weekday() >= 5 else 0)


def _top(hour: datetime) -> datetime:
    return hour.replace(minute=0, second=0, microsecond=0)


def _volumes(db: Session, start: datetime, end: datetime) -> dict[int, dict[datetime, float]]:
    """What each series gained in each whole hour from ``start`` to ``end``, by series. An hour
    with too few readings, or in which the counter began again from nothing, is left out."""
    utc = func.timezone("UTC", MetricSample.sampled_at)
    hour = func.date_trunc("hour", utc)
    first = func.array_agg(aggregate_order_by(MetricSample.value, MetricSample.sampled_at.asc()))
    last = func.array_agg(aggregate_order_by(MetricSample.value, MetricSample.sampled_at.desc()))
    query = (
        select(MetricSample.series_id, hour, first[1], last[1])
        .join(MetricSeries, MetricSeries.id == MetricSample.series_id)
        .where(
            MetricSeries.name.in_(DIRECTIONS),
            MetricSample.sampled_at >= start,
            MetricSample.sampled_at < end,
        )
        .group_by(MetricSample.series_id, hour)
        .having(func.count() >= MIN_READINGS)
    )
    volumes: dict[int, dict[datetime, float]] = defaultdict(dict)
    for series_id, at, began, ended in db.execute(query):
        if ended >= began:
            volumes[series_id][at.replace(tzinfo=UTC)] = ended - began
    return volumes


def _stats(values: list[float]) -> tuple[float, float]:
    """The median, and the spread: the median absolute deviation made a standard deviation, and
    never less than a share of the median."""
    middle = statistics.median(values)
    deviation = statistics.median(abs(value - middle) for value in values) * SCALE
    return middle, max(deviation, middle * MIN_SPREAD_SHARE)


def learn(db: Session, now: datetime) -> int:
    """Learns what is usual for each series again, if it was last learned long enough ago, and
    returns how many series it learned. Nothing is learned from a series without enough hours."""
    done = db.get(SystemInfo, LEARNED_KEY)
    if done is not None and datetime.fromisoformat(done.value) > now - REFRESH:
        return 0
    end = _top(now) - HOLD_BACK
    learned = 0
    for series_id, hours in _volumes(db, end - WINDOW, end).items():
        buckets: dict[int, list[float]] = defaultdict(list)
        for hour, volume in hours.items():
            buckets[bucket_of(hour)].append(volume)
            buckets[ANY_DAY + hour.hour].append(volume)
        rows = [
            {
                "series_id": series_id,
                "bucket": bucket,
                "samples": len(values),
                "median": (stats := _stats(values))[0],
                "spread": stats[1],
                "updated_at": now,
            }
            for bucket, values in buckets.items()
            if len(values) >= MIN_HOURS
        ]
        db.execute(delete(TrafficBaseline).where(TrafficBaseline.series_id == series_id))
        if rows:
            db.execute(insert(TrafficBaseline), rows)
            learned += 1
    _remember(db, LEARNED_KEY, now)
    return learned


def _remember(db: Session, key: str, when: datetime) -> None:
    row = db.get(SystemInfo, key)
    if row is None:
        db.add(SystemInfo(key=key, value=when.isoformat()))
    else:
        row.value = when.isoformat()


def _usual(db: Session, series_id: int, hour: datetime) -> TrafficBaseline | None:
    """What is usual for this hour: that of its kind of day if there is enough of it, or else of
    any day."""
    rows = {
        row.bucket: row
        for row in db.scalars(
            select(TrafficBaseline).where(
                TrafficBaseline.series_id == series_id,
                TrafficBaseline.bucket.in_((bucket_of(hour), ANY_DAY + hour.hour)),
            )
        )
    }
    return rows.get(bucket_of(hour)) or rows.get(ANY_DAY + hour.hour)


def confidence_of(spreads_above: float) -> int:
    """How sure it is that an hour is not just a busy one: half at the line, and five more for
    each spread beyond it, up to 95."""
    return min(95, 50 + int(5 * (spreads_above - SPREADS)))


def _size(volume: float) -> str:
    units = ("bytes", "KB", "MB", "GB", "TB")
    amount = float(volume)
    for unit in units[:-1]:
        if amount < 1024:
            return f"{amount:.0f} {unit}" if unit == "bytes" else f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{amount:.1f} {units[-1]}"


def detect(db: Session, now: datetime) -> list[NewEvent]:
    """The hours that have ended since the last run (the last few, at most) that carried far
    more than is usual for them."""
    end = _top(now)
    checked = db.get(SystemInfo, CHECKED_KEY)
    start = max(
        end - LOOK_BACK,
        datetime.fromisoformat(checked.value) if checked is not None else end - LOOK_BACK,
    )
    events: list[NewEvent] = []
    names = {
        series.id: series
        for series in db.scalars(select(MetricSeries).where(MetricSeries.name.in_(DIRECTIONS)))
    }
    for series_id, hours in _volumes(db, start, end).items():
        series = names[series_id]
        for hour, volume in sorted(hours.items()):
            usual = _usual(db, series_id, hour)
            if usual is None or volume < FLOOR or volume < usual.median * FACTOR:
                continue
            above = (volume - usual.median) / usual.spread
            if above < SPREADS:
                continue
            events.append(_event(series, hour, volume, usual, above))
    _remember(db, CHECKED_KEY, end)
    return events


def _event(
    series: MetricSeries, hour: datetime, volume: float, usual: TrafficBaseline, above: float
) -> NewEvent:
    interface = series.labels.get("interface")
    where = f"Interface {interface}" if interface else "A network interface"
    times = volume / max(usual.median, 1.0)
    confidence = confidence_of(above)
    ended = hour + timedelta(hours=1)
    return NewEvent(
        source=baselines.SOURCE,
        connection=baselines.CONNECTION,
        kind=baselines.KIND,
        severity=Severity.MEDIUM if times >= SERIOUS_FACTOR else Severity.LOW,
        occurred_at=ended,
        identity=("traffic", series.fingerprint, hour.isoformat()),
        summary=(
            f"{where} {DIRECTIONS[series.name]} {_size(volume)} between {hour:%H:%M} and "
            f"{ended:%H:%M} UTC on {hour:%A}, {times:.0f} times the {_size(usual.median)} that is "
            f"usual for that hour."
        ),
        signature="Traffic far above what is usual",
        iface=interface,
        raw={
            "baseline": "traffic",
            "confidence": confidence,
            "observed_bytes": volume,
            "usual_bytes": usual.median,
            "spread_bytes": usual.spread,
            "hours_learned_from": usual.samples,
            "direction": DIRECTIONS[series.name],
            "hour": hour.isoformat(),
        },
    )
