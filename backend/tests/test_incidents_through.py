"""Through: the devices of the network that an incident touched."""

from datetime import UTC, datetime
from ipaddress import ip_address
from typing import Any

from sqlalchemy.orm import Session

from app.assets import inventory
from app.assets.inventory import Asset
from app.incidents import through
from app.models import Incident, IncidentSignal
from e2e import factories
from e2e.factories import AssetSpec, Listed

NOW = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)
OUTSIDE = "93.184.216.34"
LAPTOP = "192.168.1.20"
CAMERA = "192.168.1.30"
FIREWALL = "192.168.1.1"


def incident(**changes: Any) -> Incident:
    fields: dict[str, Any] = {
        "subject": OUTSIDE,
        "addresses": [ip_address(OUTSIDE), ip_address(LAPTOP)],
    }
    return Incident(**{**fields, **changes})


def signal(source: str = "wazuh", src: str = OUTSIDE, dst: str = LAPTOP) -> IncidentSignal:
    return IncidentSignal(
        source=source, occurred_at=NOW, src_address=ip_address(src), dst_address=ip_address(dst)
    )


def assets(session: Session) -> list[Asset]:
    factories.assets(
        session,
        NOW,
        [
            AssetSpec(
                hostname="router",
                mac="00:11:22:00:00:01",
                addresses=(FIREWALL,),
                listed=(Listed("opnsense", "arp", 1, own=True),),
            ),
            AssetSpec(
                hostname="laptop",
                mac="00:11:22:00:00:02",
                addresses=(LAPTOP,),
                listed=(Listed("opnsense", "arp", 1),),
            ),
            AssetSpec(
                hostname="camera",
                mac="00:11:22:00:00:03",
                addresses=(CAMERA,),
                earlier=("192.168.1.99",),
                listed=(Listed("opnsense", "arp", 1),),
            ),
        ],
        [],
    )
    session.flush()
    return inventory.load(session, NOW).assets


def roles(stops: list[through.Stop]) -> list[tuple[str, str]]:
    return [(stop.role, stop.address) for stop in stops]


class TestTheWayIn:
    def test_the_firewall_comes_first_and_then_the_device_the_traffic_was_for(
        self, session: Session
    ) -> None:
        stops = through.build(incident(), [signal()], assets(session), outbound=False)

        assert roles(stops) == [("gateway", FIREWALL), ("target", LAPTOP)]
        assert stops[1].asset is not None and stops[1].asset.name == "laptop"
        assert stops[1].signals == 1

    def test_outbound_traffic_meets_the_device_first_and_the_firewall_last(
        self, session: Session
    ) -> None:
        stops = through.build(
            incident(), [signal(src=LAPTOP, dst=OUTSIDE)], assets(session), outbound=True
        )

        assert roles(stops) == [("target", LAPTOP), ("gateway", FIREWALL)]

    def test_other_devices_that_turned_up_are_listed_after_the_one_it_was_for(
        self, session: Session
    ) -> None:
        found = incident(addresses=[ip_address(OUTSIDE), ip_address(LAPTOP), ip_address(CAMERA)])
        signals = [signal(), signal(dst=CAMERA), signal(dst=CAMERA)]

        stops = through.build(found, signals, assets(session), outbound=False)

        # The camera is named by more signals, so it is what most of the traffic was for.
        assert roles(stops) == [
            ("gateway", FIREWALL),
            ("target", CAMERA),
            ("also", LAPTOP),
        ]

    def test_an_incident_about_a_device_is_about_that_device(self, session: Session) -> None:
        found = incident(subject=LAPTOP, addresses=[ip_address(LAPTOP), ip_address(CAMERA)])

        stops = through.build(
            found, [signal(src=LAPTOP, dst=CAMERA)], assets(session), outbound=False
        )

        assert roles(stops) == [("target", LAPTOP), ("also", CAMERA)]

    def test_an_address_that_no_device_has_is_listed_as_an_address(self, session: Session) -> None:
        found = incident(addresses=[ip_address(OUTSIDE), ip_address("192.168.1.77")])

        stops = through.build(found, [signal(dst="192.168.1.77")], assets(session), outbound=False)

        assert roles(stops)[-1] == ("target", "192.168.1.77")
        assert stops[-1].asset is None

    def test_an_address_a_device_had_is_that_device_unless_another_has_it_now(
        self, session: Session
    ) -> None:
        found = incident(addresses=[ip_address(OUTSIDE), ip_address("192.168.1.99")])

        stops = through.build(found, [signal(dst="192.168.1.99")], assets(session), outbound=False)

        assert stops[-1].asset is not None and stops[-1].asset.name == "camera"

    def test_the_firewall_that_is_the_target_is_listed_once(self, session: Session) -> None:
        found = incident(addresses=[ip_address(OUTSIDE), ip_address(FIREWALL)])

        stops = through.build(found, [signal(dst=FIREWALL)], assets(session), outbound=False)

        assert roles(stops) == [("gateway", FIREWALL)]

    def test_a_sweep_of_a_whole_network_is_cut_to_a_few_devices(self, session: Session) -> None:
        swept = [f"192.168.1.{number}" for number in range(100, 130)]
        found = incident(addresses=[ip_address(OUTSIDE), *(ip_address(each) for each in swept)])

        stops = through.build(
            found, [signal(dst=each) for each in swept], assets(session), outbound=False
        )

        assert len(stops) == through.MAX_STOPS + 1


class TestWhereTheFirewallIsNotOnTheWay:
    def test_traffic_between_two_devices_does_not_cross_it(self, session: Session) -> None:
        found = incident(subject=LAPTOP, addresses=[ip_address(LAPTOP), ip_address(CAMERA)])

        stops = through.build(
            found, [signal(src=LAPTOP, dst=CAMERA)], assets(session), outbound=False
        )

        assert "gateway" not in {stop.role for stop in stops}

    def test_an_incident_about_a_rule_that_names_no_address_has_nothing(
        self, session: Session
    ) -> None:
        found = incident(subject="rule:ET SCAN", addresses=[])
        bare = IncidentSignal(source="suricata", occurred_at=NOW)

        assert through.build(found, [bare], assets(session), outbound=False) == []

    def test_a_network_with_no_firewall_listed_has_no_gateway(self, session: Session) -> None:
        listed = [asset for asset in assets(session) if not asset.own]

        stops = through.build(incident(), [signal()], listed, outbound=False)

        assert roles(stops) == [("target", LAPTOP)]
