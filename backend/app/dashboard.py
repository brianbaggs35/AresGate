"""What the dashboard shows, worked out from the events and measurements that are stored: how many
alerts and blocked connections there were over a window of time and in the window before it, when
they happened, who was blocked most, the latest alerts, how fast traffic went and which devices
are new.

Each is its own function over a ``Window``, so the pages that go deeper and the AI analyst's tools
can ask the same questions the dashboard does and get the same answers."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address, IPv6Address

from sqlalchemy import ColumnElement, Interval, and_, func, literal, or_, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.events.event import Severity
from app.incidents.verdicts import MUTING
from app.models import Device, Event, Incident, MetricSample, MetricSeries
from app.models.base import UTCDateTime

# The firewall's byte counters, which only rise until the firewall restarts.
TRAFFIC_SOURCE = "opnsense"
TRAFFIC_IN = "interface.bytes_in"
TRAFFIC_OUT = "interface.bytes_out"

# What an event is called when it is an alert (an intrusion rule, a Wazuh rule) and when it is a
# connection the firewall refused. The firewall's log gives a block the lowest severity above
# info and a pass none.
IS_ALERT = Event.kind == "alert"
IS_BLOCK = and_(Event.kind == "firewall", Event.severity >= Severity.LOW)

RECENT_ALERTS = 8
TOP_SOURCES = 8
# How many incidents are marked on the charts, and how serious one has to be to be marked: a
# chart with a flag for every low-severity scan says nothing.
MARKED_INCIDENTS = 12
MARKED_FROM = Severity.MEDIUM


@dataclass(frozen=True)
class Window:
    """A stretch of time that ends now, cut into equal buckets that the counts and the traffic
    are given by. The window before it, of the same length, is what it is compared with."""

    key: str
    start: datetime
    end: datetime
    bucket: timedelta
    traffic_bucket: timedelta

    @property
    def length(self) -> timedelta:
        return self.end - self.start

    @property
    def previous_start(self) -> datetime:
        return self.start - self.length

    def buckets(self, size: timedelta | None = None) -> list[datetime]:
        """When each bucket starts."""
        size = size or self.bucket
        return [self.start + size * number for number in range(self.length // size)]


# The windows people can ask for: how long, and how finely the counts and the traffic are cut.
_WINDOWS = {
    "24h": (timedelta(hours=24), timedelta(hours=1), timedelta(minutes=15)),
    "7d": (timedelta(days=7), timedelta(hours=6), timedelta(hours=1)),
}
WINDOWS = tuple(_WINDOWS)
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def window(key: str, now: datetime) -> Window:
    """The window of that name that ends with the bucket `now` is in, so its buckets start on
    whole hours (or the bucket's own size) and the last one is the one still filling."""
    length, bucket, traffic_bucket = _WINDOWS[key]
    end = _EPOCH + bucket * -((_EPOCH - now) // bucket)
    return Window(key, end - length, end, bucket, traffic_bucket)


@dataclass(frozen=True)
class Counted:
    """How many there were in a window and in the one before it, and how many in each bucket."""

    total: int
    previous: int
    per_bucket: list[int]


def _binned(
    win: Window, column: InstrumentedAttribute[datetime], size: timedelta
) -> ColumnElement[datetime]:
    """Which bucket a time is in, as the bucket's start."""
    return func.date_bin(
        literal(size, Interval()), column, literal(win.start, UTCDateTime()), type_=UTCDateTime()
    )


def _count(db: Session, win: Window, matches: ColumnElement[bool]) -> Counted:
    bucket = _binned(win, Event.occurred_at, win.bucket)
    rows = db.execute(
        select(bucket, func.count())
        .where(matches, Event.occurred_at >= win.start, Event.occurred_at < win.end)
        .group_by(bucket)
    ).all()
    per_bucket = [0] * len(win.buckets())
    for start, count in rows:
        per_bucket[(start - win.start) // win.bucket] = count
    previous = db.scalar(
        select(func.count()).where(
            matches, Event.occurred_at >= win.previous_start, Event.occurred_at < win.start
        )
    )
    return Counted(sum(per_bucket), previous or 0, per_bucket)


def blocked(db: Session, win: Window) -> Counted:
    """The connections the firewall refused."""
    return _count(db, win, IS_BLOCK)


@dataclass(frozen=True)
class Alerts:
    """The alerts in a window, by how serious they are."""

    total: int
    previous: int
    # For each severity, how many in each bucket.
    by_severity: dict[Severity, list[int]]
    highest: Severity | None


def alerts(db: Session, win: Window) -> Alerts:
    bucket = _binned(win, Event.occurred_at, win.bucket)
    rows = db.execute(
        select(bucket, Event.severity, func.count())
        .where(IS_ALERT, Event.occurred_at >= win.start, Event.occurred_at < win.end)
        .group_by(bucket, Event.severity)
    ).all()
    by_severity = {level: [0] * len(win.buckets()) for level in Severity}
    for start, severity, count in rows:
        by_severity[Severity(severity)][(start - win.start) // win.bucket] += count
    present = [level for level, counts in by_severity.items() if any(counts)]
    previous = db.scalar(
        select(func.count()).where(
            IS_ALERT, Event.occurred_at >= win.previous_start, Event.occurred_at < win.start
        )
    )
    return Alerts(
        total=sum(sum(counts) for counts in by_severity.values()),
        previous=previous or 0,
        by_severity=by_severity,
        highest=max(present, default=None),
    )


@dataclass(frozen=True)
class Source:
    """Who a number of blocked connections came from."""

    address: IPv4Address | IPv6Address
    count: int


def top_blocked_sources(db: Session, win: Window, limit: int = TOP_SOURCES) -> list[Source]:
    """The addresses the firewall refused most in a window, the most first."""
    count = func.count().label("count")
    rows = db.execute(
        select(Event.src_address, count)
        .where(
            IS_BLOCK,
            Event.src_address.is_not(None),
            Event.occurred_at >= win.start,
            Event.occurred_at < win.end,
        )
        .group_by(Event.src_address)
        .order_by(count.desc(), Event.src_address)
        .limit(limit)
    ).all()
    return [Source(address, total) for address, total in rows if address is not None]


def recent_alerts(db: Session, win: Window, limit: int = RECENT_ALERTS) -> list[Event]:
    """The latest alerts in a window, the newest first."""
    return list(
        db.scalars(
            select(Event)
            .where(IS_ALERT, Event.occurred_at >= win.start, Event.occurred_at < win.end)
            .order_by(Event.occurred_at.desc(), Event.id.desc())
            .limit(limit)
        )
    )


def marked_incidents(db: Session, win: Window, limit: int = MARKED_INCIDENTS) -> list[Incident]:
    """The incidents worth a flag on the charts, in the order they began: those that were going on
    in the window and are serious enough, whose owner has not dismissed them or said they are not
    suspicious or low priority. If there are more than there is room for, the most serious are
    kept, then the surest and the most recent."""
    chosen = (
        select(Incident)
        .where(
            Incident.first_seen_at < win.end,
            Incident.last_seen_at >= win.start,
            Incident.status != "dismissed",
            Incident.severity >= MARKED_FROM,
            or_(Incident.verdict.is_(None), Incident.verdict.not_in(MUTING)),
        )
        .order_by(
            Incident.severity.desc(), Incident.confidence.desc(), Incident.last_seen_at.desc()
        )
        .limit(limit)
    )
    return sorted(db.scalars(chosen), key=lambda incident: (incident.first_seen_at, incident.id))


@dataclass(frozen=True)
class Traffic:
    """How fast one network interface went, in bits a second, for each bucket. None where there
    is no telling: the firewall wasn't read in that bucket or the one before, or it restarted and
    its counters began again."""

    interface: str
    received: list[float | None]
    sent: list[float | None]
    # How many bytes passed in the window, to put the busiest first.
    bytes: float


def traffic(db: Session, win: Window) -> list[Traffic]:
    """The speed of each of the firewall's interfaces, worked out from the byte counters it keeps:
    the bytes that passed between the last readings of two buckets, over the seconds between them,
    so a counter that went back to zero is a gap and not a speed of minus anything."""
    size = win.traffic_bucket
    bucket = _binned(win, MetricSample.sampled_at, size)
    interface = MetricSeries.labels["interface"].astext
    rows = db.execute(
        select(
            MetricSeries.name,
            interface,
            bucket,
            func.max(MetricSample.sampled_at),
            func.max(MetricSample.value),
        )
        .join(MetricSample, MetricSample.series_id == MetricSeries.id)
        .where(
            MetricSeries.source == TRAFFIC_SOURCE,
            MetricSeries.name.in_((TRAFFIC_IN, TRAFFIC_OUT)),
            MetricSample.sampled_at >= win.start - size,
            MetricSample.sampled_at < win.end,
        )
        .group_by(MetricSeries.name, interface, bucket)
    ).all()
    # The last reading in each bucket, for each counter of each interface.
    last: dict[tuple[str, str], dict[int, tuple[datetime, float]]] = defaultdict(dict)
    for name, label, start, at, value in rows:
        last[(label or "", name)][(start - win.start) // size] = (at, value)
    count = len(win.buckets(size))
    found: dict[str, Traffic] = {}
    for (label, name), readings in sorted(last.items(), key=lambda item: item[0]):
        speeds = [_speed(readings.get(number - 1), readings.get(number)) for number in range(count)]
        edge = found.setdefault(label, Traffic(label, [None] * count, [None] * count, 0.0))
        (edge.received if name == TRAFFIC_IN else edge.sent)[:] = speeds
    return sorted(
        (
            Traffic(
                item.interface,
                item.received,
                item.sent,
                sum(speed for speed in item.received + item.sent if speed is not None)
                * size.total_seconds()
                / 8,
            )
            for item in found.values()
        ),
        key=lambda item: (-item.bytes, item.interface),
    )


def _speed(
    before: tuple[datetime, float] | None, after: tuple[datetime, float] | None
) -> float | None:
    """Bits a second between two readings of a counter."""
    if before is None or after is None:
        return None
    seconds = (after[0] - before[0]).total_seconds()
    if seconds <= 0 or after[1] < before[1]:
        return None
    return (after[1] - before[1]) * 8 / seconds


@dataclass(frozen=True)
class Devices:
    """How many devices there are, and how many were first seen in a window."""

    total: int
    new: int


def devices(db: Session, win: Window) -> Devices:
    total = db.scalar(select(func.count()).select_from(Device)) or 0
    new = db.scalar(
        select(func.count()).where(
            Device.first_seen_at >= win.start, Device.first_seen_at < win.end
        )
    )
    return Devices(total, new or 0)
