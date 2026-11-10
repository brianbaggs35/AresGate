"""What the programs reported besides the basics, boiled down for an incident to keep."""

from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.config import Settings
from app.incidents import evidence
from app.models import Event, IncidentSignal
from tests.test_incidents_engine import alert, run, signals, store

WAZUH: dict[str, Any] = {
    "rule": {
        "id": "5760",
        "level": 5,
        "firedtimes": 12,
        "groups": ["syslog", "sshd"],
        "pci_dss": ["10.2.4", "10.2.5", "10.2.6", "10.2.7"],
        "gdpr": ["IV_35.7.d"],
        "mitre": {"id": ["T1110"], "tactic": ["Credential Access"], "technique": ["Brute Force"]},
    },
    "agent": {"id": "001", "name": "web1", "ip": "192.168.1.20"},
    "decoder": {"name": "sshd"},
    "location": "/var/log/auth.log",
    "manager": {"name": "wazuh"},
    "full_log": "sshd: Failed password for root\t from 203.0.113.9",
    "data": {"srcuser": "root", "hostname": "scanner.example.net"},
    "GeoLocation": {"country_name": "Netherlands"},
}
SURICATA: dict[str, Any] = {
    "alert_sid": 2001219,
    "alert_gid": "1",
    "alert_rev": 20,
    "alert_action": "blocked",
    "alert_category": "Attempted Information Leak",
    "app_proto": "HTTP",
    "in_iface": "igc0",
    "direction": "to_server",
    "http": {"hostname": "example.com", "url": "/admin", "http_user_agent": "curl/8.0"},
    "dns.rrname": "bad.example.org",
    "tls": {"sni": "secure.example.com", "version": "TLS 1.3"},
    "flow": {
        "pkts_toserver": 14,
        "pkts_toclient": "9",
        "bytes_toserver": 2210.0,
        "bytes_toclient": 1320,
    },
    "flow_id": 123456,
}
NTOPNG: dict[str, Any] = {
    "alert_id": {"value": 12, "label": "Scan attacker"},
    "score": {"value": 100},
    "severity": {"value": 5, "label": "Error"},
    "l7_proto": {"value": 92, "label": "SSH"},
    "cli_name": {"value": "scanner.example.net"},
    "srv_name": {"value": "web1.lan"},
    "is_cli_attacker": True,
}
CROWDSEC = {
    "type": "ban",
    "scenario": "crowdsecurity/ssh-bf",
    "origin": "crowdsec",
    "duration": "3h59m12s",
    "scope": "Ip",
}


def said(source: str, raw: object) -> dict[str, Any]:
    found = evidence.extract(source, raw)
    assert found is not None
    return dict(found)


def facts(found: dict[str, Any]) -> dict[str, str]:
    return {label: value for label, value in found["facts"]}


class TestWazuh:
    def test_it_keeps_the_rule_the_machine_and_the_log_line(self) -> None:
        found = said("wazuh", WAZUH)

        assert facts(found) == {
            "Rule": "5760",
            "Level": "5",
            "Times it fired": "12",
            "Decoder": "sshd",
            "Log source": "/var/log/auth.log",
            "Manager": "wazuh",
        }
        assert found["host"] == "web1 (192.168.1.20)"
        # Control characters are taken out of what a program says.
        assert found["excerpt"] == "sshd: Failed password for root  from 203.0.113.9"

    def test_the_groups_and_what_the_rule_is_for_are_tags(self) -> None:
        found = said("wazuh", WAZUH)

        # Three requirements of a standard at most, so that one standard can't fill the tags.
        assert found["tags"] == [
            "syslog",
            "sshd",
            "pci_dss: 10.2.4",
            "pci_dss: 10.2.5",
            "pci_dss: 10.2.6",
            "gdpr: IV_35.7.d",
        ]

    def test_the_technique_comes_with_its_tactic(self) -> None:
        assert said("wazuh", WAZUH)["mitre"] == [
            {"id": "T1110", "tactic": "Credential Access", "technique": "Brute Force"}
        ]

    def test_techniques_and_tactics_that_do_not_pair_up_are_said_of_each(self) -> None:
        raw = {
            "rule": {
                "mitre": {
                    "id": ["T1110", "T1078"],
                    "tactic": ["Credential Access", "Persistence", "Defense Evasion"],
                    "technique": ["Brute Force"],
                }
            }
        }

        assert said("wazuh", raw)["mitre"] == [
            {
                "id": "T1110",
                "tactic": "Credential Access, Persistence, Defense Evasion",
                "technique": "Brute Force",
            },
            {
                "id": "T1078",
                "tactic": "Credential Access, Persistence, Defense Evasion",
                "technique": "Brute Force",
            },
        ]

    def test_what_it_names_is_kept_to_look_up(self) -> None:
        assert said("wazuh", WAZUH)["indicators"] == [
            {"kind": "user", "value": "root"},
            {"kind": "hostname", "value": "scanner.example.net"},
            {"kind": "country", "value": "Netherlands"},
        ]

    def test_a_machine_with_only_a_name_or_only_an_address_is_that(self) -> None:
        assert said("wazuh", {"agent": {"name": "web1"}})["host"] == "web1"
        assert said("wazuh", {"agent": {"ip": "192.168.1.20"}})["host"] == "192.168.1.20"

    def test_a_rule_with_a_mitre_section_that_is_not_one_has_no_techniques(self) -> None:
        assert said("wazuh", {"rule": {"id": 1, "mitre": "T1110"}})["mitre"] == []


class TestSuricata:
    def test_it_keeps_the_signature_what_was_done_and_the_traffic(self) -> None:
        found = said("opnsense", SURICATA)

        assert facts(found) == {
            "Signature": "2001219",
            "Generation": "1",
            "Revision": "20",
            "Action": "blocked",
            "Category": "Attempted Information Leak",
            "Direction": "to_server",
            "Interface": "igc0",
            "TLS version": "TLS 1.3",
            "Flow": "123456",
        }
        assert found["app"] == "http"
        assert found["tags"] == ["Attempted Information Leak"]
        assert found["traffic"] == {
            "packets_out": 14,
            "packets_in": 9,
            "bytes_out": 2210,
            "bytes_in": 1320,
        }

    def test_what_the_traffic_asked_for_is_found_however_the_member_is_written(self) -> None:
        assert said("opnsense", SURICATA)["indicators"] == [
            {"kind": "hostname", "value": "example.com"},
            {"kind": "url", "value": "/admin"},
            {"kind": "user_agent", "value": "curl/8.0"},
            {"kind": "dns", "value": "bad.example.org"},
            {"kind": "sni", "value": "secure.example.com"},
        ]

    def test_a_flat_member_with_a_dot_in_its_name_is_found_too(self) -> None:
        assert said("opnsense", {"http.hostname": "example.com"})["indicators"] == [
            {"kind": "hostname", "value": "example.com"}
        ]

    def test_only_the_volume_it_gave_is_kept(self) -> None:
        assert said("opnsense", {"flow": {"pkts_toserver": 3}, "alert_sid": 1})["traffic"] == {
            "packets_out": 3
        }


class TestNtopng:
    def test_it_keeps_the_score_the_type_and_the_application(self) -> None:
        found = said("ntopng", NTOPNG)

        assert facts(found) == {
            "Alert type": "Scan attacker",
            "Score": "100",
            "Severity": "Error",
            "Role": "The client is the attacker",
        }
        assert found["app"] == "ssh"
        assert found["tags"] == ["Scan attacker"]
        assert found["indicators"] == [
            {"kind": "hostname", "value": "scanner.example.net"},
            {"kind": "hostname", "value": "web1.lan"},
        ]

    @pytest.mark.parametrize(
        ("flag", "said_of_it"),
        [
            ("is_srv_attacker", "The server is the attacker"),
            ("is_cli_victim", "The client is the victim"),
            ("is_srv_victim", "The server is the victim"),
        ],
    )
    def test_it_says_which_end_was_which(self, flag: str, said_of_it: str) -> None:
        assert facts(said("ntopng", {flag: "1"}))["Role"] == said_of_it

    def test_the_role_of_a_host_is_kept_as_it_is_given(self) -> None:
        assert facts(said("ntopng", {"role": {"value": "attacker"}}))["Role"] == "attacker"


class TestCrowdSec:
    def test_it_keeps_the_scenario_and_where_the_decision_came_from(self) -> None:
        found = said("crowdsec", CROWDSEC)

        assert facts(found) == {
            "Remedy": "ban",
            "Scenario": "crowdsecurity/ssh-bf",
            "Origin": "crowdsec",
            "For": "3h59m12s",
            "Scope": "Ip",
        }
        assert found["tags"] == ["crowdsec"]


class TestWhatIsNotThere:
    @pytest.mark.parametrize("raw", [None, [], "text", 3, {}, {"other": 1}])
    def test_a_record_with_nothing_to_show_gives_nothing(self, raw: object) -> None:
        assert evidence.extract("wazuh", raw) is None

    def test_a_program_this_does_not_read_gives_nothing(self) -> None:
        assert evidence.extract("someone-else", WAZUH) is None

    @pytest.mark.parametrize("value", [True, ["a"], {"x": 1}, None, "-1", "1.5", -4, 2.5])
    def test_a_number_that_is_not_one_is_left_out(self, value: object) -> None:
        assert "traffic" not in (
            evidence.extract("opnsense", {"alert_sid": 1, "flow": {"pkts_toserver": value}}) or {}
        )

    def test_what_is_kept_is_cut_to_size(self) -> None:
        raw = {
            "rule": {"id": "x" * 500, "groups": [f"group-{n}" for n in range(40)]},
            "full_log": "y" * 5000,
            "data": {"srcuser": "u" * 500},
        }

        found = said("wazuh", raw)

        assert len(facts(found)["Rule"]) == evidence.MAX_VALUE
        assert len(found["tags"]) == evidence.MAX_TAGS
        assert len(found["excerpt"]) == evidence.MAX_EXCERPT
        assert len(found["indicators"][0]["value"]) == evidence.MAX_VALUE

    def test_no_more_facts_are_kept_than_there_is_room_for(self) -> None:
        raw = {"rule": {"id": 1, "level": 2, "firedtimes": 3}, **{"decoder": {"name": "d"}}}

        assert len(said("wazuh", raw)["facts"]) <= evidence.MAX_FACTS

    def test_the_same_thing_said_twice_is_kept_once(self) -> None:
        raw = {"data": {"srcuser": "root", "dstuser": "root"}}

        assert said("wazuh", raw)["indicators"] == [{"kind": "user", "value": "root"}]

    def test_a_value_that_is_a_list_of_things_that_are_not_words_is_left_out(self) -> None:
        assert said("wazuh", {"rule": {"id": 1, "groups": [{"a": 1}, True, "ok"]}})["tags"] == [
            "ok"
        ]

    def test_a_group_that_is_a_single_word_is_a_tag(self) -> None:
        assert said("wazuh", {"rule": {"groups": "syslog"}})["tags"] == ["syslog"]


class TestKeeping:
    def test_what_there_is_to_keep_is_a_plain_record(self) -> None:
        assert evidence.kept("crowdsec", CROWDSEC)["tags"] == ["crowdsec"]

    def test_where_there_is_none_it_is_an_empty_record_that_says_it_was_read(self) -> None:
        assert evidence.kept("wazuh", None) == {}

    def test_a_signal_loads_what_it_kept(self) -> None:
        kept = evidence.kept("wazuh", WAZUH)

        assert evidence.load(IncidentSignal(evidence=kept)) == kept

    @pytest.mark.parametrize("kept", [None, {}])
    def test_a_signal_with_none_has_none(self, kept: dict[str, Any] | None) -> None:
        assert evidence.load(IncidentSignal(evidence=kept)) is None


class TestFilingKeepsIt:
    def test_a_signal_keeps_what_its_program_said_and_which_alert_it_repeats(
        self, session: Session, settings: Settings
    ) -> None:
        first = alert(source="wazuh", n=1, raw=WAZUH)
        store(session, settings, first)
        store(
            session,
            settings,
            alert(
                first.occurred_at + timedelta(seconds=2),
                n=2,
                source="opnsense",
                connection="api",
                raw=SURICATA,
            ),
        )
        run(session)

        original, twin = signals(session)

        assert original.evidence == evidence.kept("wazuh", WAZUH)
        assert original.twin_of is None
        assert twin.evidence == evidence.kept("opnsense", SURICATA)
        assert twin.duplicate
        assert twin.twin_of == original.event_id


class TestReadingWhatWasNotKept:
    def pending(
        self, session: Session, settings: Settings
    ) -> tuple[IncidentSignal, IncidentSignal]:
        store(session, settings, alert(n=1, raw=WAZUH), alert(n=2, identity=("a2",), raw=None))
        run(session)
        one, two = signals(session)
        # As if they were filed before evidence was kept.
        one.evidence = two.evidence = None
        session.commit()
        return one, two

    def test_signals_filed_earlier_get_it_from_their_events(
        self, session: Session, settings: Settings
    ) -> None:
        one, two = self.pending(session, settings)

        assert evidence.read_pending(session) == 2
        session.commit()

        assert one.evidence == evidence.kept("wazuh", WAZUH)
        # An event that had nothing to show is read all the same, so it is not read again.
        assert two.evidence == {}
        assert evidence.read_pending(session) == 0

    def test_a_signal_whose_event_has_gone_is_read_as_having_none(
        self, session: Session, settings: Settings
    ) -> None:
        one, _ = self.pending(session, settings)
        session.query(Event).delete()
        session.commit()

        assert evidence.read_pending(session) == 2
        assert one.evidence == {}

    def test_only_a_batch_is_read_at_a_time(
        self, session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self.pending(session, settings)
        monkeypatch.setattr(evidence, "BATCH", 1)

        assert [evidence.read_pending(session) for _ in range(3)] == [1, 1, 0]
