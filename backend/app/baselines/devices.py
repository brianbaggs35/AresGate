"""Which devices are on the network, and when a new one appears.

The devices there are when this first looks are what is normal. After that a device that was not
on the network before is a deviation, but only once the network has had a few devices for a week:
on a new install every device is new, and saying so is no use to anyone."""

from datetime import datetime, timedelta
from typing import Final

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import baselines
from app.events.event import NewEvent, Severity
from app.models import Device, DeviceAddress, SystemInfo

# The network is established once it has had at least this many devices for this long.
WATCHED_FOR: Final = timedelta(days=7)
MIN_DEVICES: Final = 3
# A device is new only if it first appeared this recently: one the program lists with an older date
# was not new to the network when it was listed.
NEW_WITHIN: Final = timedelta(days=3)
CONFIDENCE: Final = 40
CURSOR_KEY: Final = "baselines.devices_cursor"


def _label(device: Device) -> str:
    """What to call a device: its name, else its maker, else its hardware address."""
    return device.hostname or (f"{device.vendor} device" if device.vendor else str(device.mac))


def run(db: Session, now: datetime) -> list[NewEvent]:
    """A deviation for each device that appeared since the last run. The first run only takes
    note of the devices there are."""
    cursor = db.get(SystemInfo, CURSOR_KEY)
    newest = db.scalar(select(func.max(Device.id))) or 0
    if cursor is None:
        db.add(SystemInfo(key=CURSOR_KEY, value=str(newest)))
        return []
    after = int(cursor.value)
    cursor.value = str(max(after, newest))
    established = (
        db.scalar(
            select(func.count())
            .select_from(Device)
            .where(Device.first_seen_at <= now - WATCHED_FOR)
        )
        or 0
    ) >= MIN_DEVICES
    if not established:
        return []
    events: list[NewEvent] = []
    for device in db.scalars(
        select(Device)
        .where(Device.id > after, Device.first_seen_at >= now - NEW_WITHIN)
        .order_by(Device.id)
    ):
        address = db.scalar(
            select(DeviceAddress.address)
            .where(DeviceAddress.device_id == device.id)
            .order_by(DeviceAddress.last_seen_at.desc())
            .limit(1)
        )
        events.append(
            NewEvent(
                source=baselines.SOURCE,
                connection=baselines.CONNECTION,
                kind=baselines.KIND,
                severity=Severity.LOW,
                occurred_at=now,
                identity=("device", device.id),
                summary=(
                    f"A device that has not been on the network before appeared: {_label(device)}."
                ),
                signature="A new device",
                src_address=str(address) if address is not None else None,
                raw={
                    "baseline": "device",
                    "confidence": CONFIDENCE,
                    "device_id": device.id,
                    "mac": str(device.mac),
                    "hostname": device.hostname,
                    "vendor": device.vendor,
                    "first_seen_at": device.first_seen_at.isoformat(),
                },
            )
        )
    return events
