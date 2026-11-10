"""Repeats: the same thing said again is one thing that happened many times."""

from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from typing import Any

import pytest

from app.incidents import occurrences
from app.models import IncidentSignal

NOW = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)


def signal(minutes: int = 0, **changes: Any) -> IncidentSignal:
    fields: dict[str, Any] = {
        "occurred_at": NOW + timedelta(minutes=minutes),
        "source": "opnsense",
        "kind": "alert",
        "severity": 2,
        "summary": "ET SCAN Potential SSH Scan: tcp",
        "signature": "ET SCAN Potential SSH Scan",
        "src_address": ip_address("203.0.113.9"),
        "src_port": 40000 + minutes,
        "dst_address": ip_address("192.168.1.20"),
        "dst_port": 22,
        "protocol": "tcp",
        "verdict": None,
        "duplicate": False,
    }
    fields.update(changes)
    return IncidentSignal(**fields)


def test_the_same_thing_again_and_again_is_one_that_happened_many_times() -> None:
    found = occurrences.group([signal(0), signal(5, src_port=1), signal(9, src_port=2)])

    assert len(found) == 1
    assert found[0].first.occurred_at == NOW
    assert found[0].count == 3
    assert found[0].last_at == NOW + timedelta(minutes=9)


def test_it_does_not_matter_which_source_port_each_connection_used() -> None:
    assert occurrences.key_of(signal(0, src_port=1)) == occurrences.key_of(signal(0, src_port=2))


@pytest.mark.parametrize(
    "changes",
    [
        {"source": "wazuh"},
        {"kind": "decision"},
        {"severity": 3},
        {"signature": "ET SCAN Nmap"},
        {"src_address": ip_address("203.0.113.10")},
        {"dst_address": ip_address("192.168.1.21")},
        {"dst_port": 80},
        {"protocol": "udp"},
        {"verdict": "low_priority"},
    ],
)
def test_anything_that_differs_makes_another_occurrence(changes: dict[str, Any]) -> None:
    found = occurrences.group([signal(0), signal(1, **changes)])

    assert [each.count for each in found] == [1, 1]


def test_a_signal_without_a_signature_is_told_apart_by_what_it_says() -> None:
    found = occurrences.group(
        [
            signal(0, signature=None, summary="Blocked tcp 203.0.113.9"),
            signal(1, signature=None, summary="Blocked tcp 203.0.113.9"),
            signal(2, signature=None, summary="Blocked udp 203.0.113.9"),
        ]
    )

    assert [each.count for each in found] == [2, 1]


def test_they_are_in_the_order_each_first_happened() -> None:
    found = occurrences.group([signal(0, dst_port=80), signal(1), signal(2, dst_port=80)])

    assert [(each.first.dst_port, each.count) for each in found] == [(80, 2), (22, 1)]


def test_how_many_another_program_also_reported_is_counted() -> None:
    found = occurrences.group([signal(0), signal(1, duplicate=True), signal(2, duplicate=True)])

    assert (found[0].count, found[0].duplicates) == (3, 2)


class TestAnotherProgramReportingTheSame:
    """The same alert from a program that did not report the first is not an occurrence of its own:
    it confirms the first."""

    def twin(self, minutes: int = 0, of: int = 1, **changes: Any) -> IncidentSignal:
        fields: dict[str, Any] = {
            "source": "wazuh",
            "duplicate": True,
            "twin_of": of,
            "event_id": 100 + minutes,
            "signature": "Wazuh says ssh",
            **changes,
        }
        return signal(minutes, **fields)

    def test_it_is_added_to_the_alert_it_repeats_as_a_confirmation(self) -> None:
        found = occurrences.group([signal(0, event_id=1), signal(5, event_id=2), self.twin(0)])

        (only,) = found
        assert (only.count, only.duplicates) == (2, 1)
        assert [(one.source, one.count) for one in only.confirmations] == [("wazuh", 1)]

    def test_each_program_that_agrees_is_listed_once_with_how_often_it_did(self) -> None:
        found = occurrences.group(
            [
                signal(0, event_id=1),
                self.twin(
                    1,
                    severity=1,
                    evidence={"facts": [["Rule", "1"]], "tags": [], "mitre": [], "indicators": []},
                ),
                self.twin(2, severity=3),
                self.twin(3, source="ntopng", signature="Scan"),
            ]
        )

        (only,) = found
        assert only.duplicates == 3
        wazuh, ntopng = only.confirmations
        assert (wazuh.source, wazuh.count, wazuh.severity) == ("wazuh", 2, 3)
        assert (wazuh.first_at, wazuh.last_at) == (
            NOW + timedelta(minutes=1),
            NOW + timedelta(minutes=2),
        )
        # What the first of its reports that said any said.
        assert wazuh.evidence == {
            "facts": [["Rule", "1"]],
            "tags": [],
            "mitre": [],
            "indicators": [],
        }
        assert (ntopng.source, ntopng.signature, ntopng.evidence) == ("ntopng", "Scan", None)

    def test_a_program_that_says_it_in_other_words_is_listed_apart(self) -> None:
        found = occurrences.group(
            [signal(0, event_id=1), self.twin(1), self.twin(2, signature="Another rule")]
        )

        assert [one.signature for one in found[0].confirmations] == [
            "Wazuh says ssh",
            "Another rule",
        ]

    def test_a_twin_may_have_been_dated_before_the_alert_it_repeats(self) -> None:
        found = occurrences.group([self.twin(0), signal(1, event_id=1)])

        assert len(found) == 1
        assert found[0].first.event_id == 1
        assert found[0].duplicates == 1

    def test_one_whose_original_is_not_listed_is_an_occurrence_of_its_own(self) -> None:
        found = occurrences.group([signal(0, event_id=1), self.twin(1, of=999)])

        assert [(each.first.source, each.duplicates) for each in found] == [
            ("opnsense", 0),
            ("wazuh", 1),
        ]
        assert all(not each.confirmations for each in found)


def test_a_timeline_that_is_out_of_order_still_has_the_latest_time_last() -> None:
    found = occurrences.group([signal(9), signal(0)])

    assert found[0].last_at == NOW + timedelta(minutes=9)


def test_nothing_is_no_occurrences() -> None:
    assert occurrences.group([]) == []
