"""One asset's page: what AresGate knows of a single asset, as the integrations and its own records
tell it.

The asset is the one the Assets list shows (see ``inventory``), and it is read the same way. What is
added here is read for that asset alone: each address with when it was first and last seen, the
programs that list it, the events its addresses were in, the addresses it talked to and that talked
to it (with the ports used, and what threat intelligence has kept of each), its traffic as ntopng
measured it, the incidents its addresses are in and the verdicts the owner has given about them.
Each is a recent window, so a page is a few small reads. An asset on the Internet side is not an
asset, so it has no page."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from ipaddress import IPv4Address, IPv6Address
from typing import Final

from sqlalchemy import ColumnElement, case, func, literal_column, or_, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.assets import inventory
from app.assets.inventory import Asset, Network
from app.intel import store as intel_store
from app.intel import virustotal
from app.models import (
    DeviceAddress,
    Event,
    Incident,
    IntelSubject,
    MetricSample,
    MetricSeries,
    VerdictRule,
)

Address = IPv4Address | IPv6Address

# How far back the events and the peers are read: the week a person looks over.
DAY: Final = timedelta(days=1)
WEEK: Final = timedelta(days=7)
# How many of each the page shows: the most recent events, the most often seen peers.
EVENTS_SHOWN: Final = 25
PEERS_SHOWN: Final = 8
PORTS_SHOWN: Final = 4
INCIDENTS_SHOWN: Final = 10
VERDICTS_SHOWN: Final = 20
# The traffic of the week, hour by hour, and in the blocks of a day it is shown by.
HOURS: Final = 24 * 7
HOURS_PER_DAY: Final = 24
# What ntopng keeps for each host: the bytes it has sent and received, which only ever rise.
SENT: Final = "host.bytes_sent"
RECEIVED: Final = "host.bytes_received"


@dataclass(frozen=True)
class AddressSeen:
    """An address the asset has had, and whether it has it now."""

    address: Address
    current: bool
    first_seen_at: datetime
    last_seen_at: datetime


@dataclass(frozen=True)
class EventSeen:
    """An event one of the asset's addresses was in, as the program that reported it saw it."""

    id: int
    occurred_at: datetime
    source: str
    kind: str
    severity: int
    summary: str
    signature: str | None
    src_address: Address | None
    src_port: int | None
    dst_address: Address | None
    dst_port: int | None
    protocol: str | None


@dataclass(frozen=True)
class PortSeen:
    """A port the asset's traffic with a peer used at the far end, and how many events it was in."""

    port: int
    protocol: str | None
    events: int


@dataclass(frozen=True)
class Standing:
    """What threat intelligence has kept of a peer: the judgement, and the counts behind it."""

    judgement: str
    malicious: int
    suspicious: int
    engines: int
    owner: str | None
    country: str | None
    checked_at: datetime


@dataclass(frozen=True)
class Peer:
    """Another address the asset's traffic went to, or came from, and how many events it was in.
    ``ports`` are the ports at the far end, the most often used first. ``standing`` is what threat
    intelligence kept of it, or none if nothing is kept, or if it is an address on a network of its
    own, which is never sent to a service."""

    address: Address
    events: int
    last_seen_at: datetime
    ports: tuple[PortSeen, ...] = ()
    standing: Standing | None = None
    internal: bool = False


@dataclass(frozen=True)
class Reading:
    """What was sent and received in a stretch of time, in bytes. None where nothing was measured
    in it, which is not the same as nothing having been sent."""

    at: datetime
    sent: float | None
    received: float | None


@dataclass(frozen=True)
class Traffic:
    """The asset's traffic over the last week: by the hour, and by the block of a day. ``measured``
    says whether ntopng measured any of it."""

    measured: bool
    hours: tuple[Reading, ...]
    days: tuple[Reading, ...]


@dataclass(frozen=True)
class IncidentSeen:
    """An incident one of the asset's addresses is in, as it stands."""

    id: int
    title: str
    severity: int
    confidence: int
    status: str
    verdict: str | None
    last_seen_at: datetime
    signal_count: int
    sources: tuple[str, ...]


@dataclass(frozen=True)
class VerdictSeen:
    """A verdict the owner gave about one of the asset's addresses."""

    id: int
    verdict: str
    address: Address | None
    destination: str | None
    source: str | None
    signature: str | None
    note: str | None
    created_at: datetime


@dataclass(frozen=True)
class Detail:
    """Everything the page of one asset shows."""

    asset: Asset
    # The interfaces it is on, by name, as the Assets page names them.
    networks: tuple[Network, ...]
    addresses: tuple[AddressSeen, ...]
    events: tuple[EventSeen, ...]
    # How many events its addresses were in, in the last day and in the last week.
    events_day: int
    events_week: int
    # Where its traffic went, and where it came from, most often first.
    talks_to: tuple[Peer, ...]
    contacted_by: tuple[Peer, ...]
    traffic: Traffic
    incidents: tuple[IncidentSeen, ...]
    verdicts: tuple[VerdictSeen, ...]


def load(db: Session, key: str, now: datetime) -> Detail | None:
    """The page of one asset as of ``now``, or none when no asset on the list has that key: it is
    not one, or it is on the Internet side and so left out of the list."""
    found = inventory.load(db, now)
    asset = next((item for item in found.assets if item.key == key), None)
    if asset is None:
        return None
    addresses = list(asset.addresses)
    events, events_day, events_week = _events(db, addresses, now)
    return Detail(
        asset=asset,
        networks=tuple(network for network in found.networks if network.id in asset.interfaces),
        addresses=_addresses(db, asset),
        events=events,
        events_day=events_day,
        events_week=events_week,
        talks_to=_peers(db, Event.src_address, Event.dst_address, addresses, now - WEEK),
        contacted_by=_peers(db, Event.dst_address, Event.src_address, addresses, now - WEEK),
        traffic=_traffic(db, addresses, now),
        incidents=_incidents(db, addresses),
        verdicts=_verdicts(db, addresses),
    )


def _device(key: str) -> int | None:
    """The id of the device a page is for, or none for a machine with no hardware address."""
    kind, _, number = key.partition("-")
    return int(number) if kind == "device" else None


def _addresses(db: Session, asset: Asset) -> tuple[AddressSeen, ...]:
    """Each address the asset has had, with when it was first and last seen. A device's come from
    its own rows; one a machine merged into it has only the asset's times."""
    rows: dict[Address, DeviceAddress] = {}
    device = _device(asset.key)
    if device is not None:
        rows = {
            row.address: row
            for row in db.scalars(select(DeviceAddress).where(DeviceAddress.device_id == device))
        }
    current = set(asset.addresses[: asset.current])
    found: list[AddressSeen] = []
    for address in asset.addresses:
        row = rows.get(address)
        found.append(
            AddressSeen(
                address=address,
                current=address in current,
                first_seen_at=row.first_seen_at if row is not None else asset.first_seen_at,
                last_seen_at=row.last_seen_at if row is not None else asset.last_seen_at,
            )
        )
    return tuple(found)


def _involving(addresses: list[Address]) -> ColumnElement[bool]:
    """The events an address of the asset is the source or the destination of."""
    return or_(Event.src_address.in_(addresses), Event.dst_address.in_(addresses))


def _events(
    db: Session, addresses: list[Address], now: datetime
) -> tuple[tuple[EventSeen, ...], int, int]:
    """The latest events its addresses were in, and how many there were in the last day and in the
    last week."""
    if not addresses:
        return (), 0, 0
    involved = _involving(addresses)
    day, week = db.execute(
        select(
            func.count().filter(Event.occurred_at >= now - DAY),
            func.count(),
        ).where(involved, Event.occurred_at >= now - WEEK)
    ).one()
    rows = db.scalars(
        select(Event)
        .where(involved, Event.occurred_at >= now - WEEK)
        .order_by(Event.occurred_at.desc(), Event.id.desc())
        .limit(EVENTS_SHOWN)
    )
    shown = tuple(
        EventSeen(
            id=row.id,
            occurred_at=row.occurred_at,
            source=row.source,
            kind=row.kind,
            severity=row.severity,
            summary=row.summary,
            signature=row.signature,
            src_address=row.src_address,
            src_port=row.src_port,
            dst_address=row.dst_address,
            dst_port=row.dst_port,
            protocol=row.protocol,
        )
        for row in rows
    )
    return shown, int(day), int(week)


def _peers(
    db: Session,
    ours: InstrumentedAttribute[Address | None],
    theirs: InstrumentedAttribute[Address | None],
    addresses: list[Address],
    since: datetime,
) -> tuple[Peer, ...]:
    """The other addresses one side of an event is at, when the asset's addresses are on the other,
    most often seen first. The asset's own addresses are not peers of its own."""
    rows = db.execute(
        select(theirs, func.count(), func.max(Event.occurred_at))
        .where(
            ours.in_(addresses),
            theirs.is_not(None),
            theirs.not_in(addresses),
            Event.occurred_at >= since,
        )
        .group_by(theirs)
        .order_by(func.count().desc(), func.max(Event.occurred_at).desc())
        .limit(PEERS_SHOWN)
    ).all()
    peers = [(address, count, last) for address, count, last in rows if address is not None]
    ports = _ports(db, ours, theirs, addresses, [address for address, _, _ in peers], since)
    standing = intel_store.answers_for(
        db, virustotal.PROVIDER, [address for address, _, _ in peers if address.is_global]
    )
    return tuple(
        Peer(
            address=address,
            events=count,
            last_seen_at=last,
            ports=ports.get(address, ()),
            standing=_standing(standing.get(address)),
            internal=not address.is_global,
        )
        for address, count, last in peers
    )


def _ports(
    db: Session,
    ours: InstrumentedAttribute[Address | None],
    theirs: InstrumentedAttribute[Address | None],
    addresses: list[Address],
    peers: list[Address],
    since: datetime,
) -> dict[Address, tuple[PortSeen, ...]]:
    """The ports at the far end of the asset's events with each peer, the most often used first.
    The far end is the event's destination: the service the one side reached on the other."""
    if not peers:
        return {}
    rows = db.execute(
        select(theirs, Event.dst_port, Event.protocol, func.count())
        .where(
            ours.in_(addresses),
            theirs.in_(peers),
            Event.dst_port.is_not(None),
            Event.occurred_at >= since,
        )
        .group_by(theirs, Event.dst_port, Event.protocol)
        .order_by(func.count().desc(), Event.dst_port)
    ).all()
    found: dict[Address, list[PortSeen]] = {}
    for address, port, protocol, count in rows:
        if address is None or port is None:  # pragma: no cover - the query leaves these out
            continue
        seen = found.setdefault(address, [])
        if len(seen) < PORTS_SHOWN:
            seen.append(PortSeen(port=port, protocol=protocol, events=count))
    return {address: tuple(seen) for address, seen in found.items()}


def _standing(kept: IntelSubject | None) -> Standing | None:
    """What a kept answer says of a peer, as the page shows it."""
    if kept is None:
        return None
    return Standing(
        judgement=kept.judgement,
        malicious=kept.malicious,
        suspicious=kept.suspicious,
        engines=kept.malicious + kept.suspicious + kept.harmless + kept.undetected,
        owner=kept.owner,
        country=kept.country,
        checked_at=kept.checked_at,
    )


def _sums(
    db: Session, addresses: list[Address], start: datetime
) -> dict[tuple[datetime, str], float]:
    """What was sent and received in each hour from ``start``, by the hour and the reading. ntopng's
    counters only rise, so an hour is the rise over it. A counter that fell has started again, and
    what it reads now is what it has sent since. The first reading of a counter has nothing before
    it to rise from, so the hour it is in is not counted."""
    labels = [str(address) for address in addresses]
    readings = (
        select(
            MetricSample.sampled_at.label("sampled"),
            MetricSeries.name.label("name"),
            MetricSample.value.label("value"),
            func.lag(MetricSample.value)
            .over(partition_by=MetricSample.series_id, order_by=MetricSample.sampled_at)
            .label("previous"),
        )
        .join(MetricSeries, MetricSeries.id == MetricSample.series_id)
        .where(
            MetricSeries.source == "ntopng",
            MetricSeries.name.in_((SENT, RECEIVED)),
            MetricSeries.labels["host"].as_string().in_(labels),
            # One sample before the first hour, so that the first hour has a rise to count.
            MetricSample.sampled_at >= start - timedelta(hours=1),
        )
        .subquery()
    )
    rise = case(
        (readings.c.value >= readings.c.previous, readings.c.value - readings.c.previous),
        else_=readings.c.value,
    )
    hour = func.date_trunc(literal_column("'hour'"), readings.c.sampled)
    rows = db.execute(
        select(hour, readings.c.name, func.sum(rise))
        .where(readings.c.sampled >= start, readings.c.previous.is_not(None))
        .group_by(hour, readings.c.name)
    ).all()
    return {(at, name): float(amount) for at, name, amount in rows}


def _block(hours: Sequence[Reading]) -> Reading:
    """What was sent and received in a block of hours: none where none of them measured it."""
    sent = [item.sent for item in hours if item.sent is not None]
    received = [item.received for item in hours if item.received is not None]
    return Reading(
        at=hours[0].at,
        sent=sum(sent) if sent else None,
        received=sum(received) if received else None,
    )


def _traffic(db: Session, addresses: list[Address], now: datetime) -> Traffic:
    """The asset's traffic over the last week: an hour for each, ending with the one we are in."""
    start = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=HOURS - 1)
    sums: Mapping[tuple[datetime, str], float] = _sums(db, addresses, start) if addresses else {}
    hours = tuple(
        Reading(
            at=at,
            sent=sums.get((at, SENT)),
            received=sums.get((at, RECEIVED)),
        )
        for at in (start + timedelta(hours=index) for index in range(HOURS))
    )
    days = tuple(
        _block(hours[index : index + HOURS_PER_DAY]) for index in range(0, HOURS, HOURS_PER_DAY)
    )
    return Traffic(measured=bool(sums), hours=hours, days=days)


def _incidents(db: Session, addresses: list[Address]) -> tuple[IncidentSeen, ...]:
    """The latest incidents one of its addresses is the subject of, or is in the signals of."""
    rows = db.scalars(
        select(Incident)
        .where(
            or_(
                Incident.subject.in_([str(address) for address in addresses]),
                Incident.addresses.overlap(addresses),
            )
        )
        .order_by(Incident.last_seen_at.desc(), Incident.id.desc())
        .limit(INCIDENTS_SHOWN)
    )
    return tuple(
        IncidentSeen(
            id=row.id,
            title=row.title,
            severity=row.severity,
            confidence=row.confidence,
            status=row.status,
            verdict=row.verdict,
            last_seen_at=row.last_seen_at,
            signal_count=row.signal_count,
            sources=tuple(row.sources),
        )
        for row in rows
    )


def _verdicts(db: Session, addresses: list[Address]) -> tuple[VerdictSeen, ...]:
    """The verdicts given about its addresses, the latest first. A verdict that names a destination
    is about the device's traffic to it, so it is listed too."""
    rows = db.scalars(
        select(VerdictRule)
        .where(VerdictRule.address.in_(addresses))
        .order_by(VerdictRule.created_at.desc(), VerdictRule.id.desc())
        .limit(VERDICTS_SHOWN)
    )
    return tuple(
        VerdictSeen(
            id=row.id,
            verdict=row.verdict,
            address=row.address,
            destination=str(row.destination) if row.destination is not None else None,
            source=row.source,
            signature=row.signature,
            note=row.note,
            created_at=row.created_at,
        )
        for row in rows
    )
