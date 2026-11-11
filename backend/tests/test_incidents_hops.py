"""Hops: the path an incident travelled, drawn from the programs that reported it."""

from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from typing import Any

from app.incidents import hops
from app.models import Device, Incident, IncidentSignal

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
OUTSIDE = "93.184.216.34"
INSIDE = "192.168.1.20"


def incident(**changes: Any) -> Incident:
    fields: dict[str, Any] = {
        "subject": OUTSIDE,
        "addresses": [ip_address(OUTSIDE), ip_address(INSIDE)],
    }
    return Incident(**{**fields, **changes})


def signal(source: str, minutes: int = 0, **changes: Any) -> IncidentSignal:
    fields: dict[str, Any] = {
        "source": source,
        "occurred_at": NOW + timedelta(minutes=minutes),
        "src_address": ip_address(OUTSIDE),
        "dst_address": ip_address(INSIDE),
    }
    return IncidentSignal(**{**fields, **changes})


def build(
    found: Incident,
    signals: list[IncidentSignal],
    *,
    blocked: int = 0,
    dropped: int = 0,
    banned: bool = False,
    devices: list[tuple[Any, Device]] | None = None,
) -> hops.Path | None:
    return hops.build(
        found, signals, blocked=blocked, dropped=dropped, banned=banned, devices=devices or []
    )


def kinds(path: hops.Path | None) -> list[str]:
    assert path is not None
    return [hop.kind for hop in path.hops]


class TestTheWayIn:
    def test_the_programs_are_in_the_order_they_sit_between_the_internet_and_the_device(
        self,
    ) -> None:
        path = build(
            incident(), [signal("wazuh"), signal("opnsense"), signal("suricata"), signal("ntopng")]
        )

        assert path is not None
        assert path.direction == "inbound"
        assert kinds(path) == [
            "internet",
            "firewall",
            "detector",
            "monitor",
            "agent",
            "device",
        ]
        assert [hop.subject for hop in path.hops] == [
            OUTSIDE,
            "OPNsense",
            "suricata",
            "ntopng",
            "Wazuh",
            INSIDE,
        ]

    def test_each_hop_says_how_much_it_saw_and_when(self) -> None:
        path = build(incident(), [signal("opnsense", 0), signal("opnsense", 5)])

        assert path is not None
        firewall = path.hops[1]
        assert (firewall.alerts, firewall.source) == (2, "opnsense")
        assert (firewall.first_at, firewall.last_at) == (NOW, NOW + timedelta(minutes=5))

    def test_a_program_that_did_not_report_it_is_not_on_the_path(self) -> None:
        assert kinds(build(incident(), [signal("wazuh")])) == ["internet", "agent", "device"]

    def test_the_device_is_called_by_its_name_where_it_has_one(self) -> None:
        named = [(ip_address(INSIDE), Device(hostname="camera"))]

        path = build(incident(), [signal("wazuh")], devices=named)

        assert path is not None
        assert path.hops[-1].subject == "camera"

    def test_a_device_with_no_name_is_called_by_its_address(self) -> None:
        path = build(incident(), [signal("wazuh")], devices=[(ip_address(INSIDE), Device())])

        assert path is not None
        assert path.hops[-1].subject == INSIDE

    def test_a_program_the_path_does_not_know_sits_with_the_detectors(self) -> None:
        assert kinds(build(incident(), [signal("newthing")])) == ["internet", "detector", "device"]


class TestWhatEachDidAboutIt:
    def test_the_firewall_says_how_often_it_turned_it_away(self) -> None:
        once = build(incident(), [signal("opnsense")], blocked=1)
        often = build(incident(), [signal("opnsense")], blocked=4)

        assert once is not None
        assert often is not None
        assert once.hops[1].note == "Turned it away 1 time."
        assert often.hops[1].note == "Turned it away 4 times."

    def test_a_detector_says_how_many_alerts_it_stopped(self) -> None:
        once = build(incident(), [signal("suricata")], dropped=1)
        often = build(incident(), [signal("suricata")], dropped=3)

        assert once is not None
        assert often is not None
        assert once.hops[1].note == "Stopped 1 alert."
        assert often.hops[1].note == "Stopped 3 alerts."

    def test_a_detector_says_when_it_banned_the_address(self) -> None:
        path = build(incident(), [signal("crowdsec")], banned=True)

        assert path is not None
        assert path.hops[1].note == "Banned the address."

    def test_a_program_that_did_nothing_about_it_says_nothing(self) -> None:
        path = build(incident(), [signal("ntopng"), signal("opnsense"), signal("suricata")])

        assert path is not None
        assert [hop.note for hop in path.hops] == [None, None, None, None, None]


class TestTheWayOut:
    def test_what_a_device_sent_out_is_drawn_from_the_device_outwards(self) -> None:
        sent = signal("opnsense", src_address=ip_address(INSIDE), dst_address=ip_address(OUTSIDE))
        also = signal("wazuh", src_address=ip_address(INSIDE), dst_address=ip_address(OUTSIDE))

        path = build(incident(), [sent, also])

        assert path is not None
        assert path.direction == "outbound"
        assert [hop.subject for hop in path.hops] == [INSIDE, "Wazuh", "OPNsense", OUTSIDE]


class TestWhereThereIsNoPathToDraw:
    def test_an_incident_about_something_that_is_not_an_address_has_none(self) -> None:
        assert build(incident(subject="ssh-guessing"), [signal("opnsense")]) is None

    def test_an_incident_about_an_address_on_the_network_has_none(self) -> None:
        assert build(incident(subject=INSIDE), [signal("opnsense")]) is None

    def test_signals_that_do_not_say_which_way_it_went_give_none(self) -> None:
        bare = signal("opnsense", dst_address=None)

        assert build(incident(), [bare]) is None

    def test_an_incident_with_no_device_on_the_network_has_none(self) -> None:
        assert build(incident(addresses=[ip_address(OUTSIDE)]), [signal("opnsense")]) is None
