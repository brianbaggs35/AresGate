from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address, IPv6Address

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.devices.sighting import NewSighting
from app.devices.store import record
from app.models import Device, DeviceAddress

NOW = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
LAPTOP = "00:11:22:0a:0b:0c"
PHONE = "ac:de:48:00:00:02"


def seen(mac: str = LAPTOP, at: datetime = NOW, **changes: str | None) -> NewSighting:
    sighting = NewSighting.of(mac, at, **changes)
    assert sighting is not None
    return sighting


def devices(session: Session) -> dict[str, Device]:
    session.expire_all()
    return {device.mac: device for device in session.scalars(select(Device))}


def addresses(session: Session) -> dict[tuple[str, str], DeviceAddress]:
    """The addresses, by the hardware address of the device and the address."""
    session.expire_all()
    rows = session.execute(
        select(Device.mac, DeviceAddress).join(DeviceAddress, DeviceAddress.device_id == Device.id)
    )
    return {(mac, str(row.address)): row for mac, row in rows}


def test_a_device_is_stored_with_what_was_seen_of_it(session: Session) -> None:
    found = seen(address="192.168.1.20", hostname="laptop", vendor="Example Devices Inc.")

    assert record(session, [found], NOW) == 1
    session.commit()

    (device,) = devices(session).values()
    assert (device.mac, device.hostname, device.vendor) == (
        LAPTOP,
        "laptop",
        "Example Devices Inc.",
    )
    assert (device.first_seen_at, device.last_seen_at) == (NOW, NOW)
    (address,) = addresses(session).values()
    assert address.address == IPv4Address("192.168.1.20")
    assert (address.first_seen_at, address.last_seen_at) == (NOW, NOW)


def test_nothing_seen_stores_nothing(session: Session) -> None:
    assert record(session, [], NOW) == 0
    assert devices(session) == {}
    assert addresses(session) == {}


def test_a_device_with_nothing_but_its_hardware_address_is_stored(session: Session) -> None:
    assert record(session, [seen()], NOW) == 1

    (device,) = devices(session).values()
    assert (device.hostname, device.vendor) == (None, None)
    assert addresses(session) == {}


def test_the_number_is_of_different_devices(session: Session) -> None:
    several = [
        seen(LAPTOP, address="192.168.1.20"),
        seen(LAPTOP, address="fd00::20"),
        seen(PHONE, address="192.168.1.21"),
    ]

    assert record(session, several, NOW) == 2
    assert record(session, several, NOW) == 2
    assert set(devices(session)) == {LAPTOP, PHONE}


def test_a_device_seen_again_is_the_same_device_seen_later(session: Session) -> None:
    record(session, [seen(address="192.168.1.20")], NOW)
    later = NOW + timedelta(minutes=5)

    record(session, [seen(at=later, address="192.168.1.20")], later)
    session.commit()

    (device,) = devices(session).values()
    assert (device.first_seen_at, device.last_seen_at) == (NOW, later)
    (address,) = addresses(session).values()
    assert (address.first_seen_at, address.last_seen_at) == (NOW, later)


def test_a_sighting_older_than_the_last_does_not_move_the_last_back(session: Session) -> None:
    later = NOW + timedelta(minutes=5)
    record(session, [seen(at=later, address="192.168.1.20")], later)

    record(session, [seen(at=NOW, address="192.168.1.20")], later)

    (device,) = devices(session).values()
    assert (device.first_seen_at, device.last_seen_at) == (NOW, later)
    (address,) = addresses(session).values()
    assert (address.first_seen_at, address.last_seen_at) == (NOW, later)


def test_sightings_of_one_device_in_one_go_are_taken_together(session: Session) -> None:
    later = NOW + timedelta(minutes=1)
    record(
        session,
        [
            seen(at=later, address="192.168.1.20"),
            seen(at=NOW, address="192.168.1.20", hostname="laptop"),
            seen(at=later, address="192.168.1.30"),
        ],
        later,
    )

    (device,) = devices(session).values()
    assert (device.first_seen_at, device.last_seen_at, device.hostname) == (NOW, later, "laptop")
    assert {
        key: (row.first_seen_at, row.last_seen_at) for key, row in addresses(session).items()
    } == {
        (LAPTOP, "192.168.1.20"): (NOW, later),
        (LAPTOP, "192.168.1.30"): (later, later),
    }


def test_a_device_that_changes_its_address_keeps_the_old_one(session: Session) -> None:
    record(session, [seen(address="192.168.1.20")], NOW)
    later = NOW + timedelta(hours=1)

    record(session, [seen(at=later, address="192.168.1.50")], later)

    assert {key: row.last_seen_at for key, row in addresses(session).items()} == {
        (LAPTOP, "192.168.1.20"): NOW,
        (LAPTOP, "192.168.1.50"): later,
    }
    assert len(devices(session)) == 1


def test_a_device_can_have_an_ipv4_and_an_ipv6_address(session: Session) -> None:
    record(session, [seen(address="192.168.1.20"), seen(address="fd00::20")], NOW)

    assert {row.address for row in addresses(session).values()} == {
        IPv4Address("192.168.1.20"),
        IPv6Address("fd00::20"),
    }


def test_an_address_that_passes_to_another_device_is_in_the_rows_of_both(
    session: Session,
) -> None:
    record(session, [seen(LAPTOP, address="192.168.1.20")], NOW)
    later = NOW + timedelta(hours=1)

    record(session, [seen(PHONE, at=later, address="192.168.1.20")], later)

    assert {key: row.last_seen_at for key, row in addresses(session).items()} == {
        (LAPTOP, "192.168.1.20"): NOW,
        (PHONE, "192.168.1.20"): later,
    }


def test_a_name_replaces_the_one_kept_and_no_name_leaves_it(session: Session) -> None:
    record(session, [seen(hostname="laptop", vendor="Example Devices Inc.")], NOW)

    record(session, [seen()], NOW)
    (device,) = devices(session).values()
    assert (device.hostname, device.vendor) == ("laptop", "Example Devices Inc.")

    record(session, [seen(hostname="work-laptop", vendor="Example Devices Ltd.")], NOW)
    (device,) = devices(session).values()
    assert (device.hostname, device.vendor) == ("work-laptop", "Example Devices Ltd.")


def test_the_last_name_told_in_one_go_is_the_one_kept(session: Session) -> None:
    record(session, [seen(hostname="first"), seen(hostname="second"), seen()], NOW)

    (device,) = devices(session).values()
    assert device.hostname == "second"


def test_a_time_ahead_of_now_is_taken_as_now(session: Session) -> None:
    ahead = NOW + timedelta(days=400)

    record(session, [seen(at=ahead, address="192.168.1.20")], NOW)

    (device,) = devices(session).values()
    assert (device.first_seen_at, device.last_seen_at) == (NOW, NOW)
    (address,) = addresses(session).values()
    assert (address.first_seen_at, address.last_seen_at) == (NOW, NOW)


def test_a_device_goes_with_its_addresses(session: Session) -> None:
    record(session, [seen(address="192.168.1.20")], NOW)
    session.commit()

    session.delete(devices(session)[LAPTOP])
    session.commit()

    assert addresses(session) == {}
