"""What a destination is told about: the rules, the one function that decides, quiet hours and the
preview of the last day."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any, get_args
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.orm import Session

from app.alerts import rules as alert_rules
from app.alerts.rules import Quiet, Rules
from app.models import AlertDestination, Incident
from app.threats.settings import Tuning

# A Monday noon in UTC, which is 13:00 in Berlin (winter time) and 07:00 in New York.
NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
HOUR = timedelta(hours=1)


def rules(**changes: Any) -> Rules:
    """The rules of a new destination (serious and sure, nothing else chosen), with changes."""
    return replace(
        Rules(
            min_severity=2,
            min_confidence=65,
            sources=(),
            activities=(),
            quiet=None,
            max_per_hour=6,
            detail="standard",
            again_when_worse=True,
        ),
        **changes,
    )


def incident(session: Session | None = None, **changes: Any) -> Incident:
    fields: dict[str, Any] = {
        "subject": "203.0.113.5",
        "severity": 3,
        "confidence": 70,
        "status": "open",
        "first_seen_at": NOW - 2 * HOUR,
        "last_seen_at": NOW - HOUR,
        "signal_count": 3,
        "sources": ["opnsense", "wazuh"],
        "addresses": [],
        "ports": [],
        "activities": ["scan"],
        "top_source": "wazuh",
        "top_summary": "An alert",
        "banned": False,
        "verdict": None,
        "waves": 1,
    }
    fields.update(changes)
    fields.setdefault("title", f"Scan from {fields['subject']}")
    found = Incident(**fields)
    if session is not None:
        session.add(found)
        session.flush()
    return found


def destination(session: Session, **changes: Any) -> AlertDestination:
    fields: dict[str, Any] = {"kind": "discord", "name": "Security", "hint": "…6789", **changes}
    row = AlertDestination(**fields)
    session.add(row)
    session.flush()
    session.refresh(row)
    return row


class TestTheRulesOfADestination:
    def test_a_new_destination_is_told_only_of_what_is_serious_and_sure(
        self, session: Session
    ) -> None:
        row = destination(session)

        assert alert_rules.of(row) == rules()

    def test_quiet_hours_are_there_only_when_they_are_on(self, session: Session) -> None:
        off = destination(session, quiet_hours=False)
        on = destination(
            session,
            name="Phone",
            quiet_hours=True,
            quiet_from=23 * 60,
            quiet_until=6 * 60 + 30,
            time_zone="Europe/Berlin",
            quiet_critical=False,
        )

        assert alert_rules.of(off).quiet is None
        assert alert_rules.of(on).quiet == Quiet(23 * 60, 390, "Europe/Berlin", False)

    def test_what_was_chosen_is_kept(self, session: Session) -> None:
        row = destination(
            session,
            min_severity=3,
            min_confidence=35,
            sources=["wazuh"],
            activities=["scan", "brute_force"],
            max_per_hour=2,
            detail="brief",
            again_when_worse=False,
        )

        assert alert_rules.of(row) == rules(
            min_severity=3,
            min_confidence=35,
            sources=("wazuh",),
            activities=("scan", "brute_force"),
            max_per_hour=2,
            detail="brief",
            again_when_worse=False,
        )


class TestDeciding:
    def test_a_serious_incident_that_it_is_sure_of_is_sent(self) -> None:
        assert alert_rules.decide(rules(), incident(), NOW) == alert_rules.Decision(True)

    @pytest.mark.parametrize("verdict", ["not_suspicious", "low_priority"])
    def test_what_the_owner_called_harmless_is_never_sent(self, verdict: str) -> None:
        # Not even for rules that ask for everything.
        everything = rules(min_severity=1, min_confidence=0)

        decision = alert_rules.decide(everything, incident(verdict=verdict, confidence=100), NOW)

        assert decision == alert_rules.Decision(False, "muted")

    @pytest.mark.parametrize("status", ["resolved", "dismissed"])
    def test_what_is_settled_is_never_sent(self, status: str) -> None:
        decision = alert_rules.decide(rules(), incident(status=status), NOW)

        assert decision == alert_rules.Decision(False, "settled")

    def test_the_owners_word_on_a_signal_comes_before_whether_it_is_settled(self) -> None:
        decision = alert_rules.decide(
            rules(), incident(verdict="low_priority", status="resolved"), NOW
        )

        assert decision.reason == "muted"

    @pytest.mark.parametrize("status", ["open", "investigating"])
    def test_what_is_open_or_being_looked_at_can_be_sent(self, status: str) -> None:
        assert alert_rules.decide(rules(), incident(status=status), NOW).send

    def test_it_must_be_as_serious_as_the_floor(self) -> None:
        floor = rules(min_severity=3)

        assert alert_rules.decide(floor, incident(severity=3), NOW).send
        assert alert_rules.decide(floor, incident(severity=4), NOW).send
        assert alert_rules.decide(floor, incident(severity=2), NOW) == alert_rules.Decision(
            False, "severity"
        )

    def test_it_must_be_as_sure_as_the_floor(self) -> None:
        floor = rules(min_confidence=65)

        assert alert_rules.decide(floor, incident(confidence=65), NOW).send
        assert alert_rules.decide(floor, incident(confidence=64), NOW) == alert_rules.Decision(
            False, "confidence"
        )

    def test_the_severity_is_checked_before_the_confidence(self) -> None:
        decision = alert_rules.decide(rules(), incident(severity=1, confidence=0), NOW)

        assert decision.reason == "severity"

    def test_a_real_threat_needs_neither_floor(self) -> None:
        low = incident(verdict="threat", severity=1, confidence=10)

        assert alert_rules.decide(rules(min_severity=4, min_confidence=100), low, NOW).send

    def test_a_real_threat_still_has_to_be_of_what_was_chosen(self) -> None:
        threat = incident(verdict="threat", sources=["opnsense"], activities=["scan"])

        by_source = alert_rules.decide(rules(sources=("wazuh",)), threat, NOW)
        by_activity = alert_rules.decide(rules(activities=("brute_force",)), threat, NOW)

        assert (by_source.reason, by_activity.reason) == ("source", "activity")

    def test_with_programs_chosen_one_of_them_must_have_reported_it(self) -> None:
        chosen = rules(sources=("crowdsec", "wazuh"))

        assert alert_rules.decide(chosen, incident(sources=["opnsense", "wazuh"]), NOW).send
        assert alert_rules.decide(chosen, incident(sources=["opnsense"]), NOW) == (
            alert_rules.Decision(False, "source")
        )

    def test_with_kinds_chosen_the_incident_must_be_one_of_them(self) -> None:
        chosen = rules(activities=("brute_force",))

        assert alert_rules.decide(chosen, incident(activities=["scan", "brute_force"]), NOW).send
        assert alert_rules.decide(chosen, incident(activities=["scan"]), NOW) == (
            alert_rules.Decision(False, "activity")
        )
        # An incident that is no kind of activity in particular is not any of them.
        assert alert_rules.decide(chosen, incident(activities=[]), NOW).reason == "activity"

    def test_none_chosen_means_any(self) -> None:
        anything = incident(sources=["zenarmor"], activities=[])

        assert alert_rules.decide(rules(), anything, NOW).send

    def test_every_reason_has_words(self) -> None:
        reasons = get_args(alert_rules.Reason)

        assert set(reasons) == set(alert_rules.REASONS)
        for reason in reasons:
            assert alert_rules.explain(reason, rules()).strip()

    def test_the_words_name_the_floors(self) -> None:
        chosen = rules(min_severity=3, min_confidence=80)

        assert alert_rules.explain("severity", chosen) == "Less serious than high"
        assert alert_rules.explain("confidence", chosen) == "AresGate is less than 80% sure"


class TestQuietHours:
    DAYTIME = Quiet(9 * 60, 17 * 60, "UTC", critical_passes=False)
    NIGHT = Quiet(22 * 60, 7 * 60, "UTC", critical_passes=False)

    @pytest.mark.parametrize(
        ("hour", "minute", "quiet"),
        [
            (9, 0, True),
            (12, 0, True),
            (16, 59, True),
            (17, 0, False),
            (8, 59, False),
            (0, 0, False),
        ],
    )
    def test_a_window_within_a_day(self, hour: int, minute: int, quiet: bool) -> None:
        at = datetime(2026, 11, 2, hour, minute, tzinfo=UTC)

        assert alert_rules.in_quiet(self.DAYTIME, at) is quiet

    @pytest.mark.parametrize(
        ("hour", "minute", "quiet"),
        [
            (22, 0, True),
            (23, 59, True),
            (0, 0, True),
            (6, 59, True),
            (7, 0, False),
            (21, 59, False),
        ],
    )
    def test_a_window_over_midnight(self, hour: int, minute: int, quiet: bool) -> None:
        at = datetime(2026, 11, 2, hour, minute, tzinfo=UTC)

        assert alert_rules.in_quiet(self.NIGHT, at) is quiet

    def test_a_window_that_starts_and_ends_together_is_never_on(self) -> None:
        nothing = Quiet(600, 600, "UTC", critical_passes=False)

        assert not alert_rules.in_quiet(nothing, NOW.replace(hour=10))

    def test_it_goes_by_the_clock_in_the_zone_chosen(self) -> None:
        berlin = replace(self.NIGHT, zone="Europe/Berlin")
        # 21:30 UTC is 22:30 in Berlin; 12:00 UTC is 13:00.
        assert alert_rules.in_quiet(berlin, NOW.replace(hour=21, minute=30))
        assert not alert_rules.in_quiet(berlin, NOW)
        assert not alert_rules.in_quiet(self.NIGHT, NOW.replace(hour=21, minute=30))

    def test_a_zone_that_has_gone_is_read_as_utc(self) -> None:
        gone = replace(self.NIGHT, zone="Nowhere/Land")

        assert alert_rules.in_quiet(gone, NOW.replace(hour=23))
        assert alert_rules.quiet_ends(gone, NOW.replace(hour=23)) == datetime(
            2026, 11, 3, 7, 0, tzinfo=UTC
        )

    def test_they_end_this_morning_or_tomorrows(self) -> None:
        night = self.NIGHT

        assert alert_rules.quiet_ends(night, NOW.replace(hour=3)) == datetime(
            2026, 11, 2, 7, 0, tzinfo=UTC
        )
        assert alert_rules.quiet_ends(night, NOW.replace(hour=23)) == datetime(
            2026, 11, 3, 7, 0, tzinfo=UTC
        )
        # At the very end they are over, and the next end is a day on.
        assert alert_rules.quiet_ends(night, NOW.replace(hour=7)) == datetime(
            2026, 11, 3, 7, 0, tzinfo=UTC
        )

    def test_they_end_at_the_same_clock_time_when_the_clocks_change(self) -> None:
        new_york = Quiet(22 * 60, 7 * 60, "America/New_York", critical_passes=False)
        # The night before the clocks go back (2026-11-01 02:00 local).
        at = datetime(2026, 11, 1, 3, 0, tzinfo=UTC)

        ends = alert_rules.quiet_ends(new_york, at)

        assert ends.astimezone(ZoneInfo("America/New_York")).hour == 7

    def test_what_is_sent_in_quiet_hours_is_held(self) -> None:
        quiet = rules(quiet=self.NIGHT)

        held = alert_rules.decide(quiet, incident(), NOW.replace(hour=23))
        awake = alert_rules.decide(quiet, incident(), NOW)

        assert held == alert_rules.Decision(True, held=True)
        assert awake == alert_rules.Decision(True)

    def test_what_is_left_out_is_left_out_in_quiet_hours_too(self) -> None:
        quiet = rules(quiet=self.NIGHT)

        decision = alert_rules.decide(quiet, incident(severity=1), NOW.replace(hour=23))

        assert decision == alert_rules.Decision(False, "severity")

    def test_a_critical_incident_gets_through_when_that_was_asked_for(self) -> None:
        night = replace(self.NIGHT, critical_passes=True)
        at = NOW.replace(hour=23)

        assert alert_rules.decide(rules(quiet=night), incident(severity=4), at) == (
            alert_rules.Decision(True)
        )
        assert alert_rules.decide(rules(quiet=night), incident(severity=3), at).held
        assert alert_rules.decide(rules(quiet=self.NIGHT), incident(severity=4), at).held


class TestTheZone:
    def test_a_zone_is_found_by_its_name(self) -> None:
        zone = alert_rules.zone_of("Europe/Berlin")

        assert zone is not None
        assert zone.key == "Europe/Berlin"

    @pytest.mark.parametrize("name", ["Nowhere/Land", "", "../etc/passwd", "Europe", "UTC\0"])
    def test_a_name_that_is_no_zone_is_none(self, name: str) -> None:
        assert alert_rules.zone_of(name) is None


class TestOnlyThreats:
    def only(self, **changes: Any) -> Rules:
        return rules(mode="threats", **changes)

    def test_a_destination_reads_its_mode(self, session: Session) -> None:
        assert alert_rules.of(destination(session, mode="threats")).mode == "threats"
        assert alert_rules.of(destination(session, name="Other")).mode == "custom"

    def test_what_is_on_the_threats_page_is_told(self) -> None:
        sure = incident(confidence=90, stages=[])
        chain = incident(confidence=40, stages=["recon", "access"])
        owner = incident(confidence=40, verdict="threat")

        for found in (sure, chain, owner):
            assert alert_rules.decide(self.only(), found, NOW).send

    def test_a_suspect_is_not_told_however_serious(self) -> None:
        decision = alert_rules.decide(self.only(), incident(confidence=50, severity=4), NOW)

        assert (decision.send, decision.reason) == (False, "threat")

    def test_the_floors_the_sources_and_the_kinds_do_not_apply(self) -> None:
        strict = self.only(
            min_severity=4, min_confidence=100, sources=("zenarmor",), activities=("brute_force",)
        )

        assert alert_rules.decide(strict, incident(confidence=90, severity=1), NOW).send

    def test_the_owners_word_that_it_is_harmless_wins_over_a_chain(self) -> None:
        found = incident(stages=["recon", "access"], verdict="low_priority")

        assert alert_rules.decide(self.only(), found, NOW).reason == "muted"
        assert alert_rules.decide(self.only(), incident(status="resolved"), NOW).reason == "settled"

    def test_the_ai_can_keep_a_scan_off_the_page(self) -> None:
        found = incident(confidence=70, severity=2, ai_class="noise", ai_confidence=95)

        assert alert_rules.decide(self.only(), found, NOW).reason == "threat"

    def test_what_the_owner_set_for_telling_a_threat_from_noise_is_followed(self) -> None:
        found = incident(confidence=70, severity=2)
        strict = Tuning(threat_from=90)

        assert alert_rules.decide(self.only(), found, NOW).send
        assert alert_rules.decide(self.only(), found, NOW, strict).reason == "threat"

    def test_quiet_hours_hold_a_threat(self) -> None:
        quiet = Quiet(0, 1439, "UTC", critical_passes=False)

        decision = alert_rules.decide(self.only(quiet=quiet), incident(confidence=90), NOW)

        assert (decision.send, decision.held) == (True, True)

    def test_it_says_in_words_why_a_suspect_is_left_out(self) -> None:
        assert alert_rules.explain("threat", self.only()) == (
            "Not a threat: a suspect or background on the Threats page"
        )


class TestThePreview:
    def test_it_counts_what_would_have_been_sent_and_why_the_rest_was_not(
        self, session: Session
    ) -> None:
        incident(session, subject="a", last_seen_at=NOW - 2 * HOUR)
        incident(session, subject="b", last_seen_at=NOW - 3 * HOUR, severity=4, confidence=95)
        incident(session, subject="c", severity=1)
        incident(session, subject="d", confidence=40)
        incident(session, subject="e", verdict="low_priority")
        incident(session, subject="f", status="resolved")
        incident(session, subject="g", sources=["crowdsec"])
        incident(session, subject="h", activities=["brute_force"])

        result = alert_rules.preview(
            session, rules(sources=("wazuh", "opnsense"), activities=("scan",)), NOW
        )

        assert result.hours == 24
        assert (result.considered, result.would_send, result.held) == (8, 2, 0)
        assert result.left_out == {
            "muted": 1,
            "settled": 1,
            "threat": 0,
            "severity": 1,
            "confidence": 1,
            "source": 1,
            "activity": 1,
        }
        assert not result.truncated

    def test_for_a_destination_told_of_threats_it_counts_the_threats_of_the_day(
        self, session: Session
    ) -> None:
        incident(session, subject="a", confidence=90)
        incident(session, subject="b", confidence=40, stages=["recon", "access"])
        incident(session, subject="c", confidence=50)
        incident(session, subject="d", confidence=90, verdict="not_suspicious")

        result = alert_rules.preview(session, rules(mode="threats"), NOW)

        assert (result.considered, result.would_send) == (4, 2)
        assert result.left_out["threat"] == 1
        assert result.left_out["muted"] == 1

    def test_the_newest_that_would_be_sent_are_the_examples(self, session: Session) -> None:
        for n in range(8):
            incident(session, subject=f"i{n}", last_seen_at=NOW - n * 10 * timedelta(minutes=1))

        result = alert_rules.preview(session, rules(), NOW)

        assert [example.title for example in result.examples] == [
            f"Scan from i{n}" for n in range(5)
        ]
        assert result.would_send == 8

    def test_only_the_last_day_is_looked_at(self, session: Session) -> None:
        incident(session, subject="old", last_seen_at=NOW - 25 * HOUR)
        incident(session, subject="recent", last_seen_at=NOW - 23 * HOUR)

        result = alert_rules.preview(session, rules(), NOW)

        assert [example.title for example in result.examples] == ["Scan from recent"]
        assert result.considered == 1

    def test_quiet_hours_are_counted_as_held(self, session: Session) -> None:
        incident(session, subject="a")
        incident(session, subject="b", severity=4)
        night = Quiet(11 * 60, 14 * 60, "UTC", critical_passes=True)

        result = alert_rules.preview(session, rules(quiet=night), NOW)

        assert (result.would_send, result.held) == (2, 1)

    def test_it_says_how_many_came_in_the_busiest_hour_and_how_many_the_limit_would_catch(
        self, session: Session
    ) -> None:
        for n in range(5):
            incident(
                session, subject=f"a{n}", first_seen_at=NOW - 3 * HOUR + n * timedelta(minutes=5)
            )
        for n in range(2):
            incident(
                session, subject=f"b{n}", first_seen_at=NOW - 5 * HOUR + n * timedelta(minutes=5)
            )

        result = alert_rules.preview(session, rules(max_per_hour=3), NOW)

        assert result.busiest_hour == 5
        assert result.over_limit == 2

    def test_an_incident_that_began_before_the_day_counts_from_its_start(
        self, session: Session
    ) -> None:
        incident(session, subject="long", first_seen_at=NOW - 80 * HOUR, last_seen_at=NOW - HOUR)

        result = alert_rules.preview(session, rules(), NOW)

        assert (result.would_send, result.busiest_hour) == (1, 1)

    def test_nothing_going_on_is_nothing_to_send(self, session: Session) -> None:
        result = alert_rules.preview(session, rules(), NOW)

        assert (result.considered, result.would_send, result.busiest_hour, result.over_limit) == (
            0,
            0,
            0,
            0,
        )
        assert result.examples == ()

    def test_it_says_when_there_were_more_than_it_looked_at(
        self, session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(alert_rules, "PREVIEW_LIMIT", 2)
        for n in range(3):
            incident(session, subject=f"i{n}", last_seen_at=NOW - n * HOUR / 10)

        result = alert_rules.preview(session, rules(), NOW)

        assert result.truncated
        assert result.considered == 2
