"""What the programs, between them, knew of an incident."""

from datetime import UTC, datetime, timedelta
from typing import Any

from app.incidents import evidence, insights, occurrences
from app.models import IncidentSignal

NOW = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
TECHNIQUE = {"id": "T1110", "tactic": "Credential Access", "technique": "Brute Force"}


def said(**changes: Any) -> dict[str, Any]:
    return {"facts": [], "tags": [], "mitre": [], "indicators": [], **changes}


def signal(minutes: int, source: str = "wazuh", **changes: Any) -> IncidentSignal:
    fields: dict[str, Any] = {
        "occurred_at": NOW + timedelta(minutes=minutes),
        "event_id": minutes + 1,
        "source": source,
        "kind": "alert",
        "severity": 2,
        "summary": f"{source} saw it",
        "signature": "ET SCAN",
        "src_address": None,
        "dst_address": None,
        "protocol": None,
        "dst_port": None,
        "verdict": None,
        "duplicate": False,
        "twin_of": None,
        "evidence": None,
        **changes,
    }
    return IncidentSignal(**fields)


def test_what_is_said_of_an_alert_that_happened_often_counts_that_often() -> None:
    found = insights.of(
        occurrences.group(
            [
                signal(0, evidence=said(mitre=[TECHNIQUE], tags=["sshd"], host="web1", app="ssh")),
                signal(1, evidence=said(mitre=[TECHNIQUE], tags=["sshd"], host="web1", app="ssh")),
                signal(2, signature="Other", evidence=said(tags=["sshd", "syslog"])),
            ]
        )
    )

    assert [(each.id, each.tactic, each.name, each.count) for each in found.techniques] == [
        ("T1110", "Credential Access", "Brute Force", 2)
    ]
    assert [(each.value, each.count) for each in found.tags] == [("sshd", 3), ("syslog", 1)]
    assert [(each.value, each.count) for each in found.hosts] == [("web1", 2)]
    assert [(each.value, each.count) for each in found.apps] == [("ssh", 2)]
    assert not found.empty


def test_what_two_programs_both_said_of_one_alert_is_said_once() -> None:
    first = signal(0, evidence=said(tags=["scan"], mitre=[TECHNIQUE]))
    twin = signal(
        0,
        source="opnsense",
        event_id=50,
        duplicate=True,
        twin_of=first.event_id,
        evidence=said(
            tags=["scan", "recon"],
            mitre=[TECHNIQUE],
            indicators=[{"kind": "hostname", "value": "example.com"}],
        ),
    )

    found = insights.of(occurrences.group([first, twin]))

    assert [(each.value, each.count) for each in found.tags] == [("recon", 1), ("scan", 1)]
    assert [each.count for each in found.techniques] == [1]
    assert [(each.kind, each.value, each.count) for each in found.named] == [
        ("hostname", "example.com", 1)
    ]


def test_each_program_is_listed_with_what_it_added_and_how_often_it_reported() -> None:
    first = signal(
        0,
        evidence=said(
            facts=[["Rule", "1"]], mitre=[TECHNIQUE], host="web1", excerpt="line", tags=["x"]
        ),
    )
    twin = signal(
        0,
        source="opnsense",
        event_id=50,
        duplicate=True,
        twin_of=first.event_id,
        evidence=said(app="ssh", indicators=[{"kind": "dns", "value": "a.example"}]),
    )
    plain = signal(5, source="ntopng", signature="Other")

    found = insights.of(occurrences.group([first, twin, plain]))

    assert [(each.source, each.reports) for each in found.programs] == [
        ("ntopng", 1),
        ("opnsense", 1),
        ("wazuh", 1),
    ]
    by_source = {each.source: each for each in found.programs}
    assert by_source["wazuh"].adds == [
        "MITRE ATT&CK techniques",
        "Rule groups and categories",
        "The machine it was about",
        "The log line",
        "The rule's details",
    ]
    assert by_source["opnsense"].adds == ["The application", "Hosts, URLs and users it named"]
    # A program that said no more than the basics is listed, as one that did.
    assert by_source["ntopng"].adds == []


def test_the_commonest_come_first_and_only_so_many_are_kept() -> None:
    many = [
        signal(n, signature=f"rule {n}", evidence=said(tags=[f"tag-{n:02d}", "common"]))
        for n in range(insights.LIMIT + 5)
    ]

    found = insights.of(occurrences.group(many))

    assert len(found.tags) == insights.LIMIT
    assert found.tags[0].value == "common"


def test_nothing_said_beyond_the_basics_is_empty() -> None:
    found = insights.of(occurrences.group([signal(0), signal(1, source="ntopng")]))

    assert found.empty
    assert insights.of([]).empty


def test_an_evidence_record_missing_members_is_read_all_the_same() -> None:
    kept = {"tags": ["only-tags"]}
    found = insights.of(occurrences.group([signal(0, evidence=kept)]))

    assert [each.value for each in found.tags] == ["only-tags"]
    assert evidence.load(signal(0, evidence=kept)) is not None
