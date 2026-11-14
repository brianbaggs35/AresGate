"""The watchdog: a collector that stops working is told to the destinations, once for each
stretch of silence, and so is its return."""

from datetime import timedelta
from typing import Any

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.alerts import notify, watchdog
from app.config import Settings
from app.models import AlertDelivery, CollectorHealth
from tests.test_alerts_notify import (
    ALWAYS_QUIET,
    HOUR,
    MINUTE,
    NOW,
    destination,
    incident,
    pass_at,
    rows,
)

QUIET: dict[str, Any] = dict(ALWAYS_QUIET)


def collector(session: Session, **changes: Any) -> CollectorHealth:
    """A collector on OPNsense's API that last worked 40 minutes ago, which is long for one that
    runs every five."""
    fields: dict[str, Any] = {
        "collector": "connection-check",
        "integration": "opnsense",
        "connection": "api",
        "interval_seconds": 300,
        "last_success_at": NOW - 40 * MINUTE,
        "consecutive_failures": 0,
        "updated_at": NOW,
    }
    fields.update(changes)
    row = CollectorHealth(**fields)
    session.add(row)
    session.commit()
    return row


def watchdog_rows(session: Session) -> list[AlertDelivery]:
    return [row for row in rows(session) if row.kind == "watchdog"]


def text_of(job: notify.Job) -> str:
    embed = job.payload["embeds"][0]  # type: ignore[index]
    return f"{embed['title']}\n{embed['description']}"


class TestWhatIsQuiet:
    def test_it_is_a_quarter_of_an_hour_without_a_run_that_worked_at_the_least(
        self, session: Session
    ) -> None:
        fast = collector(session, interval_seconds=30, last_success_at=NOW - 14 * MINUTE)

        assert watchdog.quiet_for(fast) == timedelta(minutes=15)
        assert not watchdog.is_silent(fast, NOW)
        fast.last_success_at = NOW - 16 * MINUTE
        assert watchdog.is_silent(fast, NOW)

    def test_a_slow_collector_is_given_three_of_its_own_intervals(self, session: Session) -> None:
        slow = collector(session, interval_seconds=600, last_success_at=NOW - 29 * MINUTE)

        assert watchdog.quiet_for(slow) == timedelta(minutes=30)
        assert not watchdog.is_silent(slow, NOW)
        slow.last_success_at = NOW - 31 * MINUTE
        assert watchdog.is_silent(slow, NOW)

    def test_one_that_never_worked_is_not_a_monitor_that_went_quiet(self, session: Session) -> None:
        never = collector(session, last_success_at=None, consecutive_failures=4)

        assert not watchdog.is_silent(never, NOW)

    def test_it_is_called_by_the_program_and_what_it_reads(self, session: Session) -> None:
        known = collector(session)
        unknown = collector(session, collector="no-such-one", integration="newfangled")

        assert watchdog.name_of(known) == "OPNsense · Connection check"
        assert watchdog.name_of(unknown) == "newfangled · no-such-one"


class TestTellingOfASilence:
    def test_a_collector_that_went_quiet_is_told_once(
        self, session: Session, settings: Settings
    ) -> None:
        destination(session, settings)
        quiet = collector(session, last_error="HTTP 502")

        first = pass_at(session, settings)
        second = pass_at(session, settings)

        (row,) = watchdog_rows(session)
        last = int((NOW - 40 * MINUTE).timestamp())
        assert (row.kind, row.reason, row.state, row.incident_id) == (
            "watchdog",
            "silent",
            "queued",
            None,
        )
        assert row.key == f"s{last}:{quiet.id.hex[:16]}"
        assert row.title == "OPNsense · Connection check"
        assert (len(first), len(second)) == (1, 1)
        words = text_of(first[0])
        assert "OPNsense · Connection check has gone quiet" in words
        assert "hasn't worked since 2026-11-08 11:20 UTC" in words
        assert "The last attempt said: HTTP 502" in words
        assert "/status" in str(first[0].payload)

    def test_a_collector_that_works_is_not_told_of(
        self, session: Session, settings: Settings
    ) -> None:
        destination(session, settings)
        collector(session, last_success_at=NOW - MINUTE)
        collector(session, collector="firewall-log", last_success_at=None)

        assert pass_at(session, settings) == []
        assert watchdog_rows(session) == []

    def test_the_message_without_an_error_says_nothing_of_one(
        self, session: Session, settings: Settings
    ) -> None:
        destination(session, settings)
        collector(session)

        (job,) = pass_at(session, settings)

        assert "The last attempt said" not in text_of(job)

    def test_a_destination_that_is_off_hears_of_nothing(
        self, session: Session, settings: Settings
    ) -> None:
        destination(session, settings, enabled=False)
        collector(session)

        assert pass_at(session, settings) == []
        assert watchdog_rows(session) == []

    def test_a_second_stretch_of_silence_is_told_again(
        self, session: Session, settings: Settings
    ) -> None:
        destination(session, settings)
        quiet = collector(session)
        pass_at(session, settings)
        quiet.last_success_at = NOW + HOUR
        session.commit()

        pass_at(session, settings, NOW + 3 * HOUR)

        assert len(watchdog_rows(session)) == 2

    def test_it_is_not_held_back_by_the_limit_on_messages_an_hour(
        self, session: Session, settings: Settings
    ) -> None:
        destination(session, settings, max_per_hour=1)
        incident(session)
        incident(session, subject="8.8.8.8", title="Another")
        collector(session)

        jobs = pass_at(session, settings)

        (silent,) = watchdog_rows(session)
        assert silent.state == "queued"
        assert any("has gone quiet" in text_of(job) for job in jobs)
        assert "summarized" in {row.state for row in rows(session)}


class TestQuietHours:
    def test_it_waits_for_quiet_hours_to_end_when_they_do_not_let_critical_through(
        self, session: Session, settings: Settings
    ) -> None:
        row = destination(session, settings, **QUIET)
        collector(session)

        assert pass_at(session, settings) == []

        (held,) = watchdog_rows(session)
        assert (held.state, held.was_held) == ("held", True)
        assert held.due_at > NOW
        row.quiet_hours = False
        session.commit()

        (job,) = pass_at(session, settings)

        assert "has gone quiet" in text_of(job)
        (released,) = watchdog_rows(session)
        assert (released.state, released.due_at) == ("queued", NOW)

    def test_it_is_sent_through_them_where_critical_incidents_are(
        self, session: Session, settings: Settings
    ) -> None:
        destination(session, settings, **dict(QUIET, quiet_critical=True))
        collector(session)

        (job,) = pass_at(session, settings)

        assert "has gone quiet" in text_of(job)
        (row,) = watchdog_rows(session)
        assert (row.state, row.was_held) == ("queued", False)


class TestItsReturn:
    def told(self, session: Session, settings: Settings) -> CollectorHealth:
        destination(session, settings)
        quiet = collector(session)
        pass_at(session, settings)
        (row,) = watchdog_rows(session)
        row.state = "sent"
        row.sent_at = NOW
        session.commit()
        return quiet

    def test_a_destination_that_was_told_of_the_silence_is_told_it_is_back_once(
        self, session: Session, settings: Settings
    ) -> None:
        quiet = self.told(session, settings)
        quiet.last_success_at = NOW + 5 * MINUTE
        session.commit()

        first = pass_at(session, settings, NOW + 6 * MINUTE)
        second = pass_at(session, settings, NOW + 7 * MINUTE)

        silent, back = watchdog_rows(session)
        assert (back.reason, back.state, back.title) == (
            "back",
            "queued",
            "OPNsense · Connection check",
        )
        assert back.key == f"b{silent.key[1:]}"
        assert [text_of(job) for job in first] == [
            "OPNsense · Connection check is reporting again\n"
            "It worked again at 2026-11-08 12:05 UTC."
        ]
        assert len(second) == 1
        assert len(watchdog_rows(session)) == 2

    def test_one_that_was_waiting_to_be_told_is_not_told_of_either(
        self, session: Session, settings: Settings
    ) -> None:
        destination(session, settings, **QUIET)
        quiet = collector(session)
        pass_at(session, settings)
        quiet.last_success_at = NOW + 5 * MINUTE
        session.commit()

        assert pass_at(session, settings, NOW + 6 * MINUTE) == []

        (row,) = watchdog_rows(session)
        assert row.state == "dropped"
        assert row.note == "Not sent. It reported again before this was sent."

    def test_one_that_could_not_be_told_of_the_silence_is_not_told_it_is_back(
        self, session: Session, settings: Settings
    ) -> None:
        quiet = self.told(session, settings)
        (row,) = watchdog_rows(session)
        row.state = "failed"
        quiet.last_success_at = NOW + 5 * MINUTE
        session.commit()

        pass_at(session, settings, NOW + 6 * MINUTE)

        assert len(watchdog_rows(session)) == 1

    def test_one_that_is_still_quiet_is_not_back(
        self, session: Session, settings: Settings
    ) -> None:
        self.told(session, settings)

        pass_at(session, settings, NOW + 6 * MINUTE)

        assert len(watchdog_rows(session)) == 1

    def test_one_that_is_allowed_longer_than_before_is_not_back_either(
        self, session: Session, settings: Settings
    ) -> None:
        quiet = self.told(session, settings)
        quiet.interval_seconds = 3600
        session.commit()

        pass_at(session, settings, NOW + 6 * MINUTE)

        assert len(watchdog_rows(session)) == 1


class TestACollectorThatIsGone:
    def test_a_message_about_one_whose_connection_was_removed_is_not_sent(
        self, session: Session, settings: Settings
    ) -> None:
        destination(session, settings)
        collector(session)
        pass_at(session, settings)
        session.execute(delete(CollectorHealth))
        session.commit()

        assert pass_at(session, settings) == []

        (row,) = watchdog_rows(session)
        assert (row.state, row.note) == ("dropped", "Not sent. The collector is gone.")
