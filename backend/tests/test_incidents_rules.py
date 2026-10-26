import pytest

from app.events.event import Severity
from app.incidents import rules
from app.incidents.rules import Facts


def facts(**changes: object) -> Facts:
    fields: dict[str, object] = {
        "subject": "93.184.216.34",
        "severity": Severity.MEDIUM,
        "top_source": "wazuh",
        "top_summary": "sshd: authentication failed",
        "sources": ["wazuh"],
        "signal_count": 1,
        "banned": False,
        "others": 1,
        **changes,
    }
    return Facts(**fields)  # type: ignore[arg-type]


def points(assessment: rules.Assessment) -> dict[str, int]:
    return {reason.rule: reason.points for reason in assessment.reasons}


class TestWhatTheStrongestSignalIsWorth:
    @pytest.mark.parametrize(
        ("severity", "confidence"),
        [
            (Severity.INFO, 0),
            (Severity.LOW, 10),
            (Severity.MEDIUM, 25),
            (Severity.HIGH, 40),
            (Severity.CRITICAL, 55),
        ],
    )
    def test_a_lone_signal_is_as_sure_as_it_is_serious(
        self, severity: Severity, confidence: int
    ) -> None:
        assessment = rules.assess(facts(severity=severity))

        assert assessment.confidence == confidence
        assert [reason.rule for reason in assessment.reasons] == ["strongest"]

    def test_it_says_who_rated_it_and_what_it_said(self) -> None:
        reason = rules.assess(facts(severity=Severity.HIGH, top_source="opnsense")).reasons[0]

        assert reason.text == (
            "The most serious signal is rated high by OPNsense: sshd: authentication failed"
        )


class TestMoreThanOneProgram:
    def test_each_program_that_agrees_adds_to_it(self) -> None:
        two = rules.assess(facts(sources=["opnsense", "wazuh"]))
        three = rules.assess(facts(sources=["crowdsec", "opnsense", "wazuh"]))

        assert points(two)["corroborated"] == 15
        assert points(three)["corroborated"] == 30
        reason = next(item for item in three.reasons if item.rule == "corroborated")
        assert reason.text == "3 programs saw it: CrowdSec, OPNsense and Wazuh."

    def test_two_programs_are_named_with_and(self) -> None:
        reason = rules.assess(facts(sources=["opnsense", "wazuh"])).reasons[1]

        assert reason.text == "2 programs saw it: OPNsense and Wazuh."

    def test_a_fourth_adds_nothing_more(self) -> None:
        assessment = rules.assess(facts(sources=["crowdsec", "ntopng", "opnsense", "wazuh"]))

        assert points(assessment)["corroborated"] == 30

    def test_one_program_is_not_corroboration(self) -> None:
        assert "corroborated" not in points(rules.assess(facts()))


class TestRepetition:
    @pytest.mark.parametrize(
        ("count", "expected"), [(1, None), (4, None), (5, 10), (19, 10), (20, 20), (500, 20)]
    )
    def test_the_more_often_the_surer(self, count: int, expected: int | None) -> None:
        assessment = rules.assess(facts(signal_count=count))

        assert points(assessment).get("repeated") == expected

    def test_it_says_how_often(self) -> None:
        reason = rules.assess(facts(signal_count=7)).reasons[1]

        assert reason.text == "It has set off 7 signals."


def test_a_ban_is_a_decision_that_it_was_an_attack() -> None:
    assessment = rules.assess(facts(banned=True))

    assert points(assessment)["banned"] == 20
    assert "banned" not in points(rules.assess(facts()))


def test_reaching_several_addresses_counts_for_something() -> None:
    assert "spread" not in points(rules.assess(facts(others=2)))
    spread = rules.assess(facts(others=3))

    assert points(spread)["spread"] == 10
    assert spread.reasons[-1].text == "3 other addresses are involved."


def test_confidence_is_the_sum_of_the_reasons_and_never_more_than_100() -> None:
    plain = rules.assess(facts(severity=Severity.HIGH, sources=["opnsense", "wazuh"]))
    everything = rules.assess(
        facts(
            severity=Severity.CRITICAL,
            sources=["crowdsec", "opnsense", "wazuh"],
            signal_count=50,
            banned=True,
            others=9,
        )
    )

    assert plain.confidence == 40 + 15
    assert sum(reason.points for reason in everything.reasons) == 55 + 30 + 20 + 20 + 10
    assert everything.confidence == 100


def test_the_reasons_go_to_json_as_they_are_stored() -> None:
    assessment = rules.assess(facts(severity=Severity.LOW))

    assert assessment.as_json() == [
        {
            "rule": "strongest",
            "points": 10,
            "text": "The most serious signal is rated low by Wazuh: sshd: authentication failed",
        }
    ]


@pytest.mark.parametrize(
    ("confidence", "level"),
    [(0, "low"), (34, "low"), (35, "medium"), (64, "medium"), (65, "high"), (100, "high")],
)
def test_a_confidence_is_low_medium_or_high(confidence: int, level: str) -> None:
    assert rules.level_of(confidence) == level


def test_an_integration_this_version_doesnt_know_is_called_by_its_key() -> None:
    assert rules.name_of("wazuh") == "Wazuh"
    assert rules.name_of("zeek") == "zeek"


class TestTitles:
    def test_an_incident_is_called_what_its_signal_said_and_who_it_is_about(self) -> None:
        assert rules.title_of(facts(top_summary="ET SCAN Potential SSH Scan")) == (
            "ET SCAN Potential SSH Scan (93.184.216.34)"
        )

    def test_the_subject_is_not_said_twice(self) -> None:
        said = "tcp 93.184.216.34:51514 to 192.168.1.20:22"

        assert rules.title_of(facts(top_summary=said)) == said

    def test_an_incident_about_a_rule_is_called_what_the_rule_said(self) -> None:
        title = rules.title_of(facts(subject="rule:wazuh:sshd", top_summary="sshd: failed"))

        assert title == "sshd: failed"

    def test_a_long_title_is_cut(self) -> None:
        title = rules.title_of(facts(top_summary="x" * 400))

        assert len(title) == rules.MAX_TITLE
        assert title.endswith("…")
