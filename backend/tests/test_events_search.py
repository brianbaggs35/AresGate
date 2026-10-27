from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.events import search
from app.events.event import Severity
from app.events.search import Context, SearchError
from app.events.store import record as record_events
from app.models import Event, Incident, IncidentSignal
from tests.helpers import new_event

NOW = datetime(2026, 10, 27, 15, 30, tzinfo=UTC)
CONTEXT = Context(zone=UTC, now=NOW)

# 203.0.113.0/24 is for examples and so are the others.
ATTACKER = "203.0.113.7"
SCANNER = "198.51.100.9"
DEVICE = "192.168.1.20"
V6 = "2001:db8::5"


def parse(text: str) -> search.Search:
    return search.parse(text, CONTEXT)


def refused(text: str) -> str:
    with pytest.raises(SearchError) as error:
        parse(text)
    return str(error.value)


@pytest.fixture
def events(session: Session, settings: Settings) -> dict[str, Event]:
    """Five events that differ in every way the language can ask about."""
    new = [
        new_event(
            source="wazuh",
            connection="indexer",
            kind="alert",
            severity=Severity.HIGH,
            occurred_at=NOW - timedelta(minutes=10),
            identity=("a",),
            summary="sshd: authentication failed",
            signature="Brute force on ssh",
            src_address=ATTACKER,
            src_port=41000,
            dst_address=DEVICE,
            dst_port=22,
            protocol="tcp",
            raw={"rule": {"id": "5710"}, "agent": {"name": "nas"}},
        ),
        new_event(
            source="opnsense",
            connection="api",
            kind="firewall",
            severity=Severity.LOW,
            occurred_at=NOW - timedelta(minutes=5),
            identity=("b",),
            summary="Blocked tcp",
            src_address=ATTACKER,
            src_port=50000,
            dst_address=DEVICE,
            dst_port=443,
            protocol="tcp",
        ),
        new_event(
            source="crowdsec",
            connection="lapi",
            kind="decision",
            severity=Severity.MEDIUM,
            occurred_at=NOW - timedelta(minutes=2),
            identity=("c",),
            summary="Ban for ssh-bruteforce",
            src_address=ATTACKER,
        ),
        new_event(
            source="ntopng",
            connection="api",
            kind="alert",
            severity=Severity.INFO,
            occurred_at=NOW - timedelta(hours=1),
            identity=("d",),
            summary="DNS query volume",
        ),
        new_event(
            source="opnsense",
            connection="api",
            kind="firewall",
            severity=Severity.CRITICAL,
            occurred_at=NOW - timedelta(days=2),
            identity=("e",),
            summary="udp flood",
            signature="ET DOS flood",
            src_address=V6,
            src_port=5353,
            dst_address=DEVICE,
            dst_port=53,
            protocol="udp",
        ),
    ]
    for event in new:
        record_events(session, settings, [event], event.occurred_at)
    session.commit()
    stored = session.scalars(select(Event).order_by(Event.occurred_at)).all()
    return {event.summary: event for event in stored}


def found(session: Session, text: str) -> set[str]:
    """What the search finds, by what the events say."""
    return set(session.scalars(select(Event.summary).where(*parse(text).conditions())))


def labels(text: str) -> list[str]:
    return [term.label for term in parse(text).terms]


ALL = {
    "sshd: authentication failed",
    "Blocked tcp",
    "Ban for ssh-bruteforce",
    "DNS query volume",
    "udp flood",
}


class TestFields:
    def test_nothing_typed_finds_everything(self, session: Session, events: object) -> None:
        assert found(session, "") == ALL

    def test_plain_words_are_looked_for_in_what_it_says_and_the_rule_that_fired(
        self, session: Session, events: object
    ) -> None:
        assert found(session, "ssh") == {"sshd: authentication failed", "Ban for ssh-bruteforce"}
        assert found(session, "flood") == {"udp flood"}
        assert found(session, '"Brute force"') == {"sshd: authentication failed"}
        assert labels("ssh") == ["Contains: ssh"]

    def test_an_address_matches_where_it_came_from_and_where_it_went(
        self, session: Session, events: object
    ) -> None:
        assert found(session, f"address:{DEVICE}") == {
            "sshd: authentication failed",
            "Blocked tcp",
            "udp flood",
        }
        assert found(session, ATTACKER) == {
            "sshd: authentication failed",
            "Blocked tcp",
            "Ban for ssh-bruteforce",
        }
        assert labels(f"ip:{ATTACKER}") == [f"Address: {ATTACKER}"]

    def test_an_address_can_be_a_range_or_either_version(
        self, session: Session, events: object
    ) -> None:
        assert found(session, "address:203.0.113.0/24") == {
            "sshd: authentication failed",
            "Blocked tcp",
            "Ban for ssh-bruteforce",
        }
        assert found(session, "address:2001:db8::/32") == {"udp flood"}
        assert found(session, f"address:{V6},{SCANNER}") == {"udp flood"}
        assert labels("address:203.0.113.0/24,10.0.0.1") == ["Address: 203.0.113.0/24, 10.0.0.1"]

    def test_from_and_to_are_the_two_ends(self, session: Session, events: object) -> None:
        assert found(session, f"src:{DEVICE}") == set()
        assert found(session, f"from:{ATTACKER}") == {
            "sshd: authentication failed",
            "Blocked tcp",
            "Ban for ssh-bruteforce",
        }
        assert found(session, f"dst:{DEVICE}") == {
            "sshd: authentication failed",
            "Blocked tcp",
            "udp flood",
        }
        assert found(session, "to:192.168.0.0/16") == {
            "sshd: authentication failed",
            "Blocked tcp",
            "udp flood",
        }
        assert labels(f"from:{ATTACKER} to:{DEVICE}") == [f"From: {ATTACKER}", f"To: {DEVICE}"]

    def test_a_turned_around_address_keeps_the_events_that_name_none(
        self, session: Session, events: object
    ) -> None:
        assert found(session, f"-address:{ATTACKER}") == {"DNS query volume", "udp flood"}
        assert labels(f"-address:{ATTACKER}") == [f"Not address: {ATTACKER}"]

    def test_ports_are_destination_or_source(self, session: Session, events: object) -> None:
        assert found(session, "port:22") == {"sshd: authentication failed"}
        assert found(session, "port:22,53") == {"sshd: authentication failed", "udp flood"}
        assert found(session, "dport:443") == {"Blocked tcp"}
        assert found(session, "sport:5353") == {"udp flood"}
        assert labels("port:22,53 sport:5353") == ["Port: 22, 53", "Source port: 5353"]

    @pytest.mark.parametrize("value", ["0", "65536", "ssh", "-1"])
    def test_a_port_is_a_number_from_1_to_65535(self, value: str) -> None:
        assert "isn't a port" in refused(f"port:{value}")

    def test_source_is_the_integration_by_key_or_name(
        self, session: Session, events: object
    ) -> None:
        assert found(session, "source:opnsense") == {"Blocked tcp", "udp flood"}
        assert found(session, "program:OPNsense,CrowdSec") == {
            "Blocked tcp",
            "udp flood",
            "Ban for ssh-bruteforce",
        }
        assert labels("source:wazuh,crowdsec") == ["Source: Wazuh, CrowdSec"]
        assert "No integration is called" in refused("source:nowhere")

    def test_connection_kind_and_protocol_are_matched_whole_in_lower_case(
        self, session: Session, events: object
    ) -> None:
        assert found(session, "connection:lapi") == {"Ban for ssh-bruteforce"}
        assert found(session, "conn:API") == {"Blocked tcp", "DNS query volume", "udp flood"}
        assert found(session, "kind:firewall") == {"Blocked tcp", "udp flood"}
        assert found(session, "kind:decision,alert") == {
            "Ban for ssh-bruteforce",
            "sshd: authentication failed",
            "DNS query volume",
        }
        assert found(session, "protocol:UDP") == {"udp flood"}
        assert found(session, "proto:tcp") == {"sshd: authentication failed", "Blocked tcp"}
        assert labels("kind:alert,Decision connection:API protocol:TCP") == [
            "Kind: alert, decision",
            "Connection: api",
            "Protocol: tcp",
        ]

    def test_a_word_named_twice_counts_once(self) -> None:
        assert labels("kind:Alert,alert,decision") == ["Kind: alert, decision"]

    def test_those_words_are_short(self) -> None:
        assert refused(f"kind:{'x' * 33}") == '"kind" takes at most 32 characters.'

    def test_severity_is_matched_or_compared(self, session: Session, events: object) -> None:
        assert found(session, "severity:high,critical") == {
            "sshd: authentication failed",
            "udp flood",
        }
        assert found(session, "severity>=medium") == {
            "sshd: authentication failed",
            "Ban for ssh-bruteforce",
            "udp flood",
        }
        assert found(session, "sev<low") == {"DNS query volume"}
        assert labels("severity>=medium") == ["Severity: at least medium"]

    def test_a_signature_is_part_of_the_rule_name(self, session: Session, events: object) -> None:
        assert found(session, "signature:brute") == {"sshd: authentication failed"}
        assert found(session, "sig:flood") == {"udp flood"}
        assert labels('sig:"ET DOS"') == ["Signature: ET DOS"]

    def test_a_turned_around_signature_keeps_the_events_that_have_none(
        self, session: Session, events: object
    ) -> None:
        assert found(session, "-signature:flood") == ALL - {"udp flood"}

    def test_raw_looks_through_the_programs_own_record(
        self, session: Session, events: object
    ) -> None:
        assert found(session, "raw:5710") == {"sshd: authentication failed"}
        assert found(session, "raw:nas") == {"sshd: authentication failed"}
        assert found(session, "-raw:nas") == ALL - {"sshd: authentication failed"}
        assert labels("raw:nas") == ["Record contains: nas"]

    def test_incident_says_whether_it_was_filed_into_one(
        self, session: Session, events: dict[str, Event]
    ) -> None:
        incident = Incident(
            subject=ATTACKER,
            title="Brute force on ssh",
            severity=3,
            confidence=80,
            status="open",
            first_seen_at=NOW,
            last_seen_at=NOW,
            signal_count=1,
            sources=["wazuh"],
            addresses=[],
            ports=[],
            activities=[],
            top_source="wazuh",
            top_summary="An alert",
            banned=False,
            verdict=None,
            waves=1,
        )
        session.add(incident)
        session.flush()
        filed = events["sshd: authentication failed"]
        session.add(
            IncidentSignal(
                incident_id=incident.id,
                event_id=filed.id,
                occurred_at=filed.occurred_at,
                source="wazuh",
                kind="alert",
                severity=3,
                summary="An alert",
            )
        )
        session.flush()

        assert found(session, "incident:yes") == {"sshd: authentication failed"}
        assert found(session, "incident:no") == ALL - {"sshd: authentication failed"}
        assert labels("incident:no") == ["In an incident: no"]
        assert "isn't yes or no" in refused("incident:maybe")

    def test_since_and_before_are_when_it_happened(self, session: Session, events: object) -> None:
        assert found(session, "since:30m") == {
            "sshd: authentication failed",
            "Blocked tcp",
            "Ban for ssh-bruteforce",
        }
        assert found(session, "before:1d") == {"udp flood"}
        assert found(session, "since:2026-10-27 before:2026-10-27T15:00") == {"DNS query volume"}
        assert labels("since:6h before:today") == ["Since: 6h ago", "Before: today"]

    def test_the_terms_all_have_to_be_true(self, session: Session, events: object) -> None:
        assert found(session, "source:opnsense severity>=high") == {"udp flood"}
        assert found(session, "source:opnsense ssh") == set()


class TestMistakes:
    def test_a_field_nobody_knows_is_said_with_the_one_that_was_meant(self) -> None:
        message = refused("sevrity:high")
        assert 'There\'s no search field called "sevrity".' in message
        assert 'Did you mean "severity"?' in message

    def test_a_name_people_reach_for_is_offered_as_what_it_means(self) -> None:
        assert 'Did you mean "port"?' in refused("dprt:22")

    def test_fields_that_are_not_amounts_are_not_compared(self) -> None:
        assert refused("kind>alert") == '"kind" is matched with "kind:", not ">".'

    def test_a_field_takes_a_few_choices(self) -> None:
        assert "takes at most 8 choices" in refused("port:1,2,3,4,5,6,7,8,9")

    def test_a_time_is_one_value(self) -> None:
        assert refused("since:1h,2h") == '"since:" takes one value, not a list.'
        assert "isn't a time" in refused("before:whenever")
