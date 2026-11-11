"""What was sent, and between whom: an incident's alerts as the conversations they are about."""

from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from typing import Any

from app.incidents import conversations, occurrences
from app.models import IncidentSignal

NOW = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
CLIENT = "192.168.1.20"
SERVER = "203.0.113.9"


def said(**changes: Any) -> dict[str, Any]:
    return {"facts": [], "tags": [], "mitre": [], "indicators": [], **changes}


def signal(minutes: int = 0, source: str = "ntopng", **changes: Any) -> IncidentSignal:
    fields: dict[str, Any] = {
        "occurred_at": NOW + timedelta(minutes=minutes),
        "event_id": minutes + 1,
        "source": source,
        "kind": "alert",
        "severity": 2,
        "summary": f"{source} saw it",
        "signature": "Flow",
        "src_address": ip_address(CLIENT),
        "src_port": 40000 + minutes,
        "dst_address": ip_address(SERVER),
        "dst_port": 53,
        "protocol": "tcp",
        "verdict": None,
        "duplicate": False,
        "twin_of": None,
        "evidence": None,
        **changes,
    }
    return IncidentSignal(**fields)


def told(*signals: IncidentSignal) -> conversations.Conversations:
    return conversations.of(occurrences.group(list(signals)))


def test_alerts_between_the_same_two_ends_over_one_port_are_one_conversation() -> None:
    found = told(
        signal(0),
        signal(5, src_port=1),
        signal(9, signature="Other", severity=3),
        signal(12, dst_port=443),
    )

    assert found.total == 2
    first, second = found.items
    assert (first.client.address, first.server.address, first.server.port) == (CLIENT, SERVER, 53)
    assert (first.alerts, first.kinds, first.protocol) == (3, 2, "tcp")
    assert first.severity == 3
    assert first.first_at == NOW
    assert first.last_at == NOW + timedelta(minutes=9)
    assert (second.alerts, second.server.port) == (1, 443)
    # The client's port is different for every connection, so it is not told.
    assert first.client.port is None


def test_an_alert_about_one_address_is_no_conversation() -> None:
    found = told(signal(0, src_address=None), signal(1, dst_address=None))

    assert found.items == []
    assert found.total == 0


def test_what_the_programs_said_of_the_flow_is_put_together() -> None:
    ntopng = signal(
        0,
        evidence=said(
            traffic={"bytes_out": 399, "bytes_in": 722},
            app="dns",
            flow={
                "duration": 61,
                "client": {"address": CLIENT, "name": "workstation", "location": "local"},
                "server": {
                    "address": SERVER,
                    "service": "domain",
                    "country": "US",
                    "location": "remote",
                    "blacklisted": True,
                },
            },
            indicators=[
                {"kind": "dns", "value": "example.com"},
                {"kind": "community_id", "value": "1:abc="},
            ],
        ),
    )
    twin = signal(
        0,
        source="opnsense",
        event_id=50,
        duplicate=True,
        twin_of=ntopng.event_id,
        evidence=said(
            traffic={"bytes_out": 1000, "bytes_in": 20},
            app="ignored",
            flow={"duration": 10, "server": {"address": SERVER, "country": "DE"}},
            indicators=[{"kind": "dns", "value": "example.com"}, {"kind": "sni", "value": "a.b"}],
        ),
    )

    (found,) = told(ntopng, twin).items

    # The biggest volume and the longest time any program counted, and the first word on the rest.
    assert (found.bytes_out, found.bytes_in, found.duration) == (1000, 722, 61)
    assert found.app == "dns"
    assert found.server.service == "domain"
    assert found.server.country == "US"
    assert found.server.blacklisted is True
    assert found.client.name == "workstation"
    assert found.client.location == "local"
    assert found.client.blacklisted is False
    # What was asked for, once; the community id is not a name.
    assert found.names == [
        {"kind": "dns", "value": "example.com"},
        {"kind": "sni", "value": "a.b"},
    ]
    # Both reported the alert; the one that reported first is listed first.
    assert found.programs == ["ntopng", "opnsense"]


def test_what_a_program_knows_of_an_address_is_told_in_every_conversation_it_is_in() -> None:
    known = signal(
        0,
        evidence=said(flow={"server": {"address": SERVER, "country": "US", "blacklisted": True}}),
    )
    other = signal(1, dst_port=443)

    first, second = told(known, other).items

    assert (first.server.country, second.server.country) == ("US", "US")
    assert second.server.blacklisted is True
    # An address on any blacklist is on one; a flow with no word on it is not said to be.
    assert second.client.blacklisted is False


def test_a_program_that_names_no_address_adds_nothing() -> None:
    (found,) = told(signal(0, evidence=said(flow={"server": {"country": "US"}}))).items

    assert found.server.country is None
    assert (found.bytes_out, found.bytes_in, found.duration, found.app) == (None,) * 4


def test_a_program_that_said_nothing_beyond_the_basics_is_still_listed_as_having_reported() -> None:
    (found,) = told(signal(0, source="wazuh")).items

    assert found.programs == ["wazuh"]
    assert found.names == []


def test_the_busiest_come_first_and_only_so_many_are_told_of() -> None:
    busy = [signal(minute, dst_port=1000 + minute) for minute in range(conversations.LIMIT + 3)]
    busy += [signal(40 + minute, dst_port=999, src_port=minute) for minute in range(3)]

    found = told(*busy)

    assert found.total == conversations.LIMIT + 4
    assert len(found.items) == conversations.LIMIT
    assert found.items[0].server.port == 999
    assert found.items[0].alerts == 3


def test_so_many_names_asked_for_fit_and_the_traffic_asks_for_names_only() -> None:
    names = [{"kind": "hostname", "value": f"h{number}.example"} for number in range(5)]
    names.append({"kind": "user", "value": "root"})

    (found,) = told(signal(0, evidence=said(indicators=names))).items

    assert [name["value"] for name in found.names] == ["h0.example", "h1.example", "h2.example"]
