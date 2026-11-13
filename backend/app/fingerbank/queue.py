"""Which device is asked about next, and whether a request may go now.

Fingerbank's free key allows 600 requests an hour, so lookups are counted over the last hour and
stop at ``HOURLY``, which leaves the rest for the connection check and for tests made by hand. The
count is the devices asked about in the last hour, which is exact because a device is never asked
twice within it. Lookups are also ``SPACING`` apart, so a network full of new devices doesn't spend
its hour in the first minute.

The owner's own devices come before any other. Among them a device that has never been asked about
comes first, the newest on the network first, since a new device is the one worth knowing about.
Devices in incidents and threats follow, if the owner has allowed them, and only then do the
answers that have gone stale get asked for again. A device that made up its own hardware address is
never asked about: it is kept as ``private`` and the address says nothing of what it is.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from ipaddress import IPv4Address, IPv6Address
from typing import Final, cast

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.assets import inventory
from app.fingerbank.lookup import PROVIDER
from app.models import Device, DeviceAddress, DeviceIdentity, Incident

# Left of the 600 an hour for the connection check, which asks about no real device every few
# minutes, and for tests made by hand.
HOURLY: Final = 550
HOUR: Final = timedelta(hours=1)
SPACING: Final = timedelta(seconds=10)
# How long what Fingerbank said stays fresh. Its database grows, so a device it couldn't place may
# be placed later; a device it did place is rarely misplaced, so that is looked at less often.
IDENTIFIED_FRESH: Final = timedelta(days=30)
UNKNOWN_FRESH: Final = timedelta(days=7)
# Incidents seen this recently are worth identifying the devices of.
RECENT: Final = timedelta(days=7)
# How many incidents are looked through, most recent first.
INCIDENTS: Final = 200


@dataclass(frozen=True)
class Wanted:
    """A device to ask about, and why."""

    device_id: int
    mac: str
    reason: str


def may_ask(db: Session, now: datetime) -> bool:
    """Whether a request may go now: fewer than ``HOURLY`` in the last hour, and the last one at
    least ``SPACING`` ago."""
    asked, latest = db.execute(
        select(func.count(), func.max(DeviceIdentity.checked_at)).where(
            DeviceIdentity.source == PROVIDER,
            DeviceIdentity.state != "private",
            DeviceIdentity.checked_at >= now - HOUR,
        )
    ).one()
    last = cast("datetime | None", latest)
    return asked < HOURLY and (last is None or now - last >= SPACING)


def _stale(state: str | None, checked_at: datetime | None, now: datetime) -> bool:
    """Whether a device has to be asked about: it never was, or the answer has gone stale."""
    if state is None or checked_at is None:
        return True
    if state == "private":
        return False
    return now - checked_at >= (IDENTIFIED_FRESH if state == "identified" else UNKNOWN_FRESH)


def settle_private(db: Session, now: datetime) -> None:
    """Keeps every device that made up its own hardware address as one nobody is asked about. The
    caller commits."""
    rows = db.execute(
        select(Device.id, Device.mac)
        .outerjoin(DeviceIdentity, DeviceIdentity.device_id == Device.id)
        .where(DeviceIdentity.device_id.is_(None))
    ).all()
    db.add_all(
        DeviceIdentity(
            device_id=device_id,
            source=PROVIDER,
            state="private",
            reason="asset",
            checked_at=now,
        )
        for device_id, mac in rows
        if inventory.private(mac)
    )


def _incident_addresses(db: Session, now: datetime) -> set[IPv4Address | IPv6Address]:
    groups = db.scalars(
        select(Incident.addresses)
        .where(Incident.last_seen_at >= now - RECENT)
        .order_by(Incident.last_seen_at.desc())
        .limit(INCIDENTS)
    )
    return {address for group in groups for address in group}


def next_wanted(db: Session, now: datetime, *, incidents: bool) -> Wanted | None:
    """The device to ask about next, or None if there is none. Devices that made up their own
    hardware address are set aside first (the caller commits)."""
    settle_private(db, now)
    db.flush()
    rows = db.execute(
        select(
            Device.id,
            Device.mac,
            Device.first_seen_at,
            DeviceIdentity.state,
            DeviceIdentity.checked_at,
        ).outerjoin(DeviceIdentity, DeviceIdentity.device_id == Device.id)
    ).all()
    due = [row for row in rows if _stale(row.state, row.checked_at, now)]
    if not due:
        return None
    assets = {asset.key: asset for asset in inventory.load(db, now).assets}
    outside = [row for row in due if f"device-{row.id}" not in assets]
    involved: set[int] = set()
    if incidents and outside:
        involved = _involved(db, [row.id for row in outside], now)
    ranked = [
        found
        for row in due
        if (
            found := _rank(
                Wanted(row.id, row.mac, "asset" if f"device-{row.id}" in assets else "incident"),
                row.state is None,
                row.first_seen_at,
                assets.get(f"device-{row.id}"),
                row.id in involved,
            )
        )
        is not None
    ]
    return min(ranked, key=lambda found: found[0])[1] if ranked else None


def _rank(
    wanted: Wanted,
    fresh: bool,
    first_seen_at: datetime,
    asset: inventory.Asset | None,
    involved: bool,
) -> tuple[tuple[int, int, float], Wanted] | None:
    """Where a device that is due goes in the queue, or None if it is not worth asking about: one
    that is neither on the Assets list nor in a recent incident."""
    if asset is None and not involved:
        return None
    tier = (0 if fresh else 2) + (0 if asset is not None else 1)
    # Never asked about comes first, new devices first, and then the newest on the network.
    new = asset is not None and asset.is_new
    return (tier, 0 if new else 1, -first_seen_at.timestamp()), wanted


def _involved(db: Session, device_ids: list[int], now: datetime) -> set[int]:
    """Which of these devices have an address that a recent incident names."""
    named = _incident_addresses(db, now)
    if not named:
        return set()
    found = db.scalars(
        select(DeviceAddress.device_id)
        .where(DeviceAddress.device_id.in_(device_ids), DeviceAddress.address.in_(named))
        .distinct()
    )
    return set(found)
