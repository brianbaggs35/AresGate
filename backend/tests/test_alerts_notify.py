"""The notifier: what it decides to tell a destination, what it holds back, and what becomes of
each message."""

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from typing import Any

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.alerts import destinations, notify
from app.alerts import rules as alert_rules
from app.alerts.discord import Sent
from app.config import Settings
from app.integrations import netguard
from app.integrations.client import Call
from app.models import AlertDelivery, AlertDestination, Device, DeviceAddress, Incident, utcnow
from e2e.stand_ins import discord as discord_stand_in
from tests.stubs import Answer, Serve, StubServer

ID = "1234567890123456789"
TOKEN = "Zk3-_abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-_x"
ADDRESS = f"https://discord.com/api/webhooks/{ID}/{TOKEN}"
OTHER_ADDRESS = f"https://discord.com/api/webhooks/9876543210987654321/{TOKEN}"
NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
HOUR = timedelta(hours=1)
MINUTE = timedelta(minutes=1)
ALWAYS_QUIET = {"quiet_hours": True, "quiet_from": 0, "quiet_until": 1439, "quiet_critical": False}


@pytest.fixture
def new_session(engine: Engine) -> Callable[[], Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def destination(
    session: Session, settings: Settings, name: str = "Security", **changes: Any
) -> AlertDestination:
    """A destination that began listening an hour ago, with the rules of a new one."""
    row = destinations.create(session, settings, name, ADDRESS, NOW - 2 * HOUR)
    row.listening_since = NOW - HOUR
    for field, value in changes.items():
        setattr(row, field, value)
    session.commit()
    return row


def incident(session: Session, **changes: Any) -> Incident:
    fields: dict[str, Any] = {
        "subject": "93.184.216.34",
        "title": "ET SCAN Potential SSH Scan (93.184.216.34)",
        "severity": 3,
        "confidence": 70,
        "status": "open",
        "first_seen_at": NOW - 30 * MINUTE,
        "last_seen_at": NOW - 5 * MINUTE,
        "signal_count": 3,
        "sources": ["opnsense", "wazuh"],
        "addresses": [],
        "ports": [],
        "activities": ["scan"],
        "top_source": "wazuh",
        "top_summary": "ET SCAN Potential SSH Scan",
        "banned": False,
        "verdict": None,
        "waves": 1,
    }
    fields.update(changes)
    found = Incident(**fields)
    session.add(found)
    session.commit()
    return found


def rows(session: Session) -> list[AlertDelivery]:
    session.expire_all()
    return list(session.scalars(select(AlertDelivery).order_by(AlertDelivery.id)))


def pass_at(session: Session, settings: Settings, when: datetime = NOW) -> list[notify.Job]:
    jobs = notify.plan(session, settings, when)
    session.commit()
    return jobs


class TestWhatIsNew:
    def test_an_incident_the_rules_choose_is_queued_once(
        self, session: Session, settings: Settings
    ) -> None:
        destination(session, settings)
        found = incident(session)

        first = pass_at(session, settings)
        second = pass_at(session, settings)

        (row,) = rows(session)
        assert (row.reason, row.key, row.state, row.incident_id) == (
            "new",
            "new",
            "queued",
            found.id,
        )
        assert (row.rank, row.severity, row.confidence, row.title) == (
            32,
            3,
            70,
            found.title,
        )
        assert len(first) == 1
        # Still queued and so sent again if nobody settled it, but never made a second time.
        assert len(second) == 1
        assert len(rows(session)) == 1

    def test_an_incident_the_rules_do_not_choose_is_not_queued(
        self, session: Session, settings: Settings
    ) -> None:
        destination(session, settings)
        incident(session, confidence=20)
        incident(session, severity=1)

        assert pass_at(session, settings) == []
        assert rows(session) == []

    def test_it_only_hears_of_what_happened_since_it_began_listening(
        self, session: Session, settings: Settings
    ) -> None:
        destination(session, settings, listening_since=NOW - MINUTE)
        incident(session, last_seen_at=NOW - 5 * MINUTE)

        assert pass_at(session, settings) == []

    def test_an_incident_not_seen_for_hours_is_not_news(
        self, session: Session, settings: Settings
    ) -> None:
        destination(session, settings, listening_since=NOW - 10 * HOUR)
        incident(session, last_seen_at=NOW - 3 * HOUR)

        assert pass_at(session, settings) == []

    def test_a_destination_that_is_off_refused_or_without_an_address_is_left_alone(
        self, session: Session, settings: Settings
    ) -> None:
        destination(session, settings, "Off", enabled=False)
        refused = destination(session, settings, "Refused", refused=True)
        gone = destination(session, settings, "Gone")
        destinations.forget(session, gone)  # leaves nothing sealed: the row goes with it
        incident(session)

        assert pass_at(session, settings) == []
        assert refused.refused

    def test_an_address_that_cannot_be_opened_is_noted_and_skipped(
        self, session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        row = destination(session, settings)
        incident(session)

        def unusable(*_: object) -> None:
            raise destinations.Unusable("The webhook address is missing or can't be opened.")

        monkeypatch.setattr(destinations, "open_webhook", unusable)

        assert pass_at(session, settings) == []
        session.refresh(row)
        assert row.last_error == "The webhook address is missing or can't be opened."

    def test_each_destination_is_told_by_its_own_rules(
        self, session: Session, settings: Settings
    ) -> None:
        loud = destination(session, settings, "Loud", min_confidence=0, min_severity=1)
        destination(session, settings, "Sure")
        incident(session, confidence=40, severity=2)

        jobs = pass_at(session, settings)

        assert [job.destination_id for job in jobs] == [loud.id]


class TestWhatGetsWorse:
    def sent(self, session: Session, settings: Settings) -> Incident:
        destination(session, settings)
        found = incident(session)
        (job,) = pass_at(session, settings)
        sent = Sent(True, 204)
        assert notify.keep(session, job.delivery_id, sent, NOW) == "sent"
        return found

    def test_a_higher_severity_is_told_again_once(
        self, session: Session, settings: Settings
    ) -> None:
        found = self.sent(session, settings)
        found.severity = 4
        session.commit()

        pass_at(session, settings)
        pass_at(session, settings)

        assert [(row.reason, row.key, row.rank) for row in rows(session)] == [
            ("new", "new", 32),
            ("worse", "worse:42", 42),
        ]

    def test_a_higher_band_of_confidence_is_told_again(
        self, session: Session, settings: Settings
    ) -> None:
        destination(session, settings, min_confidence=0)
        found = incident(session, confidence=40)
        (job,) = pass_at(session, settings)
        notify.keep(session, job.delivery_id, Sent(True, 204), NOW)
        found.confidence = 90
        session.commit()

        pass_at(session, settings)

        assert [row.key for row in rows(session)] == ["new", "worse:32"]

    def test_the_same_band_or_a_lower_one_is_not_told_again(
        self, session: Session, settings: Settings
    ) -> None:
        found = self.sent(session, settings)
        found.confidence = 99
        session.commit()
        pass_at(session, settings)
        assert len(rows(session)) == 1

    def test_it_is_not_told_again_when_the_rules_say_not_to(
        self, session: Session, settings: Settings
    ) -> None:
        row = destination(session, settings, again_when_worse=False)
        incident_row = incident(session)
        (job,) = pass_at(session, settings)
        notify.keep(session, job.delivery_id, Sent(True, 204), NOW)
        incident_row.severity = 4
        session.commit()
        session.refresh(row)

        pass_at(session, settings)

        assert len(rows(session)) == 1

    def test_an_incident_dealt_with_and_then_reopened_is_told_again_once(
        self, session: Session, settings: Settings
    ) -> None:
        found = self.sent(session, settings)
        found.status = "resolved"
        session.commit()
        assert pass_at(session, settings, NOW + MINUTE) == []
        (told,) = rows(session)
        assert told.closed_at == NOW + MINUTE
        found.status = "open"
        session.commit()

        (job,) = pass_at(session, settings, NOW + 2 * MINUTE)
        again = pass_at(session, settings, NOW + 3 * MINUTE)

        keys = [row.key for row in rows(session)]
        assert keys == ["new", f"reopened:{int((NOW + MINUTE).timestamp())}"]
        assert [row.reason for row in rows(session)] == ["new", "reopened"]
        assert job.delivery_id == rows(session)[1].id
        # The reopening is queued and still waiting, so it is offered again but not made again.
        assert [item.delivery_id for item in again] == [job.delivery_id]

    def test_a_second_closing_is_noted_only_once(
        self, session: Session, settings: Settings
    ) -> None:
        found = self.sent(session, settings)
        found.status = "dismissed"
        session.commit()

        pass_at(session, settings, NOW + MINUTE)
        pass_at(session, settings, NOW + 2 * MINUTE)

        assert rows(session)[0].closed_at == NOW + MINUTE


class TestWhatTheOwnerSaid:
    def test_what_waits_is_dropped_when_the_owner_calls_it_not_suspicious(
        self, session: Session, settings: Settings
    ) -> None:
        destination(session, settings)
        found = incident(session)
        pass_at(session, settings)
        found.verdict = "not_suspicious"
        session.commit()

        assert pass_at(session, settings) == []

        (row,) = rows(session)
        assert row.state == "dropped"
        assert row.note == "Not sent. You called it not suspicious or low priority."

    def test_a_dropped_message_is_made_again_when_the_rules_choose_it_again(
        self, session: Session, settings: Settings
    ) -> None:
        destination(session, settings)
        found = incident(session)
        pass_at(session, settings)
        found.verdict = "low_priority"
        session.commit()
        pass_at(session, settings)
        found.verdict = None
        session.commit()

        (job,) = pass_at(session, settings)

        (row,) = rows(session)
        assert (row.state, row.note, job.delivery_id) == ("queued", None, row.id)

    def test_what_was_sent_stays_sent_when_the_owner_later_resolves_it(
        self, session: Session, settings: Settings
    ) -> None:
        destination(session, settings)
        found = incident(session)
        (job,) = pass_at(session, settings)
        notify.keep(session, job.delivery_id, Sent(True, 204), NOW)
        found.status = "resolved"
        session.commit()

        pass_at(session, settings)

        assert rows(session)[0].state == "sent"

    def test_a_failed_message_is_not_made_again(self, session: Session, settings: Settings) -> None:
        destination(session, settings)
        incident(session)
        (job,) = pass_at(session, settings)
        for _ in range(notify.MAX_ATTEMPTS):
            notify.keep(session, job.delivery_id, Sent(False, 500, "no", retry=True), NOW)

        assert pass_at(session, settings, NOW + 2 * MINUTE) == []

        (row,) = rows(session)
        assert row.state == "failed"


class TestQuietHours:
    def test_a_message_in_quiet_hours_waits_until_they_end(
        self, session: Session, settings: Settings
    ) -> None:
        row = destination(
            session, settings, quiet_hours=True, quiet_from=11 * 60, quiet_until=13 * 60
        )
        incident(session)

        assert pass_at(session, settings) == []

        (held,) = rows(session)
        assert (held.state, held.was_held) == ("held", True)
        assert held.due_at == alert_rules.quiet_ends(alert_rules.of(row).quiet, NOW)  # type: ignore[arg-type]
        assert held.due_at == datetime(2026, 11, 8, 13, 0, tzinfo=UTC)

    def test_it_is_sent_when_they_end(self, session: Session, settings: Settings) -> None:
        destination(session, settings, quiet_hours=True, quiet_from=11 * 60, quiet_until=13 * 60)
        found = incident(session)
        pass_at(session, settings)
        found.last_seen_at = NOW + 2 * HOUR
        session.commit()

        (job,) = pass_at(session, settings, NOW + 2 * HOUR + MINUTE)

        (row,) = rows(session)
        assert (row.state, job.delivery_id) == ("queued", row.id)

    def test_a_critical_one_passes_when_the_rules_let_it(
        self, session: Session, settings: Settings
    ) -> None:
        destination(
            session,
            settings,
            quiet_hours=True,
            quiet_from=11 * 60,
            quiet_until=13 * 60,
            quiet_critical=True,
        )
        incident(session, severity=4)

        assert len(pass_at(session, settings)) == 1

        assert rows(session)[0].state == "queued"

    def test_quiet_hours_that_begin_hold_what_was_waiting(
        self, session: Session, settings: Settings
    ) -> None:
        row = destination(session, settings)
        incident(session)
        pass_at(session, settings)
        row.quiet_hours, row.quiet_from, row.quiet_until = True, 11 * 60, 13 * 60
        session.commit()

        assert pass_at(session, settings) == []

        assert rows(session)[0].state == "held"

    def test_a_message_already_tried_is_not_held_by_quiet_hours(
        self, session: Session, settings: Settings
    ) -> None:
        row = destination(session, settings)
        incident(session)
        (job,) = pass_at(session, settings)
        notify.keep(session, job.delivery_id, Sent(False, 500, "no", retry=True), NOW)
        row.quiet_hours, row.quiet_from, row.quiet_until = True, 11 * 60, 13 * 60
        session.commit()

        pass_at(session, settings, NOW + 5 * MINUTE)

        assert rows(session)[0].state == "retrying"

    def test_two_or_more_that_waited_are_told_as_one_summary(
        self, session: Session, settings: Settings
    ) -> None:
        row = destination(
            session,
            settings,
            quiet_hours=True,
            quiet_from=11 * 60,
            quiet_until=13 * 60,
            quiet_critical=False,
        )
        first = incident(session)
        second = incident(session, subject="93.184.216.35", severity=4)
        pass_at(session, settings)
        for found in (first, second):
            found.last_seen_at = NOW + 2 * HOUR
        session.commit()

        jobs = pass_at(session, settings, NOW + 2 * HOUR + MINUTE)

        made = rows(session)
        summary = next(item for item in made if item.kind == "summary")
        told = [item for item in made if item.kind == "incident"]
        assert [job.delivery_id for job in jobs] == [summary.id]
        assert (summary.reason, summary.covers, summary.state) == ("quiet", 2, "queued")
        assert [(item.state, item.summary_id) for item in told] == [("summarized", summary.id)] * 2
        payload = jobs[0].payload["embeds"][0]  # type: ignore[index]
        assert payload["title"] == "2 incidents came in during quiet hours"  # type: ignore[index]
        assert row.id == summary.destination_id

    def test_one_that_waited_is_sent_as_itself(self, session: Session, settings: Settings) -> None:
        destination(session, settings, quiet_hours=True, quiet_from=11 * 60, quiet_until=13 * 60)
        found = incident(session)
        pass_at(session, settings)
        found.last_seen_at = NOW + 2 * HOUR
        session.commit()

        (job,) = pass_at(session, settings, NOW + 2 * HOUR + MINUTE)

        (row,) = rows(session)
        assert (row.kind, job.delivery_id) == ("incident", row.id)


class TestTheLimit:
    def test_what_is_over_the_limit_is_told_in_one_summary(
        self, session: Session, settings: Settings
    ) -> None:
        destination(session, settings, max_per_hour=2)
        for number in range(5):
            incident(session, subject=f"93.184.216.{number}", severity=3 if number else 4)

        jobs = pass_at(session, settings)

        made = rows(session)
        summary = next(item for item in made if item.kind == "summary")
        told = [item for item in made if item.kind == "incident"]
        assert len(jobs) == 3
        assert jobs[-1].delivery_id == summary.id
        assert (summary.reason, summary.covers) == ("limit", 3)
        assert sorted(item.state for item in told) == ["queued", "queued"] + ["summarized"] * 3
        # The worst go first.
        assert 4 in [item.severity for item in told if item.state == "queued"]
        assert all(item.note == "Told in a summary." for item in told if item.summary_id)

    def test_only_one_summary_an_hour_is_made(self, session: Session, settings: Settings) -> None:
        destination(session, settings, max_per_hour=1)
        for number in range(3):
            incident(session, subject=f"93.184.216.{number}")
        pass_at(session, settings)
        incident(session, subject="93.184.216.99")

        jobs = pass_at(session, settings, NOW + MINUTE)

        assert len([item for item in rows(session) if item.kind == "summary"]) == 1
        # The one waiting for its turn is not sent, nor made a second summary yet.
        limited = [item for item in rows(session) if item.state == "limited"]
        assert len(limited) == 1
        assert all(job.delivery_id != limited[0].id for job in jobs)

    def test_the_hour_counts_only_what_was_sent_in_it(
        self, session: Session, settings: Settings
    ) -> None:
        destination(session, settings, max_per_hour=1)
        incident(session, subject="93.184.216.1")
        (job,) = pass_at(session, settings)
        notify.keep(session, job.delivery_id, Sent(True, 204), NOW)
        incident(session, subject="93.184.216.2")

        (summary,) = pass_at(session, settings, NOW + 10 * MINUTE)
        notify.keep(session, summary.delivery_id, Sent(True, 204), NOW + 10 * MINUTE)
        incident(session, subject="93.184.216.3", last_seen_at=NOW + 65 * MINUTE)
        (next_one,) = pass_at(session, settings, NOW + 70 * MINUTE)

        made = {item.id: item for item in rows(session)}
        assert made[job.delivery_id].state == "sent"
        assert made[summary.delivery_id].kind == "summary"
        assert made[next_one.delivery_id].state == "queued"

    def test_a_summary_told_of_something_that_was_then_dropped_is_not_a_problem(
        self, session: Session, settings: Settings
    ) -> None:
        destination(session, settings, max_per_hour=1)
        incident(session, subject="93.184.216.1")
        second = incident(session, subject="93.184.216.2")
        pass_at(session, settings)
        second.verdict = "not_suspicious"
        session.commit()

        pass_at(session, settings, NOW + MINUTE)

        assert {item.state for item in rows(session)} <= {"queued", "summarized", "dropped"}


class TestWhatIsTooOld:
    def test_a_message_due_for_hours_is_given_up_on(
        self, session: Session, settings: Settings
    ) -> None:
        destination(session, settings)
        found = incident(session)
        pass_at(session, settings)
        found.last_seen_at = NOW + 3 * HOUR
        session.commit()

        assert pass_at(session, settings, NOW + notify.STALE + MINUTE) == []

        (row,) = rows(session)
        assert (row.state, row.note) == (
            "failed",
            "Not sent in time: by then it was no longer news.",
        )

    def test_what_waits_for_quiet_hours_is_not_old_while_it_waits(
        self, session: Session, settings: Settings
    ) -> None:
        destination(
            session,
            settings,
            quiet_hours=True,
            quiet_from=0,
            quiet_until=1439,
            quiet_critical=False,
        )
        incident(session)
        pass_at(session, settings)
        incident_row = rows(session)[0]
        assert incident_row.due_at > NOW + 5 * HOUR

        pass_at(session, settings, NOW + 5 * HOUR)

        assert rows(session)[0].state == "held"


class TestWhatIsSaid:
    def test_it_builds_the_message_at_the_detail_the_destination_has(
        self, session: Session, settings: Settings
    ) -> None:
        destination(session, settings, detail="full")
        found = incident(session, addresses=[ip_address("192.168.1.20"), ip_address("10.0.0.9")])
        device = Device(
            mac="aa:bb:cc:dd:ee:01", hostname="laptop", first_seen_at=NOW, last_seen_at=NOW
        )
        session.add(device)
        session.flush()
        session.add(
            DeviceAddress(
                device_id=device.id, address="192.168.1.20", first_seen_at=NOW, last_seen_at=NOW
            )
        )
        session.commit()

        (job,) = pass_at(session, settings)

        text = str(job.payload["embeds"])  # type: ignore[index]
        assert "laptop (192.168.1.20)" in text
        assert f"{settings.public_origin}/incidents/{found.id}" in text

    def test_a_message_whose_incident_has_gone_is_dropped(
        self, session: Session, settings: Settings
    ) -> None:
        destination(session, settings)
        found = incident(session)
        pass_at(session, settings)
        # The incident is deleted while the message waits, and the row stays with no incident.
        session.delete(found)
        session.commit()

        assert pass_at(session, settings) == []

        (row,) = rows(session)
        assert (row.state, row.incident_id) == ("dropped", None)
        assert row.note == "Not sent. The incident is gone."


class TestSettling:
    def made(self, session: Session, settings: Settings) -> tuple[AlertDestination, int]:
        row = destination(session, settings)
        incident(session)
        (job,) = pass_at(session, settings)
        return row, job.delivery_id

    def settle(self, session: Session, delivery_id: int, sent: Sent, when: datetime = NOW) -> str:
        return notify.keep(session, delivery_id, sent, when)

    def test_a_message_that_got_through_is_sent(self, session: Session, settings: Settings) -> None:
        row, delivery_id = self.made(session, settings)

        assert self.settle(session, delivery_id, Sent(True, 204)) == "sent"

        (sent,) = rows(session)
        assert (sent.state, sent.sent_at, sent.attempts, sent.note) == ("sent", NOW, 1, None)
        session.refresh(row)
        assert row.last_success_at == NOW
        assert row.last_error is None

    def test_a_failure_is_tried_again_after_a_longer_wait_each_time(
        self, session: Session, settings: Settings
    ) -> None:
        row, delivery_id = self.made(session, settings)
        failed = Sent(False, 500, "Discord had a fault of its own.", retry=True)

        waits: list[timedelta] = []
        for _ in range(3):
            assert self.settle(session, delivery_id, failed) == "retrying"
            waits.append(rows(session)[0].due_at - NOW)

        assert waits == [timedelta(seconds=30), timedelta(seconds=60), timedelta(seconds=120)]
        (waiting,) = rows(session)
        assert (waiting.state, waiting.attempts) == ("retrying", 3)
        assert waiting.note == "Discord had a fault of its own."
        session.refresh(row)
        assert row.last_error == "Discord had a fault of its own."

    def test_it_waits_as_long_as_discord_says(self, session: Session, settings: Settings) -> None:
        _, delivery_id = self.made(session, settings)

        self.settle(
            session, delivery_id, Sent(False, 429, "Slow down.", retry=True, retry_after=90.5)
        )

        assert rows(session)[0].due_at == NOW + timedelta(seconds=90.5)

    def test_a_retry_is_sent_when_it_is_due_and_not_before(
        self, session: Session, settings: Settings
    ) -> None:
        _, delivery_id = self.made(session, settings)
        self.settle(session, delivery_id, Sent(False, 500, "x", retry=True))

        early = pass_at(session, settings, NOW + 10 * MINUTE - 9 * MINUTE)
        due = pass_at(session, settings, NOW + 31 * timedelta(seconds=1))

        assert early == [] or early[0].delivery_id == delivery_id
        assert [job.delivery_id for job in due] == [delivery_id]

    def test_it_gives_up_after_the_most_tries(self, session: Session, settings: Settings) -> None:
        _, delivery_id = self.made(session, settings)
        failed = Sent(False, 500, "Discord had a fault of its own.", retry=True)

        outcomes = [self.settle(session, delivery_id, failed) for _ in range(notify.MAX_ATTEMPTS)]

        assert outcomes == ["retrying"] * (notify.MAX_ATTEMPTS - 1) + ["failed"]
        (row,) = rows(session)
        assert (row.state, row.attempts) == ("failed", notify.MAX_ATTEMPTS)

    def test_a_refusal_that_cannot_pass_is_not_tried_again(
        self, session: Session, settings: Settings
    ) -> None:
        _, delivery_id = self.made(session, settings)

        assert (
            self.settle(session, delivery_id, Sent(False, 400, "Discord refused it.")) == "failed"
        )

        assert rows(session)[0].note == "Discord refused it."

    def test_a_webhook_that_is_gone_is_never_tried_again_and_the_rest_fail_with_it(
        self, session: Session, settings: Settings
    ) -> None:
        row, delivery_id = self.made(session, settings)
        incident(session, subject="93.184.216.77")
        pass_at(session, settings)
        gone = Sent(False, 404, "Discord doesn't accept this webhook.", gone=True)

        assert self.settle(session, delivery_id, gone) == "failed"

        session.refresh(row)
        assert row.refused
        states = {item.id: item.state for item in rows(session)}
        assert set(states.values()) == {"failed"}
        assert "replace its address" in str(rows(session)[1].note)
        incident(session, subject="93.184.216.78")
        assert pass_at(session, settings, NOW + MINUTE) == []

    def test_an_address_put_right_makes_it_listen_again(
        self, session: Session, settings: Settings
    ) -> None:
        row, delivery_id = self.made(session, settings)
        self.settle(session, delivery_id, Sent(False, 404, "no", gone=True))

        destinations.replace_address(session, settings, row, OTHER_ADDRESS, NOW)

        assert not row.refused

    def test_a_destination_removed_meanwhile_is_not_a_problem(
        self, session: Session, settings: Settings
    ) -> None:
        row, delivery_id = self.made(session, settings)
        destinations.forget(session, row)
        session.commit()

        assert self.settle(session, delivery_id, Sent(True, 204)) == "gone"

    def test_the_waits_double_up_to_a_quarter_of_an_hour(self) -> None:
        assert [notify.retry_in(n).total_seconds() for n in (1, 2, 3, 4, 5, 6, 12)] == [
            30,
            60,
            120,
            240,
            480,
            900,
            900,
        ]
        assert notify.retry_in(0) == notify.FIRST_RETRY

    def test_bands_and_ranks_only_go_up_as_things_get_worse(self) -> None:
        assert [notify.band_of(n) for n in (0, 34, 35, 64, 65, 100)] == [0, 0, 1, 1, 2, 2]
        low = Incident(severity=2, confidence=90)
        high = Incident(severity=3, confidence=10)
        assert notify.rank_of(low) < notify.rank_of(high)
        assert notify.rank_of(replace_confidence(high, 90)) > notify.rank_of(high)


def replace_confidence(found: Incident, confidence: int) -> Incident:
    return Incident(severity=found.severity, confidence=confidence)


async def nothing(call: Call) -> None:
    """Does not log the call."""


def stand_in(serve: Serve, *answers: Answer) -> StubServer:
    """Discord, on this machine: it answers with each of these in turn, then as Discord does."""
    known = discord_stand_in(f"{ID}/{TOKEN}")
    waiting = list(answers)

    def handle(seen: Any) -> Answer:
        return waiting.pop(0) if waiting else known(seen)

    return serve(handle)


def tell(
    settings: Settings,
    new_session: Callable[[], Session],
    server: StubServer,
    pace: float = 0,
) -> notify.Report:
    return asyncio.run(
        notify.notify_once(
            settings,
            new_session,
            nothing,
            netguard.PUBLIC_INTERNET_AND_LOOPBACK,
            server.url,
            pace=pace,
        )
    )


class TestAPass:
    def test_it_sends_what_the_rules_choose_once_and_keeps_the_log(
        self, session: Session, settings: Settings, new_session: Callable[[], Session], serve: Serve
    ) -> None:
        row = destination(session, settings)
        incident(session, last_seen_at=utcnow(), first_seen_at=utcnow())
        row.listening_since = utcnow() - HOUR
        session.commit()
        server = stand_in(serve)

        first = tell(settings, new_session, server)
        second = tell(settings, new_session, server)

        assert (first, second) == (notify.Report(sent=1), notify.Report())
        assert len(server.seen) == 1
        (sent,) = rows(session)
        assert (sent.state, sent.attempts) == ("sent", 1)
        session.refresh(row)
        assert row.last_success_at is not None
        assert b"allowed_mentions" in server.seen[0].body
        assert TOKEN not in server.seen[0].body.decode()

    def test_a_busy_discord_is_waited_for(
        self, session: Session, settings: Settings, new_session: Callable[[], Session], serve: Serve
    ) -> None:
        row = destination(session, settings)
        for number in (1, 2):
            incident(session, subject=f"93.184.216.{number}", last_seen_at=utcnow())
        row.listening_since = utcnow() - HOUR
        session.commit()
        busy = Answer(
            status=429,
            body='{"message": "You are being rate limited.", "retry_after": 2.5, "global": false}',
        )
        server = stand_in(serve, busy)

        report = tell(settings, new_session, server)

        # The second message is not tried while Discord says to wait.
        assert report == notify.Report(retrying=1)
        assert len(server.seen) == 1
        waiting = [item for item in rows(session) if item.state == "retrying"]
        assert len(waiting) == 1
        assert (waiting[0].due_at - utcnow()).total_seconds() > 20

    def test_a_spent_allowance_is_waited_out_between_messages(
        self,
        session: Session,
        settings: Settings,
        new_session: Callable[[], Session],
        serve: Serve,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        row = destination(session, settings)
        for number in (1, 2):
            incident(session, subject=f"93.184.216.{number}", last_seen_at=utcnow())
        row.listening_since = utcnow() - HOUR
        session.commit()
        spent = Answer(
            status=204, headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset-After": "0.01"}
        )
        server = stand_in(serve, spent)
        slept: list[float] = []
        real_sleep = asyncio.sleep

        async def sleep(seconds: float) -> None:
            slept.append(seconds)
            await real_sleep(0)

        monkeypatch.setattr(notify.asyncio, "sleep", sleep)

        report = tell(settings, new_session, server)

        assert report == notify.Report(sent=2)
        assert slept[0] == 0.01

    def test_a_long_wait_leaves_the_rest_for_the_next_pass(
        self, session: Session, settings: Settings, new_session: Callable[[], Session], serve: Serve
    ) -> None:
        row = destination(session, settings)
        for number in (1, 2):
            incident(session, subject=f"93.184.216.{number}", last_seen_at=utcnow())
        row.listening_since = utcnow() - HOUR
        session.commit()
        spent = Answer(
            status=204, headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset-After": "30"}
        )
        server = stand_in(serve, spent)

        report = tell(settings, new_session, server)

        assert report == notify.Report(sent=1)
        assert len(server.seen) == 1
        assert sorted(item.state for item in rows(session)) == ["queued", "sent"]

    def test_a_webhook_discord_does_not_know_is_set_aside_after_one_try(
        self, session: Session, settings: Settings, new_session: Callable[[], Session], serve: Serve
    ) -> None:
        row = destination(session, settings)
        for number in (1, 2):
            incident(session, subject=f"93.184.216.{number}", last_seen_at=utcnow())
        row.listening_since = utcnow() - HOUR
        session.commit()
        server = serve(discord_stand_in("1/other"))

        first = tell(settings, new_session, server)
        second = tell(settings, new_session, server)

        assert first == notify.Report(failed=1)
        assert second == notify.Report()
        assert len(server.seen) == 1
        session.refresh(row)
        assert row.refused
        assert row.last_error is not None
        assert {item.state for item in rows(session)} == {"failed"}

    def test_when_nothing_can_be_reached_it_is_tried_again_later(
        self, session: Session, settings: Settings, new_session: Callable[[], Session], serve: Serve
    ) -> None:
        row = destination(session, settings)
        incident(session, last_seen_at=utcnow())
        row.listening_since = utcnow() - HOUR
        session.commit()
        server = stand_in(serve, Answer(drop=True))

        report = tell(settings, new_session, server)

        assert report == notify.Report(retrying=1)
        assert rows(session)[0].state == "retrying"


def run_loop(
    behave: Callable[[int], notify.Report], *, enabled: bool = True, times: int = 2
) -> list[int]:
    """Runs the loop with the pass swapped for ``behave`` until it has been called ``times``."""
    calls: list[int] = []

    async def fake(*args: Any, **kwargs: Any) -> notify.Report:
        calls.append(1)
        return behave(len(calls))

    async def go() -> None:
        task = asyncio.create_task(
            notify.run(
                None,  # type: ignore[arg-type]
                lambda: None,  # type: ignore[arg-type,return-value]
                nothing,
                netguard.PUBLIC_INTERNET,
                enabled=enabled,
                interval=timedelta(milliseconds=1),
            )
        )
        for _ in range(50):
            if len(calls) >= times:
                break
            await asyncio.sleep(0.001)
        task.cancel()
        await asyncio.wait({task})

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(notify, "notify_once", fake)
        asyncio.run(go())
    return calls


class TestTheLoop:
    def test_it_goes_on_passing(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO):
            calls = run_loop(lambda n: notify.Report(sent=n))

        assert len(calls) >= 2
        assert "Alerts: 1 sent, 0 to try again, 0 given up on" in caplog.text

    def test_it_says_nothing_of_a_pass_that_did_nothing(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO):
            run_loop(lambda n: notify.Report())

        assert "Alerts:" not in caplog.text

    def test_a_failed_pass_is_logged_and_tried_again(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        def behave(n: int) -> notify.Report:
            if n == 1:
                raise ConnectionError("the database isn't up yet")
            return notify.Report()

        with caplog.at_level(logging.ERROR):
            calls = run_loop(behave)

        assert "Couldn't send the latest alerts" in caplog.text
        assert len(calls) >= 2

    def test_when_collecting_is_off_nothing_is_sent(self) -> None:
        assert run_loop(lambda n: notify.Report(), enabled=False, times=1) == []
