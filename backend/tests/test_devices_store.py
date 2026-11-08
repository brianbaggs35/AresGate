from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address, IPv6Address
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.devices import store
from app.devices.sighting import NewHost, NewSighting
from app.models import Device, DeviceAddress, DeviceSource, HostListing

NOW = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
LAPTOP = "00:11:22:0a:0b:0c"
PHONE = "ac:de:48:00:00:02"


def record(
    session: Session,
    sightings: list[NewSighting],
    now: datetime,
    *,
    source: str = "opnsense",
    via: str = "arp",
) -> int:
    return store.record(session, sightings, now, source=source, via=via)


def seen(mac: str = LAPTOP, at: datetime = NOW, **changes: str | None) -> NewSighting:
    sighting = NewSighting.of(
        mac,
        at,
        address=changes.get("address"),
        hostname=changes.get("hostname"),
        vendor=changes.get("vendor"),
    )
    assert sighting is not None
    return sighting


def own_flags(session: Session) -> list[bool]:
    """Whether each row of a listing is one of the program's own addresses."""
    session.expire_all()
    return [row.own for row in session.scalars(select(DeviceSource))]


def listed(own: bool, at: datetime = NOW) -> NewSighting:
    sighting = NewSighting.of(LAPTOP, at, address="192.168.1.1", own=own)
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


def listings(session: Session) -> dict[tuple[str, str, str], DeviceSource]:
    """What lists each device, by its hardware address, the integration and how."""
    session.expire_all()
    rows = session.execute(
        select(Device.mac, DeviceSource).join(DeviceSource, DeviceSource.device_id == Device.id)
    )
    return {(mac, row.source, row.via): row for mac, row in rows}


class TestWhoListedTheDevice:
    def test_the_integration_and_the_way_are_kept_with_the_time(self, session: Session) -> None:
        record(session, [seen(address="192.168.1.20")], NOW, source="opnsense", via="arp")

        (row,) = listings(session).values()
        assert (row.source, row.via) == ("opnsense", "arp")
        assert (row.first_seen_at, row.last_seen_at) == (NOW, NOW)

    def test_each_way_a_device_is_listed_is_kept_apart(self, session: Session) -> None:
        later = NOW + timedelta(minutes=5)
        record(session, [seen()], NOW, source="opnsense", via="arp")
        record(session, [seen(at=later)], later, source="opnsense", via="dhcp")
        record(session, [seen(at=later)], later, source="ntopng", via="hosts")

        found = listings(session)

        assert set(found) == {
            (LAPTOP, "opnsense", "arp"),
            (LAPTOP, "opnsense", "dhcp"),
            (LAPTOP, "ntopng", "hosts"),
        }
        assert found[(LAPTOP, "opnsense", "arp")].last_seen_at == NOW
        assert found[(LAPTOP, "ntopng", "hosts")].last_seen_at == later

    def test_listing_a_device_again_moves_the_time_forward_and_never_back(
        self, session: Session
    ) -> None:
        later = NOW + timedelta(minutes=5)
        record(session, [seen()], NOW)
        record(session, [seen(at=later)], later)
        record(session, [seen(at=NOW)], later)

        (row,) = listings(session).values()
        assert (row.first_seen_at, row.last_seen_at) == (NOW, later)

    def test_a_way_nobody_knows_is_a_mistake_in_the_collector(self, session: Session) -> None:
        sightings = [seen()]

        with pytest.raises(ValueError, match="No device is listed 'telepathy'"):
            record(session, sightings, NOW, via="telepathy")

        assert devices(session) == {}


def machine(key: str = "002", at: datetime = NOW, **changes: Any) -> NewHost:
    fields: dict[str, Any] = {"state": "active", "online": True} | changes
    host = NewHost.of(key, at, **fields)
    assert host is not None
    return host


def machines(session: Session) -> dict[str, HostListing]:
    session.expire_all()
    return {row.key: row for row in session.scalars(select(HostListing))}


def record_machines(
    session: Session, hosts: list[NewHost], now: datetime = NOW, *, complete: bool = False
) -> int:
    return store.record_hosts(
        session, hosts, now, source="wazuh", connection="manager", via="agent", complete=complete
    )


class TestTheFirewallsOwnAddresses:
    def test_a_device_listed_as_one_of_the_firewalls_own_is_marked_so(
        self, session: Session
    ) -> None:
        record(session, [listed(own=True)], NOW)

        assert own_flags(session) == [True]

    def test_a_device_listed_as_a_neighbour_is_not_its_own(self, session: Session) -> None:
        record(session, [listed(own=False)], NOW)

        assert own_flags(session) == [False]

    def test_once_listed_as_its_own_it_stays_so(self, session: Session) -> None:
        later = NOW + timedelta(minutes=1)
        record(session, [listed(own=True)], NOW)
        record(session, [listed(own=False, at=later)], later)

        assert own_flags(session) == [True]

    def test_sightings_of_one_device_in_one_go_are_its_own_if_any_is(
        self, session: Session
    ) -> None:
        record(session, [listed(own=False), listed(own=True)], NOW)

        assert own_flags(session) == [True]


class TestMachinesWithNoHardwareAddress:
    def test_a_machine_is_stored_with_what_was_said_of_it(self, session: Session) -> None:
        found = machine(hostname="server", address="192.168.1.41")

        assert record_machines(session, [found]) == 1

        (row,) = machines(session).values()
        assert (row.source, row.connection, row.via, row.key) == (
            "wazuh",
            "manager",
            "agent",
            "002",
        )
        assert (row.hostname, str(row.address), row.state, row.online) == (
            "server",
            "192.168.1.41",
            "active",
            True,
        )
        assert (row.first_seen_at, row.last_seen_at) == (NOW, NOW)

    def test_listing_it_again_updates_it_and_keeps_when_it_was_first_listed(
        self, session: Session
    ) -> None:
        later = NOW + timedelta(minutes=5)
        record_machines(session, [machine(hostname="server", address="192.168.1.41")])
        record_machines(
            session,
            [machine(at=later, state="disconnected", online=False, hostname="server2")],
            later,
        )

        (row,) = machines(session).values()
        assert (row.hostname, row.state, row.online) == ("server2", "disconnected", False)
        # A listing that left out the address leaves the one kept.
        assert str(row.address) == "192.168.1.41"
        assert (row.first_seen_at, row.last_seen_at) == (NOW, later)

    def test_a_time_ahead_of_now_is_taken_as_now(self, session: Session) -> None:
        record_machines(session, [machine(at=NOW + timedelta(hours=1))])

        (row,) = machines(session).values()
        assert row.last_seen_at == NOW

    def test_the_same_key_in_one_call_is_one_machine(self, session: Session) -> None:
        assert record_machines(session, [machine(), machine(hostname="last")]) == 1

        assert machines(session)["002"].hostname == "last"

    def test_a_machine_a_complete_list_leaves_out_is_forgotten(self, session: Session) -> None:
        record_machines(session, [machine("001"), machine("002")])

        record_machines(session, [machine("002")], complete=True)

        assert set(machines(session)) == {"002"}

    def test_only_the_connection_that_listed_a_machine_can_make_it_forgotten(
        self, session: Session
    ) -> None:
        record_machines(session, [machine("001")])
        store.record_hosts(
            session,
            [machine("001")],
            NOW,
            source="elsewhere",
            connection="manager",
            via="agent",
            complete=True,
        )

        session.expire_all()
        found = {(row.source, row.key) for row in session.scalars(select(HostListing))}
        assert found == {("wazuh", "001"), ("elsewhere", "001")}

    def test_a_list_that_is_not_complete_forgets_nothing(self, session: Session) -> None:
        record_machines(session, [machine("001"), machine("002")])

        record_machines(session, [machine("002")], complete=False)

        assert set(machines(session)) == {"001", "002"}

    def test_a_complete_list_of_nothing_forgets_them_all(self, session: Session) -> None:
        record_machines(session, [machine("001")])

        assert record_machines(session, [], complete=True) == 0

        assert machines(session) == {}

    def test_a_way_nobody_knows_is_a_mistake_in_the_collector(self, session: Session) -> None:
        listed = [machine()]

        with pytest.raises(ValueError, match="No device is listed 'telepathy'"):
            store.record_hosts(
                session,
                listed,
                NOW,
                source="wazuh",
                connection="manager",
                via="telepathy",
                complete=False,
            )
