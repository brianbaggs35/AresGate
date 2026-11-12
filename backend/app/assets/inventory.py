"""The assets on the network: every device the connected integrations list, as one picture.

Each integration lists what it can see in its own words. OPNsense's ARP table and DHCP leases and
ntopng's hosts all give a hardware (MAC) address, which is what makes them the same device. A
Wazuh agent gives a name and an address and no hardware address, so it is matched to a device
afterwards: by its address, which is the stronger sign, and otherwise by its name when exactly one
device has it. What matches nothing is an asset of its own. The match is worked out each time it is
asked for and never stored, so a device that gets a lease later is merged then, and every listing
says how it was matched.

A device on the Internet side of the network, which is the provider's and not the home's, is not
an asset: it is counted. The firewall's own addresses are always assets, whichever side they are on.

All of it is read into memory and worked on there: a home network has some hundreds of devices at
the most."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network, ip_network
from typing import Final, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assets import profile as profiles
from app.devices import ways
from app.incidents.filters import inside
from app.integrations import registry
from app.models import (
    Device,
    DeviceAddress,
    DeviceSource,
    HostListing,
    IntegrationConnection,
    Interface,
)

# A device that something with presence listed this recently is on the network now. The collectors
# read every minute, so this is a few missed reads of leeway.
ONLINE_WITHIN: Final = timedelta(minutes=10)
# One that was listed at all this recently is only "seen recently": a DHCP lease is listed until it
# runs out, which says the address was given and not that the device is there.
RECENT_WITHIN: Final = timedelta(hours=24)
# A device first listed this recently is new, unless it was one of the first to be listed.
NEW_WITHIN: Final = timedelta(days=7)
# Devices first listed within this long of the very first are the network as it was found, which is
# not news: without this every device is new on the day AresGate is set up.
STARTING_INVENTORY: Final = timedelta(days=1)
# An address is one the device has now if it was listed within this long of the newest one.
CURRENT_WITHIN: Final = timedelta(hours=1)
# Names too common to say that two machines are one.
GENERIC_NAMES: Final = frozenset({"localhost", "ubuntu", "debian", "raspberrypi", "kali"})

Status = Literal["online", "recent", "away"]
Kind = Literal["device", "host"]
MatchedBy = Literal["address", "hostname"]
Address = IPv4Address | IPv6Address


@dataclass(frozen=True)
class Listing:
    """One integration listing an asset, and how."""

    source: str
    via: str
    first_seen_at: datetime
    last_seen_at: datetime
    # Whether being listed this way means it is on the network now.
    presence: bool
    # For a machine with no hardware address that was matched to a device: how it was.
    matched_by: MatchedBy | None = None
    # For a machine, the integration's word for how it is doing.
    state: str | None = None


@dataclass(frozen=True)
class Asset:
    """A device, or a machine that no device matched, as the integrations together tell it."""

    # What a page links to: ``device-12`` or ``host-3``.
    key: str
    kind: Kind
    # Its host name, else its maker, else its hardware address, else its address.
    name: str
    hostname: str | None
    vendor: str | None
    mac: str | None
    # The hardware address was made up by the device, as a phone does on Wi-Fi to keep from being
    # followed from one network to the next.
    private_mac: bool
    # The addresses it has now, then the ones it had.
    addresses: tuple[Address, ...]
    current: int
    status: Status
    first_seen_at: datetime
    last_seen_at: datetime
    is_new: bool
    # Something says what it is: a name or a maker.
    identified: bool
    listings: tuple[Listing, ...]
    # The interfaces (by id) whose networks hold one of its current addresses.
    interfaces: tuple[int, ...]
    # On the Internet side of the network, which is not the home's: left out of the list.
    outside: bool = False
    # One of the firewall's own addresses: every path to or from the Internet crosses it.
    own: bool = False
    # What the owner said it is, and what its name and maker suggest it is where they do.
    profile: profiles.Profile | None = None
    suggested: str | None = None


@dataclass(frozen=True)
class Supplier:
    """An integration that can list devices, and whether it is connected to."""

    key: str
    name: str
    connected: bool
    # What it lists, as a page calls them.
    ways: tuple[str, ...]


@dataclass(frozen=True)
class Network:
    """An interface that has networks to tell which assets are on it."""

    id: int
    name: str
    # Whether it is the Internet: what is on it is not the home's.
    internet: bool = False


@dataclass(frozen=True)
class Inventory:
    assets: list[Asset]
    suppliers: list[Supplier]
    # The interfaces of the home that have networks; the Internet is not one of them.
    networks: list[Network]
    # When the first asset was first listed; none while there is none.
    watching_since: datetime | None
    # How many assets are on the Internet side and so left out of ``assets``.
    outside: int = 0


# The integrations that list devices, with the connections each needs and how it lists them.
SUPPLIERS: Final = (
    ("opnsense", ("api",), (ways.ARP, ways.DHCP)),
    ("ntopng", ("api",), (ways.HOSTS,)),
    ("wazuh", ("manager",), (ways.AGENT,)),
)


def name_of(source: str) -> str:
    """What an integration is called, or its key for one this version doesn't know."""
    known = registry.INTEGRATIONS.get(source)
    return known.name if known else source


def private(mac: str) -> bool:
    """Whether a hardware address is one the device made up (the "locally administered" bit of
    its first byte) and not the maker's own."""
    return bool(int(mac[:2], 16) & 2)


def _short(name: str | None) -> str | None:
    """A host name without its domain, in lowercase, to tell whether two are the same; none for
    one too common to say so."""
    short = (name or "").partition(".")[0].strip().lower()
    return None if not short or short in GENERIC_NAMES else short


def _suppliers(db: Session) -> list[Supplier]:
    connected = {
        (integration, connection)
        for integration, connection in db.execute(
            select(IntegrationConnection.integration, IntegrationConnection.connection)
        )
    }
    return [
        Supplier(
            key=key,
            name=name_of(key),
            connected=all((key, connection) in connected for connection in connections),
            ways=tuple(ways.WAYS[way].label for way in listed),
        )
        for key, connections, listed in SUPPLIERS
    ]


Blocks = list[IPv4Network | IPv6Network]


def _networks(db: Session) -> list[tuple[Network, Blocks]]:
    """The interfaces that have networks, with them: the others can't tell what is on them."""
    found: list[tuple[Network, Blocks]] = []
    for item in db.scalars(select(Interface).order_by(Interface.position, Interface.id)):
        blocks: Blocks = []
        for text in item.networks:
            try:
                blocks.append(ip_network(text, strict=False))
            except ValueError:
                # The Interfaces page only keeps networks, but one this can't read is no reason
                # for the list of devices not to load.
                continue
        if blocks:
            found.append((Network(item.id, item.name, item.role == "internet"), blocks))
    return found


def _covers(addresses: tuple[Address, ...], blocks: Blocks) -> bool:
    """Whether any of these addresses is in any of these networks."""
    return any(address in block for address in addresses for block in blocks)


def _on(addresses: tuple[Address, ...], networks: list[tuple[Network, Blocks]]) -> tuple[int, ...]:
    """The interfaces with a network that holds any of these addresses."""
    return tuple(network.id for network, blocks in networks if _covers(addresses, blocks))


def _on_internet(
    own: bool, addresses: tuple[Address, ...], networks: list[tuple[Network, Blocks]]
) -> bool:
    """Whether a device is on the Internet side, which is not the home's and so is left out of the
    assets. The firewall's own addresses are the owner's, whichever side they are on. Otherwise the
    owner's networks decide where they cover an address, and a network of the home wins over one of
    the Internet. Where none does, a public IPv4 address is on the Internet, unless another of the
    device's addresses is the home's. A link-local address is on whatever link it is on, so it
    says nothing of the side."""
    if own:
        return False
    covering = [network for network, blocks in networks if _covers(addresses, blocks)]
    if any(not network.internet for network in covering):
        return False
    if covering:
        return True
    routable = [address for address in addresses if not address.is_link_local]
    public = any(address.version == 4 and address.is_global for address in routable)
    return public and not any(inside(address) for address in routable)


def _listing(row: DeviceSource) -> Listing:
    known = ways.WAYS.get(row.via)
    return Listing(
        row.source, row.via, row.first_seen_at, row.last_seen_at, known.presence if known else False
    )


def _status(listings: list[Listing], last_seen_at: datetime, now: datetime) -> Status:
    if any(item.presence and now - item.last_seen_at <= ONLINE_WITHIN for item in listings):
        return "online"
    return "recent" if now - last_seen_at <= RECENT_WITHIN else "away"


def _match(
    host: HostListing, by_address: dict[Address, int], by_name: dict[str, set[int]]
) -> tuple[int, MatchedBy] | None:
    """The device a machine is, if one is: the one that has its address now or last had it, or
    else the only one that has its name."""
    if host.address is not None and host.address in by_address:
        return by_address[host.address], "address"
    short = _short(host.hostname)
    named = by_name.get(short, set[int]()) if short else set[int]()
    return (next(iter(named)), "hostname") if len(named) == 1 else None


def _host_listing(host: HostListing, matched_by: MatchedBy | None) -> Listing:
    return Listing(
        host.source,
        host.via,
        host.first_seen_at,
        host.last_seen_at,
        host.online,
        matched_by,
        host.state,
    )


def _new(first_seen_at: datetime, since: datetime, now: datetime) -> bool:
    return first_seen_at >= now - NEW_WITHIN and first_seen_at > since + STARTING_INVENTORY


@dataclass
class _Parts:
    """What the integrations said of the devices, gathered by device."""

    addresses: dict[int, list[DeviceAddress]] = field(
        default_factory=dict[int, list[DeviceAddress]]
    )
    sources: dict[int, list[DeviceSource]] = field(default_factory=dict[int, list[DeviceSource]])
    hosts: dict[int, list[tuple[HostListing, MatchedBy]]] = field(
        default_factory=dict[int, list[tuple[HostListing, MatchedBy]]]
    )


def _device(
    device: Device,
    parts: _Parts,
    networks: list[tuple[Network, Blocks]],
    since: datetime,
    now: datetime,
    said: dict[str, profiles.Profile],
) -> Asset:
    rows = sorted(
        parts.addresses.get(device.id, []),
        key=lambda row: (-row.last_seen_at.timestamp(), str(row.address)),
    )
    newest = rows[0].last_seen_at if rows else None
    current = tuple(
        row.address
        for row in rows
        if newest is not None and newest - row.last_seen_at <= CURRENT_WITHIN
    )
    older = tuple(row.address for row in rows[len(current) :])
    machines = parts.hosts.get(device.id, [])
    # What a machine listed with the same address adds, if the device was never seen at it.
    extra = tuple(
        dict.fromkeys(
            host.address
            for host, _ in machines
            if host.address is not None and host.address not in (*current, *older)
        )
    )
    sources = parts.sources.get(device.id, [])
    own = any(row.own for row in sources)
    listings = [_listing(row) for row in sources]
    listings += [_host_listing(host, matched_by) for host, matched_by in machines]
    last_seen_at = max([device.last_seen_at, *(item.last_seen_at for item in listings)])
    first_seen_at = min([device.first_seen_at, *(host.first_seen_at for host, _ in machines)])
    hostname = device.hostname or next(
        (host.hostname for host, _ in machines if host.hostname), None
    )
    return Asset(
        key=f"device-{device.id}",
        kind="device",
        name=hostname or device.vendor or device.mac,
        hostname=hostname,
        vendor=device.vendor,
        mac=device.mac,
        private_mac=private(device.mac),
        addresses=(*current, *older, *extra),
        current=len(current),
        status=_status(listings, last_seen_at, now),
        first_seen_at=first_seen_at,
        last_seen_at=last_seen_at,
        is_new=_new(first_seen_at, since, now),
        identified=bool(hostname or device.vendor),
        listings=tuple(sorted(listings, key=lambda item: (item.source, item.via))),
        interfaces=_on(current, networks),
        outside=_on_internet(own, current, networks),
        own=own,
        profile=said.get(f"device-{device.id}"),
        suggested=profiles.suggest(hostname, device.vendor),
    )


def _host(
    host: HostListing,
    networks: list[tuple[Network, Blocks]],
    since: datetime,
    now: datetime,
    said: dict[str, profiles.Profile],
) -> Asset:
    where = (host.address,) if host.address is not None else ()
    listing = _host_listing(host, None)
    return Asset(
        key=f"host-{host.id}",
        kind="host",
        name=host.hostname
        or (str(host.address) if host.address else f"{ways.WAYS[host.via].label} {host.key}"),
        hostname=host.hostname,
        vendor=None,
        mac=None,
        private_mac=False,
        addresses=where,
        current=len(where),
        status=_status([listing], host.last_seen_at, now),
        first_seen_at=host.first_seen_at,
        last_seen_at=host.last_seen_at,
        is_new=_new(host.first_seen_at, since, now),
        identified=True,
        listings=(listing,),
        interfaces=_on(where, networks),
        outside=_on_internet(False, where, networks),
        profile=said.get(f"host-{host.id}"),
        suggested=profiles.suggest(host.hostname, None),
    )


def load(db: Session, now: datetime) -> Inventory:
    """Every asset as of ``now``, with the integrations that could list one. Those on the Internet
    side are not in it: they are counted."""
    devices = list(db.scalars(select(Device).order_by(Device.id)))
    machines = list(db.scalars(select(HostListing).order_by(HostListing.id)))
    parts = _Parts()
    owner: dict[Address, tuple[datetime, int]] = {}
    for row in db.scalars(select(DeviceAddress).order_by(DeviceAddress.device_id)):
        parts.addresses.setdefault(row.device_id, []).append(row)
        # An address that passed from one device to another is the one that had it last.
        if row.address not in owner or (row.last_seen_at, row.device_id) > owner[row.address]:
            owner[row.address] = (row.last_seen_at, row.device_id)
    for row in db.scalars(select(DeviceSource)):
        parts.sources.setdefault(row.device_id, []).append(row)
    by_address = {address: device_id for address, (_, device_id) in owner.items()}
    by_name: dict[str, set[int]] = defaultdict(set)
    for device in devices:
        if short := _short(device.hostname):
            by_name[short].add(device.id)
    alone: list[HostListing] = []
    for host in machines:
        found = _match(host, by_address, by_name)
        if found is None:
            alone.append(host)
        else:
            parts.hosts.setdefault(found[0], []).append((host, found[1]))
    firsts = [item.first_seen_at for item in (*devices, *machines)]
    networks = _networks(db)
    since = min(firsts) if firsts else now
    said = profiles.load(db)
    found = [_device(device, parts, networks, since, now, said) for device in devices]
    found += [_host(host, networks, since, now, said) for host in alone]
    return Inventory(
        assets=[asset for asset in found if not asset.outside],
        suppliers=_suppliers(db),
        networks=[network for network, _ in networks if not network.internet],
        watching_since=min(firsts, default=None),
        outside=sum(asset.outside for asset in found),
    )
