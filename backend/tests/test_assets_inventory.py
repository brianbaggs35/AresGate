from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.assets import inventory
from app.assets.inventory import Asset, Inventory
from app.devices.sighting import NewSighting
from app.devices.store import record
from app.models import DeviceSource, IntegrationConnection, Interface
from e2e import factories
from e2e.factories import AssetSpec, HostSpec, Listed

NOW = datetime(2026, 11, 1, 18, 0, tzinfo=UTC)
LAPTOP = "00:11:22:0a:0b:0c"
PHONE = "02:aa:bb:cc:dd:ee"


def load(
    session: Session, devices: list[AssetSpec] | None = None, hosts: list[HostSpec] | None = None
) -> Inventory:
    factories.assets(session, NOW, devices or [], hosts or [])
    session.flush()
    return inventory.load(session, NOW)


def one(found: Inventory) -> Asset:
    (asset,) = found.assets
    return asset


def by_name(found: Inventory) -> dict[str, Asset]:
    return {asset.name: asset for asset in found.assets}


def arp(minutes: float = 1) -> Listed:
    return Listed("opnsense", "arp", minutes)


class TestWhetherADeviceIsThere:
    def test_a_device_the_arp_table_lists_now_is_online(self, session: Session) -> None:
        assert one(load(session, [AssetSpec(listed=(arp(1),))])).status == "online"

    def test_only_a_few_missed_reads_are_forgiven(self, session: Session) -> None:
        inside = AssetSpec(hostname="inside", listed=(arp(9),))
        outside = AssetSpec(hostname="outside", listed=(arp(11),))

        found = by_name(load(session, [inside, outside]))

        assert {name: asset.status for name, asset in found.items()} == {
            "inside": "online",
            "outside": "recent",
        }

    def test_a_device_that_only_has_a_lease_is_never_online(self, session: Session) -> None:
        lease = Listed("opnsense", "dhcp", 0)

        assert one(load(session, [AssetSpec(listed=(lease,))])).status == "recent"

    def test_ntopng_listing_a_host_is_presence(self, session: Session) -> None:
        listed = Listed("ntopng", "hosts", 2)

        assert one(load(session, [AssetSpec(listed=(listed,))])).status == "online"

    def test_a_lease_alongside_a_stale_arp_entry_is_not_presence(self, session: Session) -> None:
        listed = (Listed("opnsense", "arp", 90), Listed("opnsense", "dhcp", 1))

        assert one(load(session, [AssetSpec(listed=listed)])).status == "recent"

    def test_a_device_not_listed_for_a_day_has_been_away(self, session: Session) -> None:
        assert one(load(session, [AssetSpec(listed=(arp(24 * 60 + 5),))])).status == "away"
        other = load(session, [AssetSpec(mac=PHONE, listed=(arp(23 * 60),))])
        assert {asset.mac: asset.status for asset in other.assets}[PHONE] == "recent"

    def test_a_device_with_nothing_said_of_who_listed_it_goes_by_when_it_was_listed(
        self, session: Session
    ) -> None:
        # What was stored before the integrations were kept with it.
        record(session, [_seen(NOW - timedelta(minutes=1))], NOW, source="opnsense", via="arp")
        session.query(DeviceSource).delete()
        session.flush()

        asset = one(inventory.load(session, NOW))

        assert (asset.status, asset.listings) == ("recent", ())

    def test_a_way_this_version_does_not_know_is_not_presence(self, session: Session) -> None:
        record(session, [_seen(NOW)], NOW, source="opnsense", via="arp")
        row = session.query(DeviceSource).one()
        row.via = "from-the-future"
        session.flush()

        asset = one(inventory.load(session, NOW))

        assert [(item.via, item.presence) for item in asset.listings] == [
            ("from-the-future", False)
        ]
        assert asset.status == "recent"


def _seen(at: datetime) -> NewSighting:
    found = NewSighting.of(LAPTOP, at)
    assert found is not None
    return found


class TestWhatIsKnownOfADevice:
    def test_every_integration_that_listed_it_is_there_with_how_and_when(
        self, session: Session
    ) -> None:
        spec = AssetSpec(
            addresses=("192.168.1.20",),
            listed=(arp(1), Listed("opnsense", "dhcp", 4), Listed("ntopng", "hosts", 2)),
        )

        asset = one(load(session, [spec]))

        assert [(item.source, item.via) for item in asset.listings] == [
            ("ntopng", "hosts"),
            ("opnsense", "arp"),
            ("opnsense", "dhcp"),
        ]
        assert asset.last_seen_at == NOW - timedelta(minutes=1)

    def test_the_name_is_the_host_name_else_the_maker_else_the_hardware_address(
        self, session: Session
    ) -> None:
        named = AssetSpec(hostname="laptop", vendor="Example Devices Inc.", mac=LAPTOP)
        made = AssetSpec(vendor="Example Printers Ltd.", mac="00:11:22:0a:0b:0d")
        bare = AssetSpec(mac="00:11:22:0a:0b:0e")

        found = load(session, [named, made, bare])

        assert sorted(asset.name for asset in found.assets) == [
            "00:11:22:0a:0b:0e",
            "Example Printers Ltd.",
            "laptop",
        ]

    def test_something_says_what_it_is_if_it_has_a_name_or_a_maker(self, session: Session) -> None:
        specs = [
            AssetSpec(hostname="laptop"),
            AssetSpec(vendor="Example"),
            AssetSpec(),
        ]

        found = load(session, specs)

        assert sorted(asset.identified for asset in found.assets) == [False, True, True]

    def test_a_hardware_address_the_device_made_up_is_private(self, session: Session) -> None:
        found = load(session, [AssetSpec(mac=PHONE), AssetSpec(mac=LAPTOP)])

        assert {asset.mac: asset.private_mac for asset in found.assets} == {
            PHONE: True,
            LAPTOP: False,
        }

    def test_the_addresses_it_has_now_come_before_the_ones_it_had(self, session: Session) -> None:
        spec = AssetSpec(
            addresses=("192.168.1.20", "fd00::20"),
            earlier=("192.168.1.99",),
            listed=(arp(1),),
        )

        asset = one(load(session, [spec]))

        assert [str(address) for address in asset.addresses] == [
            "192.168.1.20",
            "fd00::20",
            "192.168.1.99",
        ]
        assert asset.current == 2

    def test_a_device_never_listed_at_an_address_has_none(self, session: Session) -> None:
        asset = one(load(session, [AssetSpec()]))

        assert (asset.addresses, asset.current) == ((), 0)


class TestWhatIsNew:
    def test_a_device_first_listed_in_the_last_week_is_new(self, session: Session) -> None:
        old = AssetSpec(hostname="old", first_seen_hours=24 * 40)
        recent = AssetSpec(hostname="recent", first_seen_hours=48)
        older = AssetSpec(hostname="older", first_seen_hours=24 * 8)

        found = by_name(load(session, [old, recent, older]))

        assert {name: asset.is_new for name, asset in found.items()} == {
            "old": False,
            "recent": True,
            "older": False,
        }

    def test_the_devices_found_on_the_first_day_are_the_network_as_it_was_and_not_news(
        self, session: Session
    ) -> None:
        # AresGate was set up two days ago: what it found then is not new, and what it found
        # since is.
        first = AssetSpec(hostname="first", first_seen_hours=48)
        same_day = AssetSpec(hostname="same-day", first_seen_hours=40)
        since = AssetSpec(hostname="since", first_seen_hours=10)

        found = by_name(load(session, [first, same_day, since]))

        assert {name: asset.is_new for name, asset in found.items()} == {
            "first": False,
            "same-day": False,
            "since": True,
        }

    def test_nothing_is_new_the_day_it_is_set_up(self, session: Session) -> None:
        found = load(session, [AssetSpec(first_seen_hours=2), AssetSpec(first_seen_hours=1)])

        assert not any(asset.is_new for asset in found.assets)
        assert found.watching_since == NOW - timedelta(hours=2)

    def test_with_no_assets_there_is_nothing_watched_yet(self, session: Session) -> None:
        found = inventory.load(session, NOW)

        assert (found.assets, found.watching_since) == ([], None)


class TestMachinesThatAreDevices:
    def test_an_agent_with_the_address_of_a_device_is_that_device(self, session: Session) -> None:
        device = AssetSpec(mac=LAPTOP, addresses=("192.168.1.41",), listed=(arp(1),))
        agent = HostSpec("002", hostname="laptop", address="192.168.1.41")

        asset = one(load(session, [device], [agent]))

        assert asset.kind == "device"
        wazuh = next(item for item in asset.listings if item.source == "wazuh")
        assert (wazuh.matched_by, wazuh.state, wazuh.presence) == ("address", "active", True)

    def test_the_name_the_agent_has_names_a_device_that_has_none(self, session: Session) -> None:
        device = AssetSpec(mac=LAPTOP, addresses=("192.168.1.41",))
        agent = HostSpec("002", hostname="web1", address="192.168.1.41")

        asset = one(load(session, [device], [agent]))

        assert (asset.name, asset.hostname, asset.identified) == ("web1", "web1", True)

    def test_a_device_with_a_name_keeps_it(self, session: Session) -> None:
        device = AssetSpec(hostname="laptop", addresses=("192.168.1.41",))
        agent = HostSpec("002", hostname="agent-name", address="192.168.1.41")

        assert one(load(session, [device], [agent])).name == "laptop"

    def test_an_address_two_devices_had_belongs_to_the_one_that_had_it_last(
        self, session: Session
    ) -> None:
        before = AssetSpec(mac=LAPTOP, addresses=("192.168.1.41",), listed=(arp(600),))
        now = AssetSpec(mac=PHONE, addresses=("192.168.1.41",), listed=(arp(1),))
        agent = HostSpec("002", address="192.168.1.41")

        found = load(session, [before, now], [agent])

        assert {asset.mac: [item.source for item in asset.listings] for asset in found.assets} == {
            LAPTOP: ["opnsense"],
            PHONE: ["opnsense", "wazuh"],
        }

    def test_which_device_had_the_address_last_does_not_depend_on_the_order_they_are_stored_in(
        self, session: Session
    ) -> None:
        now = AssetSpec(mac=LAPTOP, addresses=("192.168.1.41",), listed=(arp(1),))
        before = AssetSpec(mac=PHONE, addresses=("192.168.1.41",), listed=(arp(600),))
        agent = HostSpec("002", address="192.168.1.41")

        found = load(session, [now, before], [agent])

        assert {asset.mac: [item.source for item in asset.listings] for asset in found.assets} == {
            LAPTOP: ["opnsense", "wazuh"],
            PHONE: ["opnsense"],
        }

    def test_with_no_address_that_matches_the_name_does(self, session: Session) -> None:
        device = AssetSpec(hostname="Laptop.lan", addresses=("192.168.1.99",))
        agent = HostSpec("002", hostname="laptop", address="10.9.9.9")

        asset = one(load(session, [device], [agent]))

        wazuh = next(item for item in asset.listings if item.source == "wazuh")
        assert wazuh.matched_by == "hostname"
        # The address the agent gave is one more it is said to have, after the ones it was seen at.
        assert [str(address) for address in asset.addresses] == ["192.168.1.99", "10.9.9.9"]
        assert asset.current == 1

    def test_the_address_beats_the_name(self, session: Session) -> None:
        by_the_address = AssetSpec(mac=LAPTOP, hostname="one", addresses=("192.168.1.41",))
        by_the_name = AssetSpec(mac=PHONE, hostname="laptop", addresses=("192.168.1.50",))
        agent = HostSpec("002", hostname="laptop", address="192.168.1.41")

        found = load(session, [by_the_address, by_the_name], [agent])

        assert {asset.name: len(asset.listings) for asset in found.assets} == {
            "one": 2,
            "laptop": 1,
        }

    def test_a_name_two_devices_have_is_not_enough_to_say_which(self, session: Session) -> None:
        devices = [
            AssetSpec(mac=LAPTOP, hostname="laptop"),
            AssetSpec(mac=PHONE, hostname="LAPTOP.lan"),
        ]

        found = load(session, devices, [HostSpec("002", hostname="laptop")])

        assert sorted(asset.kind for asset in found.assets) == ["device", "device", "host"]

    @pytest.mark.parametrize("name", ["localhost", "ubuntu", "Debian.local"])
    def test_a_name_too_common_to_mean_anything_is_not_enough(
        self, session: Session, name: str
    ) -> None:
        found = load(session, [AssetSpec(hostname=name)], [HostSpec("002", hostname=name)])

        assert sorted(asset.kind for asset in found.assets) == ["device", "host"]

    def test_a_machine_with_no_name_and_no_matching_address_is_its_own_asset(
        self, session: Session
    ) -> None:
        found = load(session, [AssetSpec(addresses=("192.168.1.20",))], [HostSpec("002")])

        assert sorted(asset.kind for asset in found.assets) == ["device", "host"]


class TestMachinesOnTheirOwn:
    def test_an_agent_nothing_matches_is_an_asset_of_its_own(self, session: Session) -> None:
        found = load(session, hosts=[HostSpec("002", hostname="web1", address="10.0.0.5")])

        asset = one(found)

        assert (asset.kind, asset.name, asset.mac, asset.vendor) == ("host", "web1", None, None)
        assert asset.key.startswith("host-")
        assert [str(address) for address in asset.addresses] == ["10.0.0.5"]
        assert (asset.status, asset.identified, asset.private_mac) == ("online", True, False)
        [listing] = asset.listings
        assert (listing.source, listing.via, listing.matched_by) == ("wazuh", "agent", None)

    def test_a_machine_with_no_key_cannot_be_listed(self, session: Session) -> None:
        found = load(session, hosts=[HostSpec(" "), HostSpec("002", address="10.0.0.5")])

        assert [asset.name for asset in found.assets] == ["10.0.0.5"]

    def test_it_is_named_by_its_address_and_then_by_how_it_was_listed(
        self, session: Session
    ) -> None:
        found = load(
            session,
            hosts=[HostSpec("002", address="10.0.0.5"), HostSpec("003")],
        )

        assert sorted(asset.name for asset in found.assets) == ["10.0.0.5", "Agent 003"]

    def test_it_is_online_only_while_it_is_in_touch_and_was_heard_from(
        self, session: Session
    ) -> None:
        hosts = [
            HostSpec("1", hostname="in-touch"),
            HostSpec("2", hostname="stale", minutes_ago=30),
            HostSpec("3", hostname="gone", state="disconnected", online=False, minutes_ago=120),
            HostSpec(
                "4", hostname="long-gone", state="disconnected", online=False, minutes_ago=3000
            ),
        ]

        found = by_name(load(session, hosts=hosts))

        assert {name: asset.status for name, asset in found.items()} == {
            "in-touch": "online",
            "stale": "recent",
            "gone": "recent",
            "long-gone": "away",
        }

    def test_an_agent_that_is_new_to_a_network_that_has_been_watched_a_while_is_new(
        self, session: Session
    ) -> None:
        old = AssetSpec(hostname="old", first_seen_hours=24 * 30)

        found = load(session, [old], [HostSpec("002", hostname="web1", address="10.0.0.5")])

        assert {asset.name: asset.is_new for asset in found.assets} == {"old": False, "web1": True}


def network(session: Session, name: str, *blocks: str) -> Interface:
    made = Interface(name=name, role="home", networks=list(blocks), position=0)
    session.add(made)
    session.flush()
    return made


class TestWhichInterfaceItIsOn:
    def test_a_device_is_on_the_interfaces_whose_networks_hold_its_current_address(
        self, session: Session
    ) -> None:
        home = network(session, "Home", "192.168.1.0/24")
        iot = network(session, "IoT", "192.168.20.0/24", "fd00:20::/64")
        spec = AssetSpec(
            hostname="camera", addresses=("192.168.20.7", "fd00:20::7"), earlier=("192.168.1.7",)
        )

        found = load(session, [spec])

        assert one(found).interfaces == (iot.id,)
        assert [network.id for network in found.networks] == [home.id, iot.id]

    def test_an_interface_with_no_networks_cannot_say_what_is_on_it(self, session: Session) -> None:
        network(session, "Nothing yet")

        found = load(session, [AssetSpec(addresses=("192.168.1.7",))])

        assert (found.networks, one(found).interfaces) == ([], ())

    def test_a_network_that_is_not_one_is_skipped_without_losing_the_rest(
        self, session: Session
    ) -> None:
        home = network(session, "Home", "not a network", "192.168.1.0/24")

        found = load(session, [AssetSpec(addresses=("192.168.1.7",))])

        assert one(found).interfaces == (home.id,)

    def test_an_agent_on_its_own_is_placed_by_its_address(self, session: Session) -> None:
        home = network(session, "Home", "10.0.0.0/8")

        found = load(session, hosts=[HostSpec("002", address="10.0.0.5"), HostSpec("003")])

        assert {asset.name: asset.interfaces for asset in found.assets} == {
            "10.0.0.5": (home.id,),
            "Agent 003": (),
        }


class TestWhoCouldListDevices:
    def test_each_integration_is_connected_when_everything_it_lists_with_is(
        self, session: Session
    ) -> None:
        for integration, connection in [("opnsense", "api"), ("wazuh", "indexer")]:
            session.add(
                IntegrationConnection(
                    integration=integration, connection=connection, base_url="https://x.example"
                )
            )
        session.flush()

        found = inventory.load(session, NOW)

        assert {item.key: item.connected for item in found.suppliers} == {
            "opnsense": True,
            "ntopng": False,
            # Wazuh lists its agents through the manager, not the indexer.
            "wazuh": False,
        }

    def test_they_are_named_with_what_they_list(self, session: Session) -> None:
        found = inventory.load(session, NOW)

        assert [(item.name, item.ways) for item in found.suppliers] == [
            ("OPNsense", ("ARP table", "DHCP leases")),
            ("ntopng", ("Active hosts",)),
            ("Wazuh", ("Agent",)),
        ]

    def test_an_integration_this_version_does_not_know_is_named_by_its_key(self) -> None:
        assert inventory.name_of("somenew") == "somenew"
        assert inventory.name_of("crowdsec") == "CrowdSec"
