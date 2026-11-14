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

from sqlalchemy import (
    ColumnElement,
    Interval,
    and_,
    case,
    distinct,
    func,
    literal,
    or_,
    select,
    tuple_,
)
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.events.event import Severity
from app.incidents.attention import NEEDS_YOU_FROM, Standing, clauses, urgent_clause
from app.incidents.filters import inside_clause
from app.models import Device, Event, Incident, MetricSample, MetricSeries
from app.models.base import UTCDateTime
from app.threats import importance
from app.threats.settings import Tuning

# The firewall's byte counters, which only rise until the firewall restarts.
TRAFFIC_SOURCE = "opnsense"
TRAFFIC_IN = "interface.bytes_in"
TRAFFIC_OUT = "interface.bytes_out"

# What an event is called when it is an alert (an intrusion rule, a Wazuh rule) and when it is a
# connection the firewall refused. The firewall's log gives a block the lowest severity above
# info and a pass none.
IS_ALERT = Event.kind == "alert"
# An alert that is the first of its kind, not one another program reported moments after it
# (app/events/twins.py).
IS_ORIGINAL = and_(IS_ALERT, Event.twin_of.is_(None))
# What makes one alert the same as another: the program, the words and the two ends. The same thing
# said again in the same stretch of time is one alert that happened many times
# (app/incidents/occurrences.py), not many.
_SAME = tuple_(
    Event.source,
    func.coalesce(Event.signature, Event.summary),
    Event.src_address,
    Event.dst_address,
    Event.dst_port,
    Event.protocol,
)
IS_BLOCK = and_(Event.kind == "firewall", Event.severity >= Severity.LOW)

RECENT_ALERTS = 8
TOP_SOURCES = 8
# How many signatures the noise report lists, and how serious an alert has to be to be counted
# as serious in it: the same as the banner has always said.
NOISY_SIGNATURES = 6
SERIOUS_FROM = Severity.HIGH
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
    """The window and the one before it are counted in one pass over the events: the buckets are
    cut from the window's start, so those of the window before it fall at numbers below zero."""
    bucket = _binned(win, Event.occurred_at, win.bucket)
    rows = db.execute(
        select(bucket, func.count())
        .where(matches, Event.occurred_at >= win.previous_start, Event.occurred_at < win.end)
        .group_by(bucket)
    ).all()
    per_bucket = [0] * len(win.buckets())
    previous = 0
    for start, count in rows:
        if start < win.start:
            previous += count
        else:
            per_bucket[(start - win.start) // win.bucket] = count
    return Counted(sum(per_bucket), previous, per_bucket)


def blocked(db: Session, win: Window) -> Counted:
    """The connections the firewall refused."""
    return _count(db, win, IS_BLOCK)


@dataclass(frozen=True)
class Alerts:
    """The alerts in a window, by how serious they are. An alert is counted once for each stretch
    of time it happened in (a bucket of the window), however many times it was reported in it, and
    once if several programs reported it: ``reports`` is how many reports there were."""

    total: int
    previous: int
    # For each severity, how many in each bucket.
    by_severity: dict[Severity, list[int]]
    highest: Severity | None
    # How many times programs reported alerts, the repeats and the duplicates included.
    reports: int = 0
    # How many of those another program had already reported.
    duplicates: int = 0


def alerts(db: Session, win: Window) -> Alerts:
    """The alerts of the window and of the one before it, from one pass over the events. The buckets
    are cut from the window's start, so those of the window before it fall at numbers below zero,
    and what they are counted for is how many times each was reported (``reports``) and how many of
    those another program had already reported (``duplicates``)."""
    bucket = _binned(win, Event.occurred_at, win.bucket)
    rows = db.execute(
        select(
            bucket,
            Event.severity,
            func.count(distinct(_SAME)).filter(Event.twin_of.is_(None)),
            func.count(),
            func.count().filter(Event.twin_of.is_not(None)),
        )
        .where(IS_ALERT, Event.occurred_at >= win.previous_start, Event.occurred_at < win.end)
        .group_by(bucket, Event.severity)
    ).all()
    by_severity = {level: [0] * len(win.buckets()) for level in Severity}
    previous = reports = duplicates = 0
    for start, severity, count, reported, repeated in rows:
        if start < win.start:
            previous += count
            continue
        by_severity[Severity(severity)][(start - win.start) // win.bucket] += count
        reports += reported
        duplicates += repeated
    present = [level for level, counts in by_severity.items() if any(counts)]
    return Alerts(
        total=sum(sum(counts) for counts in by_severity.values()),
        previous=previous,
        by_severity=by_severity,
        highest=max(present, default=None),
        reports=reports,
        duplicates=duplicates,
    )


@dataclass(frozen=True)
class SourceAlerts:
    """What one program reported as alerts in a window."""

    source: str
    total: int
    # How many of them were high or critical, and how many were between two addresses that are
    # both on the owner's network.
    serious: int
    inside: int


def alerts_by_source(db: Session, win: Window) -> list[SourceAlerts]:
    """Which programs the alerts of a window came from, the one with most first: how many, how
    many of them serious and how many were between two addresses on the network. Where "3,642
    serious alerts" come from is the first question about a noisy dashboard."""
    count = func.count().label("count")
    rows = db.execute(
        select(
            Event.source,
            count,
            func.count().filter(Event.severity >= SERIOUS_FROM),
            func.count().filter(
                and_(inside_clause(Event.src_address), inside_clause(Event.dst_address))
            ),
        )
        .where(IS_ALERT, Event.occurred_at >= win.start, Event.occurred_at < win.end)
        .group_by(Event.source)
        .order_by(count.desc(), Event.source)
    ).all()
    return [SourceAlerts(*row) for row in rows]


@dataclass(frozen=True)
class NoisySignature:
    """One alert (a rule, a signature) that a program reported, and how often."""

    source: str
    # None for alerts that do not say which rule raised them.
    signature: str | None
    # The most serious it was.
    severity: Severity
    count: int
    # How many different addresses it came from and went to.
    from_addresses: int
    to_addresses: int
    first_at: datetime
    last_at: datetime


def noisy_signatures(
    db: Session, win: Window, limit: int = NOISY_SIGNATURES
) -> list[NoisySignature]:
    """The alerts that were reported most in a window, the most first: what to quiet if they are
    not worth hearing about, and what to look at if they are."""
    count = func.count().label("count")
    rows = db.execute(
        select(
            Event.source,
            Event.signature,
            func.max(Event.severity),
            count,
            func.count(Event.src_address.distinct()),
            func.count(Event.dst_address.distinct()),
            func.min(Event.occurred_at),
            func.max(Event.occurred_at),
        )
        .where(IS_ALERT, Event.occurred_at >= win.start, Event.occurred_at < win.end)
        .group_by(Event.source, Event.signature)
        .order_by(count.desc(), Event.source, Event.signature)
        .limit(limit)
    ).all()
    return [
        NoisySignature(source, signature, Severity(severity), total, sources, targets, first, last)
        for source, signature, severity, total, sources, targets, first, last in rows
    ]


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


# Which way a refused connection was going, by where its two ends are: the internet knocking
# (``inbound``), one of your own devices reaching out (``outbound``) or one network of yours
# reaching another (``inside``). A line that names no source counts as the internet's.
_SIDE = case(
    (
        inside_clause(Event.src_address),
        case((inside_clause(Event.dst_address), "inside"), else_="outbound"),
    ),
    else_="inbound",
)
SIDES = ("inbound", "outbound", "inside")
TOP_PORTS = 6
TOP_DEVICES = 6


@dataclass(frozen=True)
class TriedPort:
    """A port the internet tried and the firewall refused."""

    port: int
    count: int


@dataclass(frozen=True)
class TurnedAway:
    """One of your own devices that the firewall stopped from connecting out."""

    address: IPv4Address | IPv6Address
    count: int
    # How many different addresses it tried to reach.
    destinations: int


@dataclass(frozen=True)
class Sides:
    """The connections the firewall refused in a window, by which way they were going, the ports
    the internet tried most, and the devices of yours that were turned away most. The ones the
    internet tried are the firewall doing its job. A device of yours that is refused again and
    again is worth knowing: it is what a program that has gone wrong, or a compromised one that
    is reaching for its controller, looks like from the firewall."""

    inbound: int
    outbound: int
    inside: int
    ports: list[TriedPort]
    devices: list[TurnedAway]


def blocked_sides(
    db: Session, win: Window, ports: int = TOP_PORTS, devices: int = TOP_DEVICES
) -> Sides:
    """How the refused connections of a window split by direction, and the ports and devices."""
    within = (Event.occurred_at >= win.start, Event.occurred_at < win.end)
    rows = db.execute(select(_SIDE, func.count()).where(IS_BLOCK, *within).group_by(_SIDE))
    totals = dict(rows.all())
    count = func.count().label("count")
    tried = db.execute(
        select(Event.dst_port, count)
        .where(IS_BLOCK, _SIDE == "inbound", Event.dst_port.is_not(None), *within)
        .group_by(Event.dst_port)
        .order_by(count.desc(), Event.dst_port)
        .limit(ports)
    ).all()
    reaching = func.count(distinct(Event.dst_address)).label("destinations")
    turned_away = db.execute(
        select(Event.src_address, count, reaching)
        .where(IS_BLOCK, _SIDE == "outbound", Event.src_address.is_not(None), *within)
        .group_by(Event.src_address)
        .order_by(count.desc(), Event.src_address)
        .limit(devices)
    ).all()
    return Sides(
        inbound=totals.get("inbound", 0),
        outbound=totals.get("outbound", 0),
        inside=totals.get("inside", 0),
        ports=[TriedPort(port, total) for port, total in tried if port is not None],
        devices=[
            TurnedAway(address, total, destinations)
            for address, total, destinations in turned_away
            if address is not None
        ],
    )


def recent_alerts(db: Session, win: Window, limit: int = RECENT_ALERTS) -> list[Event]:
    """The latest alerts in a window, the newest first."""
    return list(
        db.scalars(
            select(Event)
            .where(IS_ORIGINAL, Event.occurred_at >= win.start, Event.occurred_at < win.end)
            .order_by(Event.occurred_at.desc(), Event.id.desc())
            .limit(limit)
        )
    )


def marked_incidents(
    db: Session,
    win: Window,
    limit: int = MARKED_INCIDENTS,
    floor: int = NEEDS_YOU_FROM,
    tuning: Tuning | None = None,
) -> list[Incident]:
    """The incidents worth a flag on the charts, in the order they began: those that were going on
    in the window and are serious enough, that are not background (the owner's verdicts and the
    AI's judgement leave them out) and have not been dismissed. If there are more than there is
    room for, the most serious are kept, then the surest and the most recent."""
    by = clauses(floor, tuning)
    chosen = (
        select(Incident)
        .where(
            Incident.first_seen_at < win.end,
            Incident.last_seen_at >= win.start,
            Incident.status != "dismissed",
            Incident.severity >= MARKED_FROM,
            ~or_(by[Standing.MUTED], by[Standing.UNSURE], by[Standing.AI_CLEARED]),
        )
        .order_by(Incident.severity.desc(), importance.rank().desc(), Incident.last_seen_at.desc())
        .limit(limit)
    )
    return sorted(db.scalars(chosen), key=lambda incident: (incident.first_seen_at, incident.id))


@dataclass(frozen=True)
class Attention:
    """What the incidents that were going on in a window come to for the owner, and why the rest
    are not asked about. Each incident is counted once, for the first of these that is true."""

    # How many incidents were going on in the window.
    incidents: int
    # The confidence an incident needs to be asked about.
    floor: int
    # Already dealt with: resolved, or dismissed.
    handled: int
    # Called not suspicious or low priority by a verdict, so they never raise an alarm.
    muted: int
    # Not sure enough: AresGate's confidence in them is below the floor.
    unsure: int
    # Set aside by an AI that judged them background (noise or a probe) and was sure.
    cleared: int
    # What is left: they need the owner. How many of those are threats: highly likely to be real.
    needs_you: int
    urgent: int


def attention(
    db: Session, win: Window, floor: int = NEEDS_YOU_FROM, tuning: Tuning | None = None
) -> Attention:
    """How many of the incidents that were going on in a window need the owner, and how many were
    filtered out, by the reason. The Needs you lane and the Incidents page ask for the same ones
    (open or investigating, no quiet verdict, at least the floor in confidence, going on since the
    window began), so the number on the banner is the number they list."""
    going = and_(Incident.first_seen_at < win.end, Incident.last_seen_at >= win.start)
    by = clauses(floor, tuning)
    row = db.execute(
        select(
            func.count(),
            func.count().filter(by[Standing.HANDLED]),
            func.count().filter(by[Standing.MUTED]),
            func.count().filter(by[Standing.UNSURE]),
            func.count().filter(by[Standing.AI_CLEARED]),
            func.count().filter(by[Standing.NEEDS_YOU]),
            func.count().filter(urgent_clause(floor, tuning)),
        ).where(going)
    ).one()
    total, handled, muted, unsure, cleared, needs_you, urgent = row
    return Attention(total, floor, handled, muted, unsure, cleared, needs_you, urgent)


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


def traffic(db: Session, win: Window, source: str = TRAFFIC_SOURCE) -> list[Traffic]:
    """The speed of each of a program's interfaces (the firewall's, unless another is asked for),
    worked out from the byte counters it keeps: the bytes that passed between the last readings
    of two buckets, over the seconds between them, so a counter that went back to zero is a gap
    and not a speed of minus anything."""
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
            MetricSeries.source == source,
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
