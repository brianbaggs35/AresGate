"""What each interface has been doing: how fast data went through it, how many alerts came in on
it and how many devices live on its networks. The numbers are worked out when asked, from the
data as its sources named it and the feeds as they are placed now, so moving a feed to another
interface moves what it measured as well."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final

from sqlalchemy import func, literal, or_, select
from sqlalchemy.dialects.postgresql import CIDR
from sqlalchemy.orm import Session

from app import dashboard
from app.interfaces.scope import Resolver
from app.models import DeviceAddress, Event, Interface, InterfaceFeed

# The programs whose byte counters speed is worked out from, best first. The firewall counts
# every byte that crosses it; ntopng counts what its capture sees, which is less certain. Only
# one is used for an interface, because both measure the same traffic and adding them would
# count it twice.
TRAFFIC_SOURCES: Final = ("opnsense", "ntopng")


@dataclass(frozen=True)
class Speed:
    """How fast data went through an interface, in bits a second for each bucket, and which
    program measured it. None where there is no telling."""

    source: str
    received: list[float | None]
    sent: list[float | None]


@dataclass(frozen=True)
class Stats:
    """What one interface has been doing in a window."""

    interface_id: int
    speed: Speed | None
    # Alerts that came in on it in the window and in the one before.
    alerts: int
    alerts_previous: int
    # Devices with an address on its networks; None when it has no networks to look in.
    devices: int | None
    # When its feeds last reported.
    last_seen_at: datetime | None


@dataclass(frozen=True)
class Overview:
    window: dashboard.Window
    # When each bucket of the speeds starts.
    times: list[datetime]
    stats: list[Stats] = field(default_factory=list[Stats])


def added(first: list[float | None], second: list[float | None]) -> list[float | None]:
    """Two lists of speeds added bucket by bucket; a bucket is unknown only if both are."""
    return [
        None if left is None and right is None else (left or 0.0) + (right or 0.0)
        for left, right in zip(first, second, strict=True)
    ]


def _speeds(db: Session, win: dashboard.Window, feeds: list[InterfaceFeed]) -> Speed | None:
    """The speed of the interface these feeds are placed on, from the first program in
    ``TRAFFIC_SOURCES`` that measured any of the ports they name."""
    ports: dict[str, set[str]] = defaultdict(set)
    for feed in feeds:
        if feed.native_name:
            ports[feed.integration].add(feed.native_name)
    for source in TRAFFIC_SOURCES:
        if source not in ports:
            continue
        measured = [
            item for item in dashboard.traffic(db, win, source) if item.interface in ports[source]
        ]
        if not measured:
            continue
        received = measured[0].received
        sent = measured[0].sent
        for item in measured[1:]:
            received = added(received, item.received)
            sent = added(sent, item.sent)
        return Speed(source, received, sent)
    return None


def _alerts(db: Session, resolver: Resolver, start: datetime, end: datetime) -> dict[int, int]:
    """How many alerts came in on each interface in a stretch of time. An alert from a program
    that names no port belongs to the interface its whole connection was placed on."""
    rows = db.execute(
        select(Event.source, Event.connection, Event.iface, func.count())
        .where(dashboard.IS_ALERT, Event.occurred_at >= start, Event.occurred_at < end)
        .group_by(Event.source, Event.connection, Event.iface)
    ).all()
    counts: dict[int, int] = defaultdict(int)
    for source, connection, port, count in rows:
        place = resolver.of(source, connection, port)
        if place is not None and place.interface is not None:
            counts[place.interface.id] += count
    return counts


def _devices(db: Session, networks: list[str]) -> int:
    """How many devices have an address in any of these networks."""
    inside = [DeviceAddress.address.op("<<=")(literal(block, CIDR())) for block in networks]
    return (
        db.scalar(select(func.count(func.distinct(DeviceAddress.device_id))).where(or_(*inside)))
        or 0
    )


def overview(db: Session, win: dashboard.Window) -> Overview:
    interfaces = list(db.scalars(select(Interface).order_by(Interface.position, Interface.id)))
    placed: dict[int, list[InterfaceFeed]] = defaultdict(list)
    for feed in db.scalars(select(InterfaceFeed)):
        if feed.interface_id is not None:
            placed[feed.interface_id].append(feed)
    resolver = Resolver(db)
    now = _alerts(db, resolver, win.start, win.end)
    before = _alerts(db, resolver, win.previous_start, win.start)
    stats: list[Stats] = []
    for item in interfaces:
        feeds = placed.get(item.id, [])
        networks = [str(block) for block in item.networks]
        stats.append(
            Stats(
                interface_id=item.id,
                speed=_speeds(db, win, feeds),
                alerts=now.get(item.id, 0),
                alerts_previous=before.get(item.id, 0),
                devices=_devices(db, networks) if networks else None,
                last_seen_at=max((feed.last_seen_at for feed in feeds), default=None),
            )
        )
    return Overview(win, win.buckets(win.traffic_bucket), stats)
