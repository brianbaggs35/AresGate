from datetime import UTC, datetime
from ipaddress import IPv4Address
from typing import Any

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.collectors import registry as collectors
from app.collectors.base import Collector
from app.collectors.opnsense import leases
from app.collectors.opnsense.arp_table import ArpTable, sightings
from app.collectors.opnsense.dnsmasq_leases import DnsmasqLeases
from app.collectors.opnsense.kea_leases import KeaLeases, holds
from app.config import Settings
from app.models import CollectorHealth, Device, DeviceAddress, utcnow
from e2e import stand_ins
from e2e.stand_ins import opnsense
from tests.opnsense import KEY, SECRET, answering, collect, run
from tests.stubs import Serve

NOW = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
LAPTOP = "00:11:22:0a:0b:0c"
PHONE = "ac:de:48:00:00:02"
FIREWALL = "ac:de:48:00:00:01"
PRINTER = "f0:ad:4e:00:00:01"
CAMERA = "00:1a:2b:00:00:01"


def firewall(*services: str) -> Any:
    """A firewall with what the stand-in has in its ARP table and, if those are installed,
    among the leases of Dnsmasq and Kea."""
    return opnsense(
        KEY,
        SECRET,
        set(services),
        arp_table=stand_ins.sample_arp_table(),
        dnsmasq_leases=stand_ins.sample_dnsmasq_leases(),
        kea_leases=stand_ins.sample_kea_leases(),
    )


def known(session: Session) -> dict[str, tuple[str | None, str | None]]:
    """The hostname and the maker of each device kept, by its hardware address."""
    session.expire_all()
    return {
        device.mac: (device.hostname, device.vendor) for device in session.scalars(select(Device))
    }


def addresses(session: Session) -> dict[str, set[str]]:
    session.expire_all()
    rows = session.execute(
        select(Device.mac, DeviceAddress.address).join(
            DeviceAddress, DeviceAddress.device_id == Device.id
        )
    )
    found: dict[str, set[str]] = {}
    for mac, address in rows:
        found.setdefault(mac, set()).add(str(address))
    return found


def record_of(session: Session, collector: Collector) -> CollectorHealth:
    session.expire_all()
    return session.scalars(
        select(CollectorHealth).where(CollectorHealth.collector == collector.key)
    ).one()


class TestAsScheduledCollectors:
    @pytest.mark.parametrize(
        ("collector", "module"),
        [(ArpTable, "firewall"), (DnsmasqLeases, "dnsmasq"), (KeaLeases, "kea")],
    )
    def test_each_reads_the_firewalls_api_unless_its_module_is_off(
        self, collector: type[Collector], module: str
    ) -> None:
        assert collector.reads("opnsense", "api")
        assert not collector.reads("opnsense", "zenarmor")
        assert not collector.reads("ntopng", "api")
        assert collector.module == module

    @pytest.mark.parametrize("collector", [ArpTable(), DnsmasqLeases(), KeaLeases()])
    def test_each_is_one_of_the_collectors_with_a_name_of_its_own(
        self, collector: Collector
    ) -> None:
        assert collectors.find(collector.key) is not None
        assert [item.key for item in collectors.COLLECTORS].count(collector.key) == 1


class TestTheArpTableRead:
    def test_each_device_in_it_is_a_sighting(self) -> None:
        found = sightings(stand_ins.sample_arp_table(), NOW)

        assert [(item.mac, item.address, item.hostname, item.vendor) for item in found] == [
            (LAPTOP, IPv4Address("192.168.1.20"), None, "Example Devices Inc."),
            (PHONE, IPv4Address("192.168.1.21"), "phone.lan", None),
            (FIREWALL, IPv4Address("192.168.1.1"), None, None),
        ]
        assert {item.seen_at for item in found} == {NOW}

    def test_an_entry_that_went_stale_is_not_a_sighting(self) -> None:
        stale = {"mac": LAPTOP, "ip": "192.168.1.20", "expired": True}
        fresh = {"mac": PHONE, "ip": "192.168.1.21", "expired": False}

        assert [item.mac for item in sightings([stale, fresh], NOW)] == [PHONE]

    @pytest.mark.parametrize("expired", [False, "false", 0, None, "yes"])
    def test_only_an_entry_that_says_it_is_stale_is_left_out(self, expired: object) -> None:
        assert len(sightings([{"mac": LAPTOP, "ip": "192.168.1.20", "expired": expired}], NOW)) == 1

    def test_what_is_not_an_entry_of_a_device_is_skipped(self) -> None:
        entries = [
            "text",
            None,
            7,
            {},
            {"ip": "192.168.1.9"},
            {"mac": "(incomplete)", "ip": "192.168.1.8"},
            {"mac": "ff:ff:ff:ff:ff:ff", "ip": "192.168.1.255"},
            {"mac": LAPTOP, "ip": "not an address", "hostname": 5},
        ]

        found = sightings(entries, NOW)

        assert [(item.mac, item.address, item.hostname) for item in found] == [(LAPTOP, None, "5")]


class TestTheArpTableRun:
    def test_it_stores_the_devices_with_their_addresses_and_makers(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        before = utcnow()
        run(session, settings, engine, serve, ArpTable(), firewall())

        assert known(session) == {
            LAPTOP: (None, "Example Devices Inc."),
            PHONE: ("phone.lan", None),
            FIREWALL: (None, None),
        }
        assert addresses(session) == {
            LAPTOP: {"192.168.1.20"},
            PHONE: {"192.168.1.21"},
            FIREWALL: {"192.168.1.1"},
        }
        # The stale entry is left out, and the time is the run's.
        session.expire_all()
        for device in session.scalars(select(Device)):
            assert before <= device.first_seen_at == device.last_seen_at <= utcnow()
        record = record_of(session, ArpTable())
        assert (record.consecutive_failures, record.last_items) == (0, 3)

    def test_reading_it_again_finds_the_same_devices(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        run(session, settings, engine, serve, ArpTable(), firewall())
        collect(settings, engine, ArpTable())

        assert len(known(session)) == 3
        assert record_of(session, ArpTable()).last_items == 3

    def test_a_table_with_nothing_in_it_is_not_a_failure(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        run(session, settings, engine, serve, ArpTable(), answering([]))

        record = record_of(session, ArpTable())
        assert (record.consecutive_failures, record.last_items) == (0, 0)
        assert known(session) == {}

    def test_a_table_of_stale_entries_is_not_a_failure(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        reply = [{"mac": LAPTOP, "ip": "192.168.1.20", "expired": True}]
        run(session, settings, engine, serve, ArpTable(), answering(reply))

        assert record_of(session, ArpTable()).last_items == 0
        assert known(session) == {}

    @pytest.mark.parametrize("reply", [None, {}, {"arp": []}, "text", 7])
    def test_an_answer_that_is_not_a_list_is_reported(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve, reply: object
    ) -> None:
        run(session, settings, engine, serve, ArpTable(), answering(reply))

        assert "doesn't look like OPNsense's" in (record_of(session, ArpTable()).last_error or "")

    @pytest.mark.parametrize("reply", [["text"], [{"ip": "192.168.1.20"}], [None, 3]])
    def test_a_list_of_things_that_are_not_entries_is_reported(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve, reply: object
    ) -> None:
        run(session, settings, engine, serve, ArpTable(), answering(reply))

        assert "ARP table isn't in a form" in (record_of(session, ArpTable()).last_error or "")
        assert known(session) == {}

    def test_a_user_who_may_not_see_the_table_is_reported(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        run(session, settings, engine, serve, ArpTable(), answering({}, status=403))

        assert "didn't accept the credentials" in (record_of(session, ArpTable()).last_error or "")


class TestTheLeasesRead:
    def test_each_lease_of_a_client_with_a_hardware_address_is_a_sighting(self) -> None:
        found = leases.sightings(stand_ins.sample_dnsmasq_leases(), NOW)

        assert [(item.mac, item.address, item.hostname, item.vendor) for item in found] == [
            (LAPTOP, IPv4Address("192.168.1.20"), "laptop", "Example Devices Inc."),
            (PRINTER, IPv4Address("192.168.1.30"), None, "Example Printers Ltd."),
        ]

    @pytest.mark.parametrize(
        ("state", "in_force"),
        [(0, True), ("0", True), (None, True), ("", True), (1, False), (2, False), ("1", False)],
    )
    def test_a_kea_lease_holds_if_its_state_is_zero(self, state: object, in_force: bool) -> None:
        lease = {} if state is None else {"state": state}

        assert holds(lease) is in_force


class TestTheDnsmasqLeasesRun:
    def test_it_stores_the_devices_and_their_names(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        run(session, settings, engine, serve, DnsmasqLeases(), firewall("dnsmasq"))

        assert known(session) == {
            LAPTOP: ("laptop", "Example Devices Inc."),
            PRINTER: (None, "Example Printers Ltd."),
        }
        assert addresses(session) == {LAPTOP: {"192.168.1.20"}, PRINTER: {"192.168.1.30"}}
        record = record_of(session, DnsmasqLeases())
        assert (record.consecutive_failures, record.last_items) == (0, 2)

    def test_a_device_of_the_arp_table_is_given_its_name_by_the_lease(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        run(session, settings, engine, serve, ArpTable(), firewall("dnsmasq"))
        assert known(session)[LAPTOP] == (None, "Example Devices Inc.")

        collect(settings, engine, DnsmasqLeases())

        assert known(session)[LAPTOP] == ("laptop", "Example Devices Inc.")
        assert set(known(session)) == {LAPTOP, PHONE, FIREWALL, PRINTER}
        assert len(addresses(session)[LAPTOP]) == 1

    def test_without_leases_it_is_not_a_failure(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        run(session, settings, engine, serve, DnsmasqLeases(), answering({"rows": [], "total": 0}))

        record = record_of(session, DnsmasqLeases())
        assert (record.consecutive_failures, record.last_items) == (0, 0)

    @pytest.mark.parametrize("reply", [None, [], {}, {"rows": "none"}, {"rows": {}}, "text"])
    def test_an_answer_without_a_list_of_leases_is_reported(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve, reply: object
    ) -> None:
        run(session, settings, engine, serve, DnsmasqLeases(), answering(reply))

        error = record_of(session, DnsmasqLeases()).last_error or ""
        assert "doesn't look like OPNsense's" in error

    @pytest.mark.parametrize("rows", [["text"], [{"address": "192.168.1.20"}], [None, 3]])
    def test_leases_that_do_not_say_who_holds_them_are_reported(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve, rows: object
    ) -> None:
        run(session, settings, engine, serve, DnsmasqLeases(), answering({"rows": rows}))

        error = record_of(session, DnsmasqLeases()).last_error or ""
        assert "leases aren't in a form" in error

    def test_a_firewall_without_dnsmasq_is_reported(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        run(session, settings, engine, serve, DnsmasqLeases(), firewall())

        assert record_of(session, DnsmasqLeases()).consecutive_failures == 1

    def test_a_user_who_may_not_see_the_leases_is_reported(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        run(session, settings, engine, serve, DnsmasqLeases(), answering({}, status=403))

        error = record_of(session, DnsmasqLeases()).last_error or ""
        assert "didn't accept the credentials" in error


class TestTheKeaLeasesRun:
    def test_it_stores_the_devices_whose_leases_hold(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        run(session, settings, engine, serve, KeaLeases(), firewall("kea"))

        # The lease that ran out is not a device that is there, and a name is written without
        # the dot that ends it.
        assert known(session) == {CAMERA: ("camera.lan", "Example Cameras Corp.")}
        assert addresses(session) == {CAMERA: {"192.168.1.40"}}
        record = record_of(session, KeaLeases())
        assert (record.consecutive_failures, record.last_items) == (0, 1)

    def test_a_firewall_without_kea_is_reported(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        run(session, settings, engine, serve, KeaLeases(), firewall("dnsmasq"))

        assert record_of(session, KeaLeases()).consecutive_failures == 1

    def test_a_user_who_may_not_see_the_leases_is_reported(
        self, session: Session, settings: Settings, engine: Engine, serve: Serve
    ) -> None:
        run(session, settings, engine, serve, KeaLeases(), answering({}, status=403))

        error = record_of(session, KeaLeases()).last_error or ""
        assert "didn't accept the credentials" in error
