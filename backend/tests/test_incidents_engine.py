from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import Engine, delete, func, select, text
from sqlalchemy.orm import Session

from app import partitions
from app.config import Settings
from app.events.event import NewEvent, Severity
from app.events.store import record as record_events
from app.incidents import engine as correlation
from app.models import Event, Incident, IncidentSignal, SystemInfo
from tests.helpers import new_event

NOW = datetime(2026, 10, 26, 6, 0, tzinfo=UTC)
HOUR = timedelta(hours=1)
# Late enough that everything these tests store has settled, and not so late it is forgotten.
LATER = NOW + 12 * HOUR
# Public addresses, which the documentation ranges are not, and a device on the home network.
ATTACKER = "93.184.216.34"
OTHER_ATTACKER = "8.8.8.8"
DEVICE = "192.168.1.20"


def alert(at: datetime = NOW, n: int = 1, **changes: Any) -> NewEvent:
    return new_event(
        **{
            "occurred_at": at,
            "identity": (f"alert-{n}",),
            "src_address": ATTACKER,
            "dst_address": DEVICE,
            "signature": "ET SCAN Potential SSH Scan",
            "severity": Severity.MEDIUM,
            **changes,
        }
    )


def store(session: Session, settings: Settings, *events: NewEvent) -> None:
    """Stores events as a collector would have as they happened."""
    for event in events:
        record_events(session, settings, [event], event.occurred_at)
    session.commit()


def run(session: Session, now: datetime = LATER) -> correlation.Result:
    result = correlation.correlate(session, now)
    session.commit()
    return result


def incidents(session: Session) -> list[Incident]:
    session.expire_all()
    return list(session.scalars(select(Incident).order_by(Incident.id)))


def signals(session: Session) -> list[IncidentSignal]:
    return list(session.scalars(select(IncidentSignal).order_by(IncidentSignal.occurred_at)))


class TestFilingAnAlert:
    def test_it_becomes_an_incident_about_the_address_outside_the_network(
        self, session: Session, settings: Settings
    ) -> None:
        store(session, settings, alert(severity=Severity.HIGH))

        result = run(session)

        assert result == correlation.Result(events=1, created=1, updated=0)
        (incident,) = incidents(session)
        assert incident.subject == ATTACKER
        assert incident.title == f"ET SCAN Potential SSH Scan ({ATTACKER})"
        assert incident.severity == Severity.HIGH
        assert incident.confidence == 40
        assert incident.status == "open"
        assert incident.signal_count == 1
        assert incident.sources == ["wazuh"]
        assert [str(address) for address in incident.addresses] == [ATTACKER, DEVICE]
        assert (incident.first_seen_at, incident.last_seen_at) == (NOW, NOW)
        assert incident.top_source == "wazuh"
        assert incident.top_summary == "ET SCAN Potential SSH Scan"
        assert not incident.banned
        assert incident.status_changed_at is None
        assert [reason["rule"] for reason in incident.reasons] == ["strongest"]

    def test_the_signal_is_kept_as_it_was(self, session: Session, settings: Settings) -> None:
        store(
            session,
            settings,
            alert(src_port=51514, dst_port=22, protocol="tcp", summary="A scan on ssh"),
        )

        run(session)

        (signal,) = signals(session)
        event = session.scalars(select(Event)).one()
        assert signal.event_id == event.id
        assert signal.incident_id == incidents(session)[0].id
        assert (signal.source, signal.kind, signal.severity) == ("wazuh", "alert", 2)
        assert signal.summary == "A scan on ssh"
        assert signal.signature == "ET SCAN Potential SSH Scan"
        assert str(signal.src_address) == ATTACKER
        assert (signal.src_port, signal.dst_port, signal.protocol) == (51514, 22, "tcp")
        assert str(signal.dst_address) == DEVICE

    def test_the_signal_outlives_the_event(self, session: Session, settings: Settings) -> None:
        store(session, settings, alert())
        run(session)

        session.execute(delete(Event))
        session.commit()

        assert len(signals(session)) == 1

    def test_the_programs_that_agree_and_a_ban_make_it_surer(
        self, session: Session, settings: Settings
    ) -> None:
        store(
            session,
            settings,
            alert(n=1, severity=Severity.HIGH),
            alert(
                NOW + timedelta(minutes=1),
                n=2,
                source="opnsense",
                connection="api",
                severity=Severity.MEDIUM,
            ),
            new_event(
                source="crowdsec",
                connection="lapi",
                kind="decision",
                severity=Severity.LOW,
                occurred_at=NOW + timedelta(minutes=2),
                identity=("ban-1",),
                summary="Ban for ssh-bruteforce",
                src_address=ATTACKER,
            ),
        )

        result = run(session)

        assert result == correlation.Result(events=3, created=1, updated=0)
        (incident,) = incidents(session)
        assert incident.sources == ["crowdsec", "opnsense", "wazuh"]
        assert incident.banned
        assert incident.signal_count == 3
        # The strongest signal is worth 40, two more programs 30, the ban 20.
        assert incident.confidence == 90
        assert [reason["rule"] for reason in incident.reasons] == [
            "strongest",
            "corroborated",
            "banned",
        ]
        assert incident.last_seen_at == NOW + timedelta(minutes=2)

    def test_the_most_serious_signal_names_the_incident(
        self, session: Session, settings: Settings
    ) -> None:
        store(
            session,
            settings,
            alert(n=1, severity=Severity.MEDIUM, signature="Scan"),
            alert(
                NOW + HOUR, n=2, source="opnsense", severity=Severity.CRITICAL, signature="Exploit"
            ),
            alert(NOW + 2 * HOUR, n=3, severity=Severity.LOW, signature="Noise"),
        )

        run(session)

        (incident,) = incidents(session)
        assert incident.severity == Severity.CRITICAL
        assert (incident.top_source, incident.top_summary) == ("opnsense", "Exploit")
        assert incident.title == f"Exploit ({ATTACKER})"

    def test_it_says_why_it_is_as_sure_as_it_is(self, session: Session, settings: Settings) -> None:
        store(session, settings, *(alert(NOW + timedelta(minutes=n), n=n) for n in range(5)))

        run(session)

        (incident,) = incidents(session)
        assert incident.confidence == 25 + 10
        assert incident.reasons[1] == {
            "rule": "repeated",
            "points": 10,
            "text": "It has set off 5 signals.",
        }

    def test_it_is_surer_of_an_attack_that_reaches_several_devices(
        self, session: Session, settings: Settings
    ) -> None:
        store(
            session,
            settings,
            *(
                alert(NOW + timedelta(minutes=n), n=n, dst_address=f"192.168.1.{20 + n}")
                for n in range(3)
            ),
        )

        run(session)

        (incident,) = incidents(session)
        assert [reason["rule"] for reason in incident.reasons] == ["strongest", "spread"]
        assert incident.confidence == 25 + 10


class TestWhatIsNotASignal:
    @pytest.mark.parametrize(
        "changes",
        [
            {"kind": "firewall", "severity": Severity.LOW},
            {"kind": "firewall", "severity": Severity.HIGH},
            {"kind": "agent", "severity": Severity.HIGH},
            {"kind": "alert", "severity": Severity.INFO},
        ],
        ids=["a block", "a serious block", "an agent", "an alert of no importance"],
    )
    def test_the_rest_is_left_alone(
        self, session: Session, settings: Settings, changes: dict[str, Any]
    ) -> None:
        store(session, settings, alert(**changes))

        assert run(session) == correlation.Result()
        assert incidents(session) == []

    def test_an_alert_of_low_severity_is(self, session: Session, settings: Settings) -> None:
        store(session, settings, alert(severity=Severity.LOW))

        assert run(session).created == 1


class TestWhichIncidentASignalBelongsTo:
    @pytest.mark.parametrize(
        ("changes", "subject"),
        [
            ({}, ATTACKER),
            ({"src_address": DEVICE, "dst_address": ATTACKER}, ATTACKER),
            ({"src_address": "192.168.1.30", "dst_address": DEVICE}, "192.168.1.30"),
            ({"src_address": None}, DEVICE),
            ({"src_address": "0.0.0.0", "dst_address": DEVICE}, DEVICE),  # noqa: S104
            (
                {"src_address": None, "dst_address": None},
                "rule:wazuh:ET SCAN Potential SSH Scan",
            ),
        ],
        ids=["inbound", "outbound", "both inside", "one address", "unusable", "none"],
    )
    def test_it_is_about_the_address_of_interest(
        self, session: Session, settings: Settings, changes: dict[str, Any], subject: str
    ) -> None:
        store(session, settings, alert(**changes))

        run(session)

        assert incidents(session)[0].subject == subject

    def test_what_one_attacker_does_is_one_incident_whichever_program_saw_it(
        self, session: Session, settings: Settings
    ) -> None:
        store(
            session,
            settings,
            alert(n=1),
            alert(
                NOW + timedelta(minutes=1),
                n=2,
                source="opnsense",
                src_address=DEVICE,
                dst_address=ATTACKER,
            ),
        )

        assert run(session).created == 1

    def test_two_attackers_are_two_incidents(self, session: Session, settings: Settings) -> None:
        store(session, settings, alert(n=1), alert(n=2, src_address=OTHER_ATTACKER))

        result = run(session)

        assert (result.created, result.updated) == (2, 0)
        assert {incident.subject for incident in incidents(session)} == {ATTACKER, OTHER_ATTACKER}

    def test_signals_without_an_address_are_one_incident_per_rule(
        self, session: Session, settings: Settings
    ) -> None:
        bare: dict[str, Any] = {"src_address": None, "dst_address": None}
        store(
            session,
            settings,
            alert(n=1, **bare),
            alert(NOW + timedelta(minutes=1), n=2, **bare),
            alert(NOW + timedelta(minutes=2), n=3, signature="Another rule", **bare),
        )

        run(session)

        assert sorted((i.subject, i.signal_count) for i in incidents(session)) == [
            ("rule:wazuh:Another rule", 1),
            ("rule:wazuh:ET SCAN Potential SSH Scan", 2),
        ]


class TestWhenAnIncidentIsOver:
    def test_a_signal_a_few_hours_later_is_the_same_incident(
        self, session: Session, settings: Settings
    ) -> None:
        store(session, settings, alert(n=1), alert(NOW + correlation.GAP, n=2))

        run(session)

        (incident,) = incidents(session)
        assert incident.signal_count == 2
        assert incident.last_seen_at == NOW + correlation.GAP

    def test_a_signal_after_a_long_quiet_is_another(
        self, session: Session, settings: Settings
    ) -> None:
        later = NOW + correlation.GAP + timedelta(minutes=1)
        store(session, settings, alert(n=1), alert(later, n=2))

        result = run(session)

        assert result.created == 2
        first, second = incidents(session)
        assert (first.last_seen_at, second.first_seen_at) == (NOW, later)

    def test_a_resolved_incident_stays_resolved_and_the_next_signal_starts_another(
        self, session: Session, settings: Settings
    ) -> None:
        store(session, settings, alert(n=1))
        run(session)
        incident = incidents(session)[0]
        incident.status = "resolved"
        session.commit()
        store(session, settings, alert(NOW + HOUR, n=2))

        result = run(session)

        assert result == correlation.Result(events=1, created=1, updated=0)
        resolved, new = incidents(session)
        assert (resolved.status, resolved.signal_count) == ("resolved", 1)
        assert (new.status, new.signal_count) == ("open", 1)

    @pytest.mark.parametrize("status", ["investigating", "dismissed"])
    def test_an_incident_someone_is_looking_at_or_dismissed_takes_more_signals(
        self, session: Session, settings: Settings, status: str
    ) -> None:
        store(session, settings, alert(n=1))
        run(session)
        incidents(session)[0].status = status
        session.commit()
        store(session, settings, alert(NOW + HOUR, n=2))

        result = run(session)

        assert result == correlation.Result(events=1, created=0, updated=1)
        (incident,) = incidents(session)
        assert (incident.status, incident.signal_count) == (status, 2)

    def test_a_late_signal_from_before_an_incident_joins_it_if_it_is_close_enough(
        self, session: Session, settings: Settings
    ) -> None:
        store(session, settings, alert(NOW + 2 * HOUR, n=1))
        run(session)
        store(session, settings, alert(NOW, n=2))

        result = run(session)

        assert result.updated == 1
        (incident,) = incidents(session)
        assert incident.first_seen_at == NOW
        assert incident.last_seen_at == NOW + 2 * HOUR

    def test_and_starts_its_own_if_it_is_too_far_before(
        self, session: Session, settings: Settings
    ) -> None:
        store(session, settings, alert(NOW + 10 * HOUR, n=1))
        run(session, NOW + 11 * HOUR)
        store(session, settings, alert(NOW, n=2))

        result = run(session, NOW + 12 * HOUR)

        assert result.created == 1
        assert len(incidents(session)) == 2

    def test_it_joins_the_incident_that_was_going_most_recently(
        self, session: Session, settings: Settings
    ) -> None:
        for n, at in enumerate([NOW, NOW + 7 * HOUR], start=1):
            session.add(
                Incident(
                    subject=ATTACKER,
                    title=str(n),
                    severity=2,
                    confidence=25,
                    first_seen_at=at,
                    last_seen_at=at,
                    top_source="wazuh",
                    top_summary="x",
                    signal_count=1,
                    sources=["wazuh"],
                    addresses=[],
                )
            )
        session.commit()
        store(session, settings, alert(NOW + 4 * HOUR, n=1))

        run(session)

        first, second = incidents(session)
        # Both are within hours of the signal; the later one takes it.
        assert (first.signal_count, second.signal_count) == (1, 2)


class TestWhereTheRunGotTo:
    def test_a_run_begins_after_the_last_event_it_read(
        self, session: Session, settings: Settings
    ) -> None:
        store(session, settings, alert(n=1))
        assert run(session).events == 1
        event_id = session.scalars(select(Event.id)).one()

        assert run(session) == correlation.Result()
        assert session.get(SystemInfo, correlation.CURSOR) is not None
        cursor = session.get(SystemInfo, correlation.CURSOR)
        assert cursor is not None
        assert cursor.value == str(event_id)

        store(session, settings, alert(NOW + HOUR, n=2))
        result = run(session)
        assert result == correlation.Result(events=1, created=0, updated=1)
        assert incidents(session)[0].signal_count == 2

    def test_nothing_is_filed_twice(self, session: Session, settings: Settings) -> None:
        store(session, settings, alert(n=1))

        run(session)
        run(session)
        run(session)

        assert session.scalar(select(func.count()).select_from(IncidentSignal)) == 1

    def test_an_event_is_left_until_it_has_settled(
        self, session: Session, settings: Settings
    ) -> None:
        store(session, settings, alert(n=1))

        just_before = NOW + correlation.SETTLE - timedelta(seconds=1)
        assert run(session, just_before) == correlation.Result()
        assert run(session, NOW + correlation.SETTLE).events == 1

    def test_an_event_from_too_long_ago_is_forgotten(
        self, session: Session, settings: Settings
    ) -> None:
        store(session, settings, alert(n=1))

        assert run(session, NOW + correlation.LOOKBACK + timedelta(seconds=1)) == (
            correlation.Result()
        )
        assert run(session, NOW + correlation.LOOKBACK).events == 1

    def test_events_stored_out_of_order_are_filed_in_the_order_they_happened(
        self, session: Session, settings: Settings
    ) -> None:
        # The later one is stored first and so has the lower id.
        store(session, settings, alert(NOW + HOUR, n=1, severity=Severity.HIGH))
        store(session, settings, alert(NOW, n=2, severity=Severity.MEDIUM))

        run(session)

        (incident,) = incidents(session)
        assert (incident.first_seen_at, incident.last_seen_at) == (NOW, NOW + HOUR)
        assert incident.severity == Severity.HIGH

    def test_a_run_reads_only_so_many_events_and_says_there_are_more(
        self, session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(correlation, "BATCH", 2)
        addresses = ["93.184.216.34", "8.8.8.8", "1.1.1.1"]
        store(session, settings, *(alert(n=n, src_address=a) for n, a in enumerate(addresses)))

        first = run(session)
        second = run(session)
        third = run(session)

        assert first == correlation.Result(events=2, created=2, behind=True)
        assert second == correlation.Result(events=1, created=1)
        assert third == correlation.Result()

    def test_a_run_that_is_already_going_leaves_the_work_to_it(
        self, session: Session, settings: Settings, engine: Engine
    ) -> None:
        store(session, settings, alert(n=1))

        with engine.connect() as other:
            other.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": correlation.LOCK})

            result = run(session)

        assert result == correlation.Result(skipped=True)
        assert incidents(session) == []
        # Nothing was lost: the next run files it.
        assert run(session).created == 1

    def test_the_lock_is_not_one_of_the_partitions(self) -> None:
        assert correlation.LOCK not in {weeks.lock_key for weeks in partitions.ALL}


class TestLimits:
    def test_a_very_long_incident_lists_only_so_many_signals_and_counts_the_rest(
        self, session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(correlation, "MAX_SIGNALS", 2)
        store(session, settings, *(alert(NOW + timedelta(minutes=n), n=n) for n in range(3)))

        run(session)

        (incident,) = incidents(session)
        assert incident.signal_count == 3
        assert len(signals(session)) == 2
        assert incident.last_seen_at == NOW + timedelta(minutes=2)

    def test_an_incident_names_only_so_many_addresses_subject_first(
        self, session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(correlation, "MAX_ADDRESSES", 2)
        store(
            session,
            settings,
            alert(n=1, src_address=DEVICE, dst_address=ATTACKER),
            alert(NOW + timedelta(minutes=1), n=2, dst_address="192.168.1.21"),
            alert(NOW + timedelta(minutes=2), n=3, dst_address=DEVICE),
        )

        run(session)

        (incident,) = incidents(session)
        assert [str(address) for address in incident.addresses] == [ATTACKER, DEVICE]

    def test_the_subject_is_kept_even_when_the_first_signal_had_more_addresses_than_fit(
        self, session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(correlation, "MAX_ADDRESSES", 1)
        store(session, settings, alert(n=1, src_address=DEVICE, dst_address=ATTACKER))

        run(session)

        assert [str(address) for address in incidents(session)[0].addresses] == [ATTACKER]
