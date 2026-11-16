"""What was learned of what is normal, as the Baselines page and the assistant read it: for each
interface the usual traffic of each hour of the day, with how far it strays, and for each device
the places it usually talks to. The owner can correct what was learned: say a place is expected,
or forget it so that the next time a device goes there is new again."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from ipaddress import IPv4Address, IPv6Address, ip_network
from typing import Final

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import baselines
from app.baselines import destinations, traffic
from app.interfaces.scope import Resolver
from app.models import (
    Device,
    DeviceAddress,
    Event,
    KnownDestination,
    MetricSeries,
    TrafficBaseline,
)

Address = IPv4Address | IPv6Address

# How far back the deviations that are listed reach, and how many of each series are.
LOOK_BACK: Final = timedelta(days=30)
DEVIATIONS_SHOWN: Final = 5
# How many devices and how many places of one device are listed.
MAX_DEVICES: Final = 200
MAX_PLACES: Final = 200


@dataclass(frozen=True)
class Hour:
    """What is usual for an hour of the day (UTC): the median bytes in it, the spread that says
    how far is far, and how many hours that was learned from."""

    hour: int
    median: float
    spread: float
    samples: int


@dataclass(frozen=True)
class Deviation:
    """An hour that carried far more than is usual, as it was raised."""

    at: datetime
    summary: str
    observed: float
    usual: float
    severity: int


@dataclass(frozen=True)
class Series:
    """The usual traffic of one interface in one direction."""

    interface: str | None
    # What the owner calls the interface, if they have placed it.
    name: str | None
    direction: str
    hours: tuple[Hour, ...]
    learned_at: datetime | None
    deviations: tuple[Deviation, ...]

    @property
    def samples(self) -> int:
        return max((hour.samples for hour in self.hours), default=0)


@dataclass(frozen=True)
class Interfaces:
    series: tuple[Series, ...]
    # Whether any interface counter has been collected at all, so an empty page can say what is
    # missing: the counters, or the weeks it takes to learn from them.
    counted: bool


def _deviations(db: Session, now: datetime) -> dict[tuple[str | None, str], list[Deviation]]:
    """The traffic deviations of the last month, newest first, by interface and direction."""
    events = db.scalars(
        select(Event)
        .where(
            Event.source == baselines.SOURCE,
            Event.kind == baselines.KIND,
            Event.occurred_at >= now - LOOK_BACK,
            Event.raw["baseline"].as_string() == "traffic",
        )
        .order_by(Event.occurred_at.desc())
        .limit(500)
    )
    found: dict[tuple[str | None, str], list[Deviation]] = {}
    for event in events:
        raw = event.raw or {}
        key = (event.iface, str(raw.get("direction", "")))
        listed = found.setdefault(key, [])
        if len(listed) < DEVIATIONS_SHOWN:
            listed.append(
                Deviation(
                    at=event.occurred_at,
                    summary=event.summary,
                    observed=float(raw.get("observed_bytes", 0)),
                    usual=float(raw.get("usual_bytes", 0)),
                    severity=event.severity,
                )
            )
    return found


def interfaces(db: Session, now: datetime) -> Interfaces:
    """The usual traffic of every interface counter that has something learned, and whether any
    counter is collected at all."""
    series = db.scalars(
        select(MetricSeries)
        .where(MetricSeries.name.in_(traffic.DIRECTIONS))
        .order_by(MetricSeries.labels["interface"].as_string(), MetricSeries.name)
    ).all()
    rows = db.scalars(
        select(TrafficBaseline).where(
            TrafficBaseline.series_id.in_([item.id for item in series]),
            TrafficBaseline.bucket >= traffic.ANY_DAY,
        )
    ).all()
    by_series: dict[int, list[TrafficBaseline]] = {}
    for row in rows:
        by_series.setdefault(row.series_id, []).append(row)
    resolver = Resolver(db)
    deviations = _deviations(db, now)
    learned: list[Series] = []
    for item in series:
        hours = sorted(by_series.get(item.id, []), key=lambda row: row.bucket)
        if not hours:
            continue
        native = item.labels.get("interface")
        place = resolver.of(item.source, item.connection, native)
        direction = traffic.DIRECTIONS[item.name]
        learned.append(
            Series(
                interface=native,
                name=place.interface.name if place and place.interface else None,
                direction=direction,
                hours=tuple(
                    Hour(row.bucket - traffic.ANY_DAY, row.median, row.spread, row.samples)
                    for row in hours
                ),
                learned_at=max(row.updated_at for row in hours),
                deviations=tuple(deviations.get((native, direction), ())),
            )
        )
    return Interfaces(series=tuple(learned), counted=bool(series))


# ---------------------------------------------------------------------------------------------
# What each device talks to


@dataclass(frozen=True)
class Talker:
    """A device and how much is known of where it talks to."""

    address: Address
    name: str | None
    places: int
    expected: int
    hits: int
    learning_since: datetime
    last_seen_at: datetime
    # Whether it has been watched long enough, and talks to enough places, to be judged: until
    # then every new place is learned, not reported.
    judged: bool


@dataclass(frozen=True)
class Talkers:
    items: tuple[Talker, ...]
    total: int


def _names(db: Session, addresses: list[Address]) -> dict[Address, str]:
    if not addresses:
        return {}
    rows = db.execute(
        select(DeviceAddress.address, Device.hostname)
        .join(Device, Device.id == DeviceAddress.device_id)
        .where(DeviceAddress.address.in_(addresses), Device.hostname.is_not(None))
    )
    return {address: name for address, name in rows if name}


def talkers(db: Session, now: datetime) -> Talkers:
    """The devices that places are known for, the one with the most places first."""
    places = func.count()
    total = db.scalar(select(func.count(func.distinct(KnownDestination.client)))) or 0
    rows = db.execute(
        select(
            KnownDestination.client,
            places,
            func.count().filter(KnownDestination.expected.is_(True)),
            func.sum(KnownDestination.hits),
            func.min(KnownDestination.first_seen_at),
            func.max(KnownDestination.last_seen_at),
        )
        .group_by(KnownDestination.client)
        .order_by(places.desc(), KnownDestination.client)
        .limit(MAX_DEVICES)
    ).all()
    names = _names(db, [row[0] for row in rows])
    return Talkers(
        items=tuple(
            Talker(
                address=client,
                name=names.get(client),
                places=count,
                expected=expected,
                hits=int(hits or 0),
                learning_since=began,
                last_seen_at=last,
                judged=began <= now - destinations.WATCHED_FOR and count >= destinations.MIN_PLACES,
            )
            for client, count, expected, hits, began, last in rows
        ),
        total=total,
    )


def name_of(db: Session, client: Address) -> str | None:
    """What the owner's inventory calls the device with this address, if it is one."""
    return _names(db, [client]).get(client)


@dataclass(frozen=True)
class Place:
    """A place a device talks to: a network and a port (0 where there is none)."""

    network: str
    port: int
    first_seen_at: datetime
    last_seen_at: datetime
    hits: int
    expected: bool


def places(db: Session, client: Address, limit: int = MAX_PLACES) -> tuple[Place, ...]:
    """The places a device talks to, the expected ones first, then the most visited."""
    rows = db.scalars(
        select(KnownDestination)
        .where(KnownDestination.client == client)
        .order_by(
            KnownDestination.expected.desc(),
            KnownDestination.hits.desc(),
            KnownDestination.network,
            KnownDestination.port,
        )
        .limit(limit)
    )
    return tuple(
        Place(
            str(row.network), row.port, row.first_seen_at, row.last_seen_at, row.hits, row.expected
        )
        for row in rows
    )


class BadPlace(ValueError):
    """The place named is not one that can be kept: a network that is not a /24 (or a /64) or a
    port that is not one."""


def place_key(network: str, port: int) -> tuple[destinations.Network, int]:
    """The network and port as they are kept, or `BadPlace`. A network is written as its /24 (for
    IPv4) or /64 (for IPv6), the way it is learned."""
    try:
        parsed = ip_network(network, strict=False)
    except ValueError as error:
        raise BadPlace("That is not a network.") from error
    if parsed != destinations.network_of(parsed.network_address):
        wanted = 24 if parsed.version == 4 else 64
        raise BadPlace(f"Places are kept as a /{wanted}.")
    if not 0 <= port <= 65_535:
        raise BadPlace("A port is a number from 0 to 65535.")
    return parsed, port


def mark(
    db: Session,
    client: Address,
    network: destinations.Network,
    port: int,
    *,
    expected: bool,
    now: datetime,
) -> bool | None:
    """Says a place is expected, or no longer is. A place that was never learned is made, so what
    a device is yet to do is expected too. Returns whether it was made, or None where there is
    nothing to take the mark off."""
    row = db.get(KnownDestination, (client, network, port))
    if row is None:
        if not expected:
            return None
        db.add(
            KnownDestination(
                client=client,
                network=network,
                port=port,
                first_seen_at=now,
                last_seen_at=now,
                hits=0,
                expected=True,
            )
        )
        return True
    row.expected = expected
    return False


def forget(db: Session, client: Address, network: destinations.Network, port: int) -> bool:
    """Takes a place out of what is known of a device, so the next time it goes there is new
    again. Returns whether there was such a place."""
    row = db.get(KnownDestination, (client, network, port))
    if row is None:
        return False
    db.delete(row)
    return True
