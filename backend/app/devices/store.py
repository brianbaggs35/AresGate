"""Storing devices: what collectors call with the devices they saw."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from ipaddress import IPv4Address, IPv6Address
from typing import Any

from sqlalchemy import delete, or_
from sqlalchemy.dialects.postgresql import Insert, insert
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app.devices import ways
from app.devices.sighting import NewHost, NewSighting
from app.models import Device, DeviceAddress, DeviceSource, HostListing


@dataclass
class _Seen:
    """What the sightings of one device add up to."""

    first: datetime
    last: datetime
    hostname: str | None = None
    vendor: str | None = None
    own: bool = False
    addresses: dict[IPv4Address | IPv6Address, tuple[datetime, datetime]] = field(
        default_factory=dict[IPv4Address | IPv6Address, tuple[datetime, datetime]]
    )


def record(
    db: Session, sightings: Sequence[NewSighting], now: datetime, *, source: str, via: str
) -> int:
    """Remembers the devices that were listed, and returns how many different ones there were.
    A device is told apart by its MAC address: one not seen before is added, and one that was is
    updated with when it was seen, its addresses, and a name or maker if the sighting has one,
    which replaces the one kept. ``source`` is the integration that listed them and ``via`` how
    (a key of ``app.devices.ways``), which are kept with the time of the listing. A time ahead of
    ``now`` is taken as ``now``. The caller commits."""
    ways.check(via)
    seen = _sum_up(sightings, now)
    if not seen:
        return 0
    devices = _upsert_devices(db, seen)
    addresses = [
        {
            "device_id": devices[mac],
            "address": address,
            "first_seen_at": first,
            "last_seen_at": last,
        }
        for mac, found in seen.items()
        for address, (first, last) in found.addresses.items()
    ]
    if addresses:
        new = insert(DeviceAddress)
        db.execute(
            new.on_conflict_do_update(index_elements=["device_id", "address"], set_=_widen(new)),
            addresses,
        )
    listings = insert(DeviceSource)
    db.execute(
        listings.on_conflict_do_update(
            index_elements=["device_id", "source", "via"],
            # Once the program has listed a device as its own, it stays so.
            set_={**_widen(listings), "own": or_(DeviceSource.own, listings.excluded.own)},
        ),
        [
            {
                "device_id": devices[mac],
                "source": source,
                "via": via,
                "first_seen_at": found.first,
                "last_seen_at": found.last,
                "own": found.own,
            }
            for mac, found in seen.items()
        ],
    )
    return len(seen)


def record_hosts(
    db: Session,
    hosts: Sequence[NewHost],
    now: datetime,
    *,
    source: str,
    connection: str,
    via: str,
    complete: bool,
) -> int:
    """Remembers the machines an integration listed that have no hardware address, and returns
    how many. One listed before is updated, and its first sighting kept. When ``complete`` says
    the list is the whole of what the connection has, the ones it no longer lists are forgotten,
    since an agent that was removed is not an asset any more. A time ahead of ``now`` is taken as
    ``now``. The caller commits."""
    ways.check(via)
    found = {host.key: host for host in hosts}
    if found:
        new = insert(HostListing)
        db.execute(
            new.on_conflict_do_update(
                index_elements=["source", "connection", "key"],
                set_={
                    "via": new.excluded.via,
                    "hostname": func.coalesce(new.excluded.hostname, HostListing.hostname),
                    "address": func.coalesce(new.excluded.address, HostListing.address),
                    "state": new.excluded.state,
                    "online": new.excluded.online,
                    **_widen(new),
                },
            ),
            [
                {
                    "source": source,
                    "connection": connection,
                    "via": via,
                    "key": host.key,
                    "hostname": host.hostname,
                    "address": host.address,
                    "state": host.state,
                    "online": host.online,
                    "first_seen_at": min(host.seen_at, now),
                    "last_seen_at": min(host.seen_at, now),
                }
                for host in found.values()
            ],
        )
    if complete:
        db.execute(
            delete(HostListing).where(
                HostListing.source == source,
                HostListing.connection == connection,
                HostListing.key.not_in(list(found)),
            )
        )
    return len(found)


def _sum_up(sightings: Sequence[NewSighting], now: datetime) -> dict[str, _Seen]:
    """The sightings gathered by device, in the order they came: a later name wins."""
    seen: dict[str, _Seen] = {}
    for sighting in sightings:
        at = min(sighting.seen_at, now)
        found = seen.setdefault(sighting.mac, _Seen(first=at, last=at))
        found.first, found.last = min(found.first, at), max(found.last, at)
        found.hostname = sighting.hostname or found.hostname
        found.vendor = sighting.vendor or found.vendor
        found.own = found.own or sighting.own
        if sighting.address is not None:
            first, last = found.addresses.get(sighting.address, (at, at))
            found.addresses[sighting.address] = (min(first, at), max(last, at))
    return seen


def _upsert_devices(db: Session, seen: dict[str, _Seen]) -> dict[str, int]:
    """Adds the devices that are new and updates the others, and returns each one's id."""
    new = insert(Device)
    statement = new.on_conflict_do_update(
        index_elements=["mac"],
        set_={
            # A sighting that has no name leaves the one that is kept.
            "hostname": func.coalesce(new.excluded.hostname, Device.hostname),
            "vendor": func.coalesce(new.excluded.vendor, Device.vendor),
            **_widen(new),
        },
    ).returning(Device.id, Device.mac)
    rows: list[dict[str, Any]] = [
        {
            "mac": mac,
            "hostname": found.hostname,
            "vendor": found.vendor,
            "first_seen_at": found.first,
            "last_seen_at": found.last,
        }
        for mac, found in seen.items()
    ]
    return {mac: device_id for device_id, mac in db.execute(statement, rows).all()}


def _widen(statement: Insert) -> dict[str, Any]:
    """Moves the time a row was first seen back and the time it was last seen forward, to take
    in the sighting, whatever order sightings are read in."""
    table = statement.table
    return {
        "first_seen_at": func.least(table.c.first_seen_at, statement.excluded.first_seen_at),
        "last_seen_at": func.greatest(table.c.last_seen_at, statement.excluded.last_seen_at),
    }
