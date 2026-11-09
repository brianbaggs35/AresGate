"""The second pass of the noise filters: how long a scan or a brute force may pause before its next
signal is another incident, and the fewest signals of low severity that one program's incident
needs before it is asked about (see ``filters.too_thin``)."""

from dataclasses import replace
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.config import Settings
from app.events.event import Severity
from app.incidents import engine as correlation
from app.incidents import episode, filters, verdicts
from app.incidents.filters import Filters
from app.models import IncidentSignal
from tests.test_incidents_engine import (
    NOW,
    alert,
    brute,
    incidents,
    run,
    say,
    scan,
    signals,
    store,
)


def keep(session: Session, **changes: Any) -> None:
    """The owner saves their filters, with these settings changed and the rest as they are."""
    filters.save(session, replace(filters.load(session), **changes))
    session.commit()


def row(**changes: Any) -> IncidentSignal:
    """A signal of an incident as the engine keeps it, with nothing set aside unless changed."""
    fields: dict[str, Any] = {
        "source": "wazuh",
        "kind": "alert",
        "severity": int(Severity.LOW),
        "duplicate": False,
        **changes,
    }
    return IncidentSignal(**fields)


class TestHowLongAScanMayPause:
    def test_a_scan_that_pauses_for_less_than_the_owners_gap_is_the_same_incident(
        self, session: Session, settings: Settings
    ) -> None:
        keep(session, scan_gap_hours=8)
        store(session, settings, scan(n=1), scan(NOW + timedelta(hours=7), n=2))

        assert run(session).created == 1

    def test_a_longer_pause_is_another_incident(self, session: Session, settings: Settings) -> None:
        keep(session, scan_gap_hours=8)
        store(session, settings, scan(n=1), scan(NOW + timedelta(hours=9), n=2))

        assert run(session).created == 2

    def test_a_brute_force_has_its_own_gap(self, session: Session, settings: Settings) -> None:
        keep(session, brute_force_gap_hours=2)
        store(session, settings, brute(n=1), brute(NOW + timedelta(hours=3), n=2))

        assert run(session).created == 2

    def test_a_scan_keeps_its_gap_when_the_brute_force_one_changes(
        self, session: Session, settings: Settings
    ) -> None:
        keep(session, brute_force_gap_hours=2)
        store(session, settings, scan(n=1), scan(NOW + timedelta(hours=3), n=2))

        assert run(session).created == 1


class TestWhenAThinIncidentIsAskedAbout:
    def test_a_lone_low_alert_is_set_aside_until_as_many_as_the_owner_said_are_there(
        self, session: Session, settings: Settings
    ) -> None:
        keep(session, thin_low_signals=3)
        store(session, settings, alert(n=1, severity=Severity.LOW))

        run(session)

        (incident,) = incidents(session)
        (kept,) = signals(session)
        assert kept.filtered_by == filters.THIN
        assert (incident.signal_count, incident.filtered_count, incident.confidence) == (1, 1, 0)

        store(
            session,
            settings,
            alert(NOW + timedelta(minutes=1), n=2, severity=Severity.LOW),
            alert(NOW + timedelta(minutes=2), n=3, severity=Severity.LOW),
        )

        run(session)

        (incident,) = incidents(session)
        assert incident.filtered_count == 0
        assert {item.filtered_by for item in signals(session)} == {None}

    def test_low_alerts_from_one_program_are_asked_about_when_there_are_enough(
        self, session: Session, settings: Settings
    ) -> None:
        keep(session, thin_low_signals=3)
        store(
            session,
            settings,
            *(alert(NOW + timedelta(minutes=n), n=n, severity=Severity.LOW) for n in range(3)),
        )

        run(session)

        (incident,) = incidents(session)
        assert (incident.signal_count, incident.filtered_count) == (3, 0)

    def test_a_program_that_agrees_with_another_is_not_thin(
        self, session: Session, settings: Settings
    ) -> None:
        keep(session, thin_low_signals=5)
        store(
            session,
            settings,
            alert(n=1, severity=Severity.LOW),
            alert(NOW + timedelta(minutes=1), n=2, source="opnsense", severity=Severity.LOW),
        )

        run(session)

        assert {item.filtered_by for item in signals(session)} == {None}

    def test_a_high_alert_is_never_thin(self, session: Session, settings: Settings) -> None:
        keep(session, thin_low_signals=5)
        store(session, settings, alert(n=1, severity=Severity.HIGH))

        run(session)

        assert {item.filtered_by for item in signals(session)} == {None}

    def test_a_verdict_outranks_the_minimum(self, session: Session, settings: Settings) -> None:
        keep(session, thin_low_signals=3)
        say(session, verdicts.THREAT, signature="ET SCAN Potential SSH Scan")
        store(session, settings, alert(n=1, severity=Severity.LOW))

        run(session)

        (kept,) = signals(session)
        assert (kept.verdict, kept.filtered_by) == (verdicts.THREAT, None)

    def test_the_minimum_is_worked_out_again_for_the_incidents_going_on(
        self, session: Session, settings: Settings
    ) -> None:
        store(
            session,
            settings,
            alert(n=1, severity=Severity.LOW),
            alert(NOW + timedelta(minutes=1), n=2, severity=Severity.LOW),
        )
        run(session)
        assert {item.filtered_by for item in signals(session)} == {None}

        keep(session, thin_low_signals=3)
        correlation.reapply(session)
        session.commit()

        assert {item.filtered_by for item in signals(session)} == {filters.THIN}
        (incident,) = incidents(session)
        assert incident.filtered_count == 2

        keep(session, thin_low_signals=2)
        correlation.reapply(session)
        session.commit()

        assert {item.filtered_by for item in signals(session)} == {None}

    def test_an_incident_that_outgrew_its_timeline_keeps_the_count_it_had(
        self, session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(correlation, "MAX_SIGNALS", 1)
        keep(session, thin_low_signals=3)
        store(
            session,
            settings,
            alert(n=1, severity=Severity.LOW),
            alert(NOW + timedelta(minutes=1), n=2, severity=Severity.LOW),
        )

        run(session)

        (incident,) = incidents(session)
        assert incident.signal_count == 2


class TestWhatIsThin:
    def test_one_is_no_minimum_at_all(self) -> None:
        assert not filters.too_thin([row()], 1)

    def test_a_lone_low_alert_is_thin_until_the_minimum_is_reached(self) -> None:
        assert filters.too_thin([row()], 3)
        assert filters.too_thin([row(), row()], 3)
        assert not filters.too_thin([row(), row(), row()], 3)

    def test_it_is_one_program_and_low_severity_only(self) -> None:
        assert not filters.too_thin([row(), row(source="opnsense")], 5)
        assert not filters.too_thin([row(), row(severity=int(Severity.MEDIUM))], 5)

    def test_a_verdict_on_any_of_its_signals_means_the_owner_has_looked(self) -> None:
        assert not filters.too_thin([row(verdict=verdicts.NOT_SUSPICIOUS)], 5)
        assert not filters.too_thin([row(), row(verdict=verdicts.THREAT)], 5)

    def test_what_another_filter_set_aside_is_not_counted(self) -> None:
        assert filters.too_thin([row(), row(filtered_by=filters.INSIDE)], 2)
        assert not filters.too_thin([row(filtered_by=filters.SEVERITY)], 5)

    def test_a_duplicate_is_not_counted_but_another_program_agrees(self) -> None:
        assert filters.too_thin([row(), row(duplicate=True)], 2)
        assert not filters.too_thin([row(), row(source="opnsense", duplicate=True)], 5)

    def test_nothing_is_not_thin(self) -> None:
        assert not filters.too_thin([], 3)


class TestTheSettingsOfTheSecondPass:
    def test_the_defaults_are_the_engines_own(self) -> None:
        assert Filters().gaps() == episode.DEFAULT_GAPS
        assert filters.DEFAULT_THIN_LOW_SIGNALS == 1
        assert timedelta(hours=filters.MAX_GAP_HOURS) == episode.MAX_SPAN

    def test_what_is_saved_is_what_is_loaded(self, session: Session) -> None:
        saved = Filters(scan_gap_hours=8, brute_force_gap_hours=2, thin_low_signals=3)

        assert filters.save(session, saved)
        session.commit()

        assert filters.load(session) == saved
        assert saved.gaps() == episode.Gaps(scan=timedelta(hours=8), brute_force=timedelta(hours=2))
