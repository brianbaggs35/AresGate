"""Devices: every address that took part in a connection the integrations told AresGate of, the
home's own devices and the ones on the Internet side alike.

The Assets list is the owner's inventory, what the network says is on it. This is what it did: an
address is here because an event (a firewall block, an alert) names it as the source or the
destination of a connection, so a device that connected in from the Internet is in it, and so is a
server a camera called out to. Each is read over the last week, with what it did (connections to
it and from it, the ports they used, when), the incidents it is in and what threat intelligence has
kept of it. The count of connections is the count of events the integrations reported, which is
not every packet on the wire.

Nothing is asked of a service to build a page: a name, a standing or an identity is shown only if
it is already kept.
"""

from collections.abc import Iterable
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import Final, Literal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.assets import detail, inventory
from app.assets.detail import EventSeen, PortSeen, Standing
from app.assets.inventory import Asset
from app.intel import overrides, virustotal
from app.intel import store as intel_store
from app.models import AddressName, Event, Incident, IncidentFamily

Address = IPv4Address | IPv6Address
Scope = Literal["yours", "local", "outside"]
Sort = Literal["recent", "busiest", "address"]
Direction = Literal["incoming", "outgoing"]

# The week the connections are read over, the one the asset pages read too.
WEEK: Final = detail.WEEK
DAY: Final = detail.DAY
# How many addresses are read for each side of a connection, the most recently seen first: a
# network that is scanned all week has more than anyone looks through.
MOST: Final = 5000
# How many ports a device lists, and how many connections and incidents its page does.
PORTS_SHOWN: Final = 4
CONNECTIONS_SHOWN: Final = 50
INCIDENTS_SHOWN: Final = 10


@dataclass(frozen=True)
class Tally:
    """How many events an address was in as the destination (``incoming``, connections to it) and
    as the source (``outgoing``, connections it made), and when it was first and last in one."""

    incoming: int
    outgoing: int
    first_seen_at: datetime
    last_seen_at: datetime

    @property
    def events(self) -> int:
        return self.incoming + self.outgoing


@dataclass(frozen=True)
class Flagged:
    """The incidents an address is in: how many, and how serious the worst is."""

    count: int
    worst: int


@dataclass(frozen=True)
class Device:
    """An address and what it did over the week."""

    address: Address
    scope: Scope
    # The asset it is, when the Assets list holds it.
    asset: Asset | None
    # What its reverse lookup said, when one is kept.
    name: str | None
    tally: Tally
    ports: tuple[PortSeen, ...]
    protocols: tuple[str, ...]
    incidents: Flagged | None
    # What threat intelligence kept of it, for one on the Internet side.
    standing: Standing | None


@dataclass(frozen=True)
class Counts:
    """How many devices there are of each scope, among those a search finds."""

    everything: int
    yours: int
    local: int
    outside: int


@dataclass(frozen=True)
class Devices:
    """A page of the devices that match, and how many match in all."""

    items: tuple[Device, ...]
    total: int
    counts: Counts
    # Whether more addresses were seen than are read, so the list is the most recent of them.
    capped: bool


@dataclass(frozen=True)
class Connection:
    """What one device did with another, over one port: how often, and which way. ``outgoing`` is
    the device connecting to the peer; the port is the one at the far end of that, the service
    that was reached."""

    direction: Direction
    peer: Address | None
    port: int | None
    protocol: str | None
    events: int
    first_seen_at: datetime
    last_seen_at: datetime


@dataclass(frozen=True)
class Involved:
    """An incident an address is in, with the kind of threat and the chain it belongs to."""

    id: int
    title: str
    severity: int
    confidence: int
    status: str
    verdict: str | None
    last_seen_at: datetime
    signal_count: int
    sources: tuple[str, ...]
    family_id: int | None
    family_label: str | None
    chain_id: int | None


@dataclass(frozen=True)
class Detail:
    """Everything the page of one device shows."""

    device: Device
    # Events it was in over the last day and over the week.
    events_day: int
    events_week: int
    connections: tuple[Connection, ...]
    events: tuple[EventSeen, ...]
    incidents: tuple[Involved, ...]


def _scope(address: Address, assets: dict[Address, Asset]) -> Scope:
    if address in assets:
        return "yours"
    return "outside" if address.is_global else "local"


def _merged(
    before: Tally | None, incoming: bool, count: int, first: datetime, last: datetime
) -> Tally:
    """An address's tally with one more side's events added to what is already counted."""
    if before is None:
        return Tally(
            incoming=count if incoming else 0,
            outgoing=0 if incoming else count,
            first_seen_at=first,
            last_seen_at=last,
        )
    return Tally(
        incoming=before.incoming + (count if incoming else 0),
        outgoing=before.outgoing + (0 if incoming else count),
        first_seen_at=min(before.first_seen_at, first),
        last_seen_at=max(before.last_seen_at, last),
    )


def _tallies(db: Session, since: datetime) -> tuple[dict[Address, Tally], bool]:
    """Each address's events in the window, and whether either side was cut at ``MOST``."""
    found: dict[Address, Tally] = {}
    capped = False
    sides: tuple[tuple[InstrumentedAttribute[Address | None], bool], ...] = (
        (Event.dst_address, True),
        (Event.src_address, False),
    )
    for column, incoming in sides:
        rows = db.execute(
            select(column, func.count(), func.min(Event.occurred_at), func.max(Event.occurred_at))
            .where(column.is_not(None), Event.occurred_at >= since)
            .group_by(column)
            .order_by(func.max(Event.occurred_at).desc(), column)
            .limit(MOST)
        ).all()
        capped = capped or len(rows) >= MOST
        for address, count, first, last in rows:
            if address is None:  # pragma: no cover - the query leaves these out
                continue
            found[address] = _merged(found.get(address), incoming, count, first, last)
    return found, capped


def _flagged(db: Session, since: datetime) -> dict[Address, Flagged]:
    """The incidents active in the window by each address they name, as their subject or in their
    signals."""
    counts: dict[Address, list[int]] = {}
    for subject, severity, addresses in db.execute(
        select(Incident.subject, Incident.severity, Incident.addresses).where(
            Incident.last_seen_at >= since
        )
    ):
        named = set(addresses)
        with suppress(ValueError):  # A rule's name, which no address is.
            named.add(ip_address(subject))
        for address in named:
            counts.setdefault(address, []).append(severity)
    return {
        address: Flagged(count=len(severities), worst=max(severities))
        for address, severities in counts.items()
    }


def _names(db: Session, addresses: Iterable[Address] | None = None) -> dict[str, str]:
    """What the reverse lookups kept have called addresses, for these or for all of them."""
    query = select(AddressName.address, AddressName.name).where(AddressName.name.is_not(None))
    if addresses is not None:
        query = query.where(AddressName.address.in_([str(address) for address in addresses]))
    return {address: name for address, name in db.execute(query) if name is not None}


def _matches(
    words: list[str],
    address: Address,
    asset: Asset | None,
    name: str | None,
) -> bool:
    shown = [str(address), name]
    if asset is not None:
        shown += [asset.name, asset.hostname, asset.vendor, asset.mac]
    text = " ".join(part for part in shown if part).lower()
    return all(word in text for word in words)


def _ports(
    db: Session, addresses: list[Address], since: datetime
) -> tuple[dict[Address, tuple[PortSeen, ...]], dict[Address, tuple[str, ...]]]:
    """The ports of these devices' connections, the most often used first, and the protocols."""
    counts: dict[Address, dict[tuple[int | None, str | None], int]] = {}
    for column in (Event.dst_address, Event.src_address):
        for address, port, protocol, count in db.execute(
            select(column, Event.dst_port, Event.protocol, func.count())
            .where(column.in_(addresses), Event.occurred_at >= since)
            .group_by(column, Event.dst_port, Event.protocol)
        ):
            if address is None:  # pragma: no cover - the query leaves these out
                continue
            kept = counts.setdefault(address, {})
            kept[(port, protocol)] = kept.get((port, protocol), 0) + count
    ports: dict[Address, tuple[PortSeen, ...]] = {}
    protocols: dict[Address, tuple[str, ...]] = {}
    for address, kept in counts.items():
        by_port: dict[tuple[int, str | None], int] = {}
        for (port, protocol), count in kept.items():
            if port is not None:
                by_port[(port, protocol)] = count
        ranked = sorted(by_port.items(), key=lambda item: (-item[1], item[0][0]))
        ports[address] = tuple(
            PortSeen(port=port, protocol=protocol, events=count)
            for (port, protocol), count in ranked[:PORTS_SHOWN]
        )
        protocols[address] = tuple(sorted({protocol for _, protocol in kept if protocol}))
    return ports, protocols


def _standings(db: Session, addresses: list[Address]) -> dict[Address, Standing]:
    """What threat intelligence has kept of the addresses on the Internet side among these."""
    outside = [address for address in addresses if address.is_global]
    kept = intel_store.answers_for(db, virustotal.PROVIDER, outside)
    rulings = overrides.for_addresses(db, outside)
    standings: dict[Address, Standing] = {}
    for address in outside:
        standing = detail.standing_of(kept.get(address), rulings.get(str(address)))
        if standing is not None:
            standings[address] = standing
    return standings


def _devices(
    db: Session,
    rows: list[tuple[Address, Tally]],
    assets: dict[Address, Asset],
    flagged: dict[Address, Flagged],
    since: datetime,
) -> tuple[Device, ...]:
    """The devices for these addresses, with what is read for each of them."""
    addresses = [address for address, _ in rows]
    ports, protocols = _ports(db, addresses, since) if addresses else ({}, {})
    names = _names(db, addresses) if addresses else {}
    standings = _standings(db, addresses)
    return tuple(
        Device(
            address=address,
            scope=_scope(address, assets),
            asset=assets.get(address),
            name=names.get(str(address)),
            tally=tally,
            ports=ports.get(address, ()),
            protocols=protocols.get(address, ()),
            incidents=flagged.get(address),
            standing=standings.get(address),
        )
        for address, tally in rows
    )


def _key(sort: Sort, address: Address, tally: Tally) -> tuple[float, ...]:
    by_address = (address.version, int(address))
    if sort == "busiest":
        return (-tally.events, -tally.last_seen_at.timestamp(), *by_address)
    if sort == "address":
        return (0, 0, *by_address)
    return (-tally.last_seen_at.timestamp(), -tally.events, *by_address)


def search(
    db: Session,
    now: datetime,
    *,
    text: str = "",
    scope: Scope | None = None,
    direction: Direction | None = None,
    flagged_only: bool = False,
    sort: Sort = "recent",
    limit: int = 50,
    offset: int = 0,
) -> Devices:
    """The devices that match, in the order asked for."""
    since = now - WEEK
    tallies, capped = _tallies(db, since)
    assets = {
        address: asset for asset in inventory.load(db, now).assets for address in asset.addresses
    }
    flags = _flagged(db, since)
    words = text.lower().split()
    names = _names(db) if words else {}
    found = [
        (address, tally)
        for address, tally in tallies.items()
        if not words or _matches(words, address, assets.get(address), names.get(str(address)))
    ]
    scopes = [_scope(address, assets) for address, _ in found]
    counts = Counts(
        everything=len(found),
        yours=scopes.count("yours"),
        local=scopes.count("local"),
        outside=scopes.count("outside"),
    )
    kept = [
        (address, tally)
        for (address, tally), where in zip(found, scopes, strict=True)
        if (scope is None or where == scope)
        and (direction != "incoming" or tally.incoming)
        and (direction != "outgoing" or tally.outgoing)
        and (not flagged_only or address in flags)
    ]
    kept.sort(key=lambda row: _key(sort, *row))
    page = kept[offset : offset + limit]
    return Devices(
        items=_devices(db, page, assets, flags, since),
        total=len(kept),
        counts=counts,
        capped=capped,
    )


def _connections(db: Session, address: Address, since: datetime) -> tuple[Connection, ...]:
    """What the device did with others, a row for each peer and port, the most often first."""
    found: list[Connection] = []
    sides: tuple[
        tuple[
            Direction, InstrumentedAttribute[Address | None], InstrumentedAttribute[Address | None]
        ],
        ...,
    ] = (
        ("outgoing", Event.src_address, Event.dst_address),
        ("incoming", Event.dst_address, Event.src_address),
    )
    for direction, mine, theirs in sides:
        rows = db.execute(
            select(
                theirs,
                Event.dst_port,
                Event.protocol,
                func.count(),
                func.min(Event.occurred_at),
                func.max(Event.occurred_at),
            )
            .where(mine == address, Event.occurred_at >= since)
            .group_by(theirs, Event.dst_port, Event.protocol)
            .order_by(func.count().desc(), func.max(Event.occurred_at).desc())
            .limit(CONNECTIONS_SHOWN)
        ).all()
        found += [
            Connection(
                direction=direction,
                peer=peer,
                port=port,
                protocol=protocol,
                events=count,
                first_seen_at=first,
                last_seen_at=last,
            )
            for peer, port, protocol, count, first, last in rows
        ]
    found.sort(key=lambda item: (-item.events, -item.last_seen_at.timestamp()))
    return tuple(found[:CONNECTIONS_SHOWN])


def _incidents(db: Session, address: Address) -> tuple[Involved, ...]:
    """The latest incidents the address is the subject of, or is in the signals of."""
    rows = db.execute(
        select(Incident, IncidentFamily.label)
        .outerjoin(IncidentFamily, IncidentFamily.id == Incident.family_id)
        .where(or_(Incident.subject == str(address), Incident.addresses.overlap([address])))
        .order_by(Incident.last_seen_at.desc(), Incident.id.desc())
        .limit(INCIDENTS_SHOWN)
    ).all()
    return tuple(
        Involved(
            id=row.id,
            title=row.title,
            severity=row.severity,
            confidence=row.confidence,
            status=row.status,
            verdict=row.verdict,
            last_seen_at=row.last_seen_at,
            signal_count=row.signal_count,
            sources=tuple(row.sources),
            family_id=row.family_id,
            family_label=label,
            chain_id=row.chain_id,
        )
        for row, label in rows
    )


def load(db: Session, address: Address, now: datetime) -> Detail | None:
    """The page of one device as of ``now``, or none when nothing is known of the address: it is in
    no event of the week, no incident, and not an asset."""
    since = now - WEEK
    assets = {known: asset for asset in inventory.load(db, now).assets for known in asset.addresses}
    seen = db.execute(
        select(
            func.count().filter(Event.dst_address == address),
            func.count().filter(Event.src_address == address),
            func.min(Event.occurred_at),
            func.max(Event.occurred_at),
        ).where(
            or_(Event.src_address == address, Event.dst_address == address),
            Event.occurred_at >= since,
        )
    ).one()
    incidents = _incidents(db, address)
    asset = assets.get(address)
    if not seen[0] + seen[1] and not incidents and asset is None:
        return None
    if seen[0] + seen[1]:
        tally = Tally(
            incoming=seen[0], outgoing=seen[1], first_seen_at=seen[2], last_seen_at=seen[3]
        )
    else:
        # Known from elsewhere, with nothing in the week: it was last seen when the asset was, or
        # the incident was.
        last = asset.last_seen_at if asset is not None else incidents[0].last_seen_at
        tally = Tally(incoming=0, outgoing=0, first_seen_at=last, last_seen_at=last)
    [device] = _devices(db, [(address, tally)], assets, _flagged(db, since), since)
    events, events_day, events_week = detail.events_of(db, [address], now)
    return Detail(
        device=device,
        events_day=events_day,
        events_week=events_week,
        connections=_connections(db, address, since),
        events=events,
        incidents=incidents,
    )
