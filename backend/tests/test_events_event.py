import math
from datetime import UTC, datetime, timedelta, timezone
from ipaddress import IPv4Address, IPv6Address
from typing import Any

import pytest

from app.events.event import MAX_RAW_BYTES, Severity, fingerprint
from tests.helpers import new_event

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)


def row(**changes: object) -> dict[str, Any]:
    return new_event(**changes).row(NOW)


class TestWhatAnEventNeeds:
    @pytest.mark.parametrize("field", ["source", "connection", "kind"])
    @pytest.mark.parametrize("value", ["", "Wazuh", "a b", "x" * 33, "-start"])
    def test_a_key_is_a_short_lowercase_name(self, field: str, value: str) -> None:
        with pytest.raises(ValueError, match=field):
            new_event(**{field: value})

    def test_the_time_needs_a_time_zone(self) -> None:
        with pytest.raises(ValueError, match="time zone"):
            new_event(occurred_at=datetime(2026, 10, 23, 12, 0))

    def test_it_needs_something_that_says_which_event_it_is(self) -> None:
        with pytest.raises(ValueError, match="which event"):
            new_event(identity=())

    def test_the_severities_run_from_info_to_critical(self) -> None:
        assert [item.name.lower() for item in Severity] == [
            "info",
            "low",
            "medium",
            "high",
            "critical",
        ]
        assert [int(item) for item in Severity] == [0, 1, 2, 3, 4]


class TestTheFingerprint:
    def test_the_same_event_has_the_same_one(self) -> None:
        assert new_event().fingerprint == new_event().fingerprint
        assert len(new_event().fingerprint) == 64

    def test_it_depends_on_the_source_and_on_each_part(self) -> None:
        assert fingerprint("wazuh", ("a", "b")) != fingerprint("ntopng", ("a", "b"))
        assert fingerprint("wazuh", ("a", "b")) != fingerprint("wazuh", ("a", "c"))
        assert fingerprint("wazuh", ("a", "b")) != fingerprint("wazuh", ("ab",))
        assert fingerprint("wazuh", ("1",)) != fingerprint("wazuh", (1,))

    def test_it_doesnt_depend_on_the_connection(self) -> None:
        # The same alert read through two of an integration's APIs is one event.
        one = new_event(connection="manager")
        other = new_event(connection="indexer")

        assert one.fingerprint == other.fingerprint

    def test_text_that_cant_be_encoded_still_has_one(self) -> None:
        assert len(new_event(identity=("\ud800 lone",)).fingerprint) == 64


class TestTheRow:
    def test_it_holds_every_column(self) -> None:
        occurred = NOW - timedelta(minutes=3)
        result = row(
            occurred_at=occurred,
            severity=Severity.HIGH,
            signature="ET SCAN Nmap",
            src_address="203.0.113.9",
            src_port=51514,
            dst_address="2001:db8::1",
            dst_port=22,
            protocol="TCP",
            raw={"rule": {"id": 5710}},
        )

        assert result == {
            "occurred_at": occurred,
            "received_at": NOW,
            "source": "wazuh",
            "connection": "indexer",
            "kind": "alert",
            "severity": 3,
            "summary": "sshd: authentication failed",
            "signature": "ET SCAN Nmap",
            "src_address": IPv4Address("203.0.113.9"),
            "src_port": 51514,
            "dst_address": IPv6Address("2001:db8::1"),
            "dst_port": 22,
            "protocol": "tcp",
            "fingerprint": new_event().fingerprint,
            "raw": {"rule": {"id": 5710}},
        }

    def test_what_isnt_given_is_left_empty(self) -> None:
        result = row()

        for column in ("signature", "src_address", "src_port", "dst_address", "dst_port"):
            assert result[column] is None
        assert result["protocol"] is None
        assert result["raw"] is None


class TestTextFromAProgram:
    def test_control_characters_become_spaces_and_it_is_cut_to_fit(self) -> None:
        result = row(summary="line one\nline two\x00" + "x" * 600, signature="a\tb" + "y" * 300)

        assert result["summary"].startswith("line one line two ")
        assert len(result["summary"]) == 500
        assert result["signature"].startswith("a b")
        assert len(result["signature"]) == 256

    def test_a_blank_summary_is_kept_blank(self) -> None:
        assert row(summary="  ")["summary"] == ""

    def test_text_that_isnt_valid_is_replaced(self) -> None:
        assert row(summary="bad \ud800 text")["summary"] == "bad ? text"

    def test_the_protocol_is_lowercase_and_short(self) -> None:
        assert row(protocol="ICMPv6")["protocol"] == "icmpv6"
        assert row(protocol="X" * 40)["protocol"] == "x" * 16
        assert row(protocol="  ")["protocol"] is None


class TestAddressesAndPorts:
    @pytest.mark.parametrize(
        ("given", "expected"),
        [
            ("192.168.1.5", IPv4Address("192.168.1.5")),
            (" 10.0.0.1 ", IPv4Address("10.0.0.1")),
            ("fe80::1%eth0", IPv6Address("fe80::1")),
            ("::ffff:192.0.2.1", IPv6Address("::ffff:192.0.2.1")),
        ],
    )
    def test_an_address_is_read(self, given: str, expected: IPv4Address | IPv6Address) -> None:
        assert row(src_address=given)["src_address"] == expected

    @pytest.mark.parametrize("given", ["unknown", "router.lan", "", "999.1.1.1", "10.0.0.0/8"])
    def test_what_isnt_an_address_is_left_out_without_losing_the_event(self, given: str) -> None:
        assert row(dst_address=given)["dst_address"] is None

    @pytest.mark.parametrize("given", [0, 1, 65535])
    def test_a_port_is_kept(self, given: int) -> None:
        assert row(src_port=given)["src_port"] == given

    @pytest.mark.parametrize("given", [-1, 65536, 10**9])
    def test_what_isnt_a_port_is_left_out(self, given: int) -> None:
        assert row(dst_port=given)["dst_port"] is None


class TestTheProgramsOwnRecord:
    def test_nested_json_is_kept(self) -> None:
        raw: dict[str, Any] = {"a": [1, 2.5, "x", None, True], "b": {"c": {"d": []}}}

        assert row(raw=raw)["raw"] == raw

    def test_what_the_database_would_refuse_is_taken_out(self) -> None:
        raw = {
            "nul": "a\x00b",
            "lone": "x\ud800y",
            "nan": math.nan,
            "inf": [math.inf, -math.inf],
            "key\x00": 1,
            5: "numeric key",
        }

        assert row(raw=raw)["raw"] == {
            "nul": "ab",
            "lone": "x?y",
            "nan": None,
            "inf": [None, None],
            "key": 1,
            "5": "numeric key",
        }

    def test_what_isnt_json_becomes_text(self) -> None:
        moment = datetime(2026, 10, 23, tzinfo=UTC)
        raw = {"when": moment, "tags": ("a", "b"), "set": {1}, "address": IPv4Address("10.0.0.1")}

        assert row(raw=raw)["raw"] == {
            "when": str(moment),
            "tags": ["a", "b"],
            "set": [1],
            "address": "10.0.0.1",
        }

    def test_a_record_that_is_too_large_is_replaced_by_its_size(self) -> None:
        raw = {"blob": "é" * MAX_RAW_BYTES}

        result = row(raw=raw)["raw"]

        assert result["truncated"] is True
        assert result["bytes"] > MAX_RAW_BYTES
        assert set(result) == {"truncated", "bytes"}

    def test_a_record_just_inside_the_limit_is_kept(self) -> None:
        raw = {"blob": "x" * (MAX_RAW_BYTES - 20)}

        assert row(raw=raw)["raw"] == raw


def test_an_event_in_another_time_zone_keeps_its_moment() -> None:
    zone = timezone(timedelta(hours=-3))
    moment = datetime(2026, 10, 23, 9, 0, tzinfo=zone)

    assert row(occurred_at=moment)["occurred_at"] == moment
