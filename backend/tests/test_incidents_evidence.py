"""What the programs reported besides the basics, boiled down for an incident to keep."""

import base64
from datetime import timedelta
from typing import Any, ClassVar

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


# A flow alert as ntopng's alert list gives it, with the addresses and names made up.
NTOPNG_FLOW: dict[str, Any] = {
    "msg": {
        "name": "Low Goodput Ratio",
        "description": "Low goodput ratio <b>[19.7%]</b> <a href='/x'>edit</a>",
    },
    "alert_id": {"label": "Low Goodput Ratio", "value": "12"},
    "cli_ip": {
        "ip": "192.168.7.57",
        "name": "workstation",
        "label": "workstation",
        "value": "192.168.7.57",
        "country": "",
        "location": "local",
        "blacklisted": "0",
    },
    "srv_ip": {
        "ip": "8.8.4.4",
        "name": "8.8.4.4",
        "value": "8.8.4.4",
        "country": "us",
        "location": "remote",
        "blacklisted": "1",
    },
    "cli_port": {"label": "56664", "value": "56664"},
    "srv_port": {"label": "domain", "value": "53"},
    "info": {"label": "example.com", "value": "example.com"},
    "proto": {"label": "TCP", "value": "6"},
    "score": {"label": "10", "value": 10},
    "duration": 61,
    "l7_proto": {"label": "TCP:DNS", "value": "5", "l4_label": "TCP", "l7_label": "DNS"},
    "severity": {"label": "<i class='fas fa-info-circle'></i> ", "value": 3},
    "mitre_data": {
        "mitre_id": "T1071",
        "mitre_tactic": "command-and-control",
        "mitre_tactic_i18n": "Command and Control",
        "mitre_technique": "app-layer",
        "mitre_technique_i18n": "Application Layer Protocol",
        "mitre_subtechnique_i18n": "DNS",
    },
    "cli_network": {"label": "192.168.7.0/24", "value": "4"},
    "srv_network": {"label": "", "value": ""},
    "vlan_id": {"label": "", "value": 20},
    "cli_host_pool_id": {"label": "Cameras", "value": "3"},
    "total_bytes": {"bytes_rcvd": 722, "bytes_sent": 399, "total_bytes": 1121, "total_packets": 16},
    "community_id": {"name": "1:abc=", "value": "1:abc="},
    "alert_category": {"icon": "x", "label": "Network", "value": "3"},
    "description": {"descr": "Low goodput ratio [19.7%]"},
}


class TestNtopngFlow:
    def test_it_says_who_the_flow_was_between_and_what_it_was(self) -> None:
        found = said("ntopng", NTOPNG_FLOW)

        assert found["flow"] == {
            "client": {
                "address": "192.168.7.57",
                "name": "workstation",
                "port": 56664,
                "location": "local",
                "blacklisted": False,
            },
            "server": {
                "address": "8.8.4.4",
                "port": 53,
                "service": "domain",
                "country": "US",
                "location": "remote",
                "blacklisted": True,
            },
            "protocol": "tcp",
            "duration": 61,
        }
        assert found["app"] == "dns"
        assert found["score"] == 10
        assert found["traffic"] == {"bytes_out": 399, "bytes_in": 722}

    def test_it_says_what_it_made_of_it_in_plain_words(self) -> None:
        found = said("ntopng", NTOPNG_FLOW)

        assert found["summary"] == "Low goodput ratio [19.7%]"
        assert facts(found) == {
            "Alert type": "Low Goodput Ratio",
            "Score": "10",
            "Severity": "Notice",
            "Category": "Network",
            "Packets": "16",
            "Client network": "192.168.7.0/24",
            "VLAN": "20",
            "Host pool": "Cameras",
        }
        assert found["mitre"] == [
            {
                "id": "T1071",
                "tactic": "Command and Control",
                "technique": "Application Layer Protocol: DNS",
            }
        ]

    def test_what_the_traffic_asked_for_is_named_for_the_kind_of_traffic_it_was(self) -> None:
        found = said("ntopng", NTOPNG_FLOW)

        assert {"kind": "dns", "value": "example.com"} in found["indicators"]
        assert {"kind": "community_id", "value": "1:abc="} in found["indicators"]
        for app, kind in (("TLS", "sni"), ("HTTP", "hostname"), ("Telegram", "info")):
            raw = {**NTOPNG_FLOW, "l7_proto": {"label": f"TCP:{app}"}}
            assert {"kind": kind, "value": "example.com"} in said("ntopng", raw)["indicators"]

    def test_the_description_is_the_plain_one_when_it_is_the_only_one_given(self) -> None:
        raw = {"msg": {"description": "<p>Low   goodput\n ratio</p> &amp; more"}}

        assert said("ntopng", raw)["summary"] == "Low goodput ratio & more"
        assert said("ntopng", {"description": "Plain words"})["summary"] == "Plain words"

    def test_the_default_pool_and_no_vlan_are_not_facts(self) -> None:
        raw = {
            "alert_id": {"label": "Scan"},
            "cli_host_pool_id": {"label": "Default"},
            "vlan_id": {"label": "", "value": 0},
        }

        assert facts(said("ntopng", raw)) == {"Alert type": "Scan"}

    @pytest.mark.parametrize(
        ("level", "name"),
        [(0, "None"), (2, "Info"), (4, "Warning"), (5, "Error"), (6, "Critical"), (8, "Emergency")],
    )
    def test_severity_is_said_in_words_not_in_the_html_ntopng_gives_for_its_page(
        self, level: int, name: str
    ) -> None:
        raw = {"severity": {"label": "<i></i>", "value": level}}

        assert facts(said("ntopng", raw)) == {"Severity": name}

    def test_a_severity_it_has_no_word_for_is_left_out(self) -> None:
        raw = {"score": {"value": 3}, "severity": {"value": 7}}

        assert "Severity" not in facts(said("ntopng", raw))

    def test_the_app_is_a_plain_member_in_a_version_that_gives_it_so(self) -> None:
        assert said("ntopng", {"l7_proto": "SSH", "score": 1})["app"] == "ssh"
        assert said("ntopng", {"l7_proto": {"label": "SSH"}, "score": 1})["app"] == "ssh"

    def test_a_technique_with_nothing_to_say_is_none(self) -> None:
        raw = {"score": 1, "mitre_data": {"mitre_id": "", "mitre_tactic": "x"}}

        assert said("ntopng", raw)["mitre"] == []
        assert said("ntopng", {"score": 1, "mitre_data": "x"})["mitre"] == []

    def test_a_technique_without_a_subtechnique_is_just_the_technique(self) -> None:
        raw = {"mitre_data": {"mitre_id": "T1046", "mitre_technique": "Network Scanning"}}

        assert said("ntopng", raw)["mitre"] == [
            {"id": "T1046", "tactic": "", "technique": "Network Scanning"}
        ]

    def test_the_flow_may_be_given_inside_a_member_of_its_own(self) -> None:
        raw = {"flow": {"cli_ip": {"ip": "10.0.0.5"}, "srv_port": {"label": "https", "value": 443}}}

        assert said("ntopng", raw)["flow"] == {
            "client": {"address": "10.0.0.5"},
            "server": {"port": 443, "service": "https"},
        }


class TestSuricataDetail:
    RULE: ClassVar[dict[str, Any]] = {
        "alert_severity": 2,
        "alert": {
            "metadata": {
                "signature_severity": ["Major"],
                "confidence": ["High"],
                "affected_product": ["Linux"],
                "attack_target": ["Server"],
                "deployment": ["Perimeter"],
                "mitre_technique_id": ["T1190"],
                "mitre_technique_name": ["Exploit Public-Facing Application"],
                "mitre_tactic_name": ["Initial Access"],
            }
        },
        "http": {
            "http_content_type": "text/html",
            "length": 512,
            "redirect": "https://example.com/login",
        },
        "dns": {"rcode": "NXDOMAIN"},
        "tls": {
            "subject": "CN=example.com",
            "issuerdn": "CN=Example CA",
            "ja3": {"hash": "e7d705a3286e19ea42f587b344ee6865"},
        },
        "payload_printable": "GET /admin HTTP/1.1\r\nHost: example.com\x00",
    }

    def test_it_says_what_the_rule_says_of_itself(self) -> None:
        found = said("opnsense", self.RULE)

        assert facts(found) == {
            "Priority": "Medium",
            "Rule severity": "Major",
            "Rule confidence": "High",
            "Affected product": "Linux",
            "Target": "Server",
            "Deployment": "Perimeter",
            "HTTP content type": "text/html",
            "HTTP response size": "512",
            "Redirected to": "https://example.com/login",
            "DNS answer": "NXDOMAIN",
            "Certificate for": "CN=example.com",
            "Certificate issued by": "CN=Example CA",
            "TLS client fingerprint": "e7d705a3286e19ea42f587b344ee6865",
        }
        assert found["mitre"] == [
            {
                "id": "T1190",
                "tactic": "Initial Access",
                "technique": "Exploit Public-Facing Application",
            }
        ]

    def test_it_keeps_what_was_sent_when_the_firewall_kept_the_packet(self) -> None:
        assert said("opnsense", self.RULE)["payload"] == "GET /admin HTTP/1.1  Host: example.com"

    def test_a_rule_that_names_no_technique_matches_none(self) -> None:
        raw = {"alert_gid": 1, "alert": {"metadata": {"signature_severity": ["Minor"]}}}

        assert said("opnsense", raw)["mitre"] == []

    def test_the_metadata_may_be_flattened_and_a_priority_it_does_not_know_is_left_out(
        self,
    ) -> None:
        raw = {"alert_metadata": {"deployment": "Internal"}, "alert_severity": 9}

        assert facts(said("opnsense", raw)) == {"Deployment": "Internal"}


class TestWazuhDetail:
    def test_it_says_what_the_log_names_and_what_the_vulnerability_detector_found(self) -> None:
        raw = {
            "rule": {"id": "23504", "level": 7},
            "data": {
                "srcip": "203.0.113.9",
                "srcport": "40000",
                "dstport": "22",
                "protocol": "tcp",
                "command": "/bin/sh",
                "win": {"system": {"eventID": "4625"}},
                "vulnerability": {
                    "cve": "CVE-2026-0001",
                    "title": "Buffer overflow in example",
                    "severity": "High",
                    "status": "Active",
                    "package": {"name": "example", "version": "1.2"},
                },
            },
        }

        found = said("wazuh", raw)

        assert facts(found) == {
            "Rule": "23504",
            "Level": "7",
            "Address in the log": "203.0.113.9",
            "Port in the log": "40000",
            "Destination port": "22",
            "Protocol": "tcp",
            "Command": "/bin/sh",
            "Windows event": "4625",
            "Vulnerability": "Buffer overflow in example",
            "Vulnerability severity": "High",
            "Package": "example",
            "Package version": "1.2",
            "Fix": "Active",
        }
        assert found["indicators"] == [{"kind": "cve", "value": "CVE-2026-0001"}]


class TestThePacketDump:
    def packet(self, data: bytes) -> dict[str, object]:
        return {
            "alert_sid": 1,
            "alert": {"signature": "x"},
            "payload": base64.b64encode(data).decode(),
        }

    def test_the_first_bytes_are_laid_out_as_a_dump(self) -> None:
        found = said("opnsense", self.packet(b"GET /admin HTTP/1.1\r\nHost: a\x00"))

        assert found["dump"] == [
            [
                "0000",
                "47 45 54 20 2f 61 64 6d 69 6e 20 48 54 54 50 2f",
                "GET /admin HTTP/",
            ],
            ["0010", "31 2e 31 0d 0a 48 6f 73 74 3a 20 61 00", "1.1..Host: a."],
        ]

    def test_no_more_than_the_first_128_bytes_are_kept(self) -> None:
        found = said("opnsense", self.packet(bytes(range(256))))

        assert len(found["dump"]) == evidence.MAX_DUMP // 16
        assert found["dump"][-1][0] == "0070"

    def test_data_that_is_not_base64_is_left_out(self) -> None:
        raw = {"alert_sid": 1, "alert": {"signature": "x"}, "payload": "not base64 !!"}

        assert "dump" not in (evidence.extract("opnsense", raw) or {})

    def test_no_data_is_no_dump(self) -> None:
        assert "dump" not in (evidence.extract("opnsense", self.packet(b"")) or {})
