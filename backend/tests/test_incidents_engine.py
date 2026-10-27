from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from typing import Any

import pytest
from sqlalchemy import Engine, delete, func, select, text
from sqlalchemy.orm import Session

from app import partitions
from app.config import Settings
from app.events.event import NewEvent, Severity
from app.events.store import record as record_events
from app.incidents import engine as correlation
from app.incidents import episode
from app.models import Event, Incident, IncidentSignal, SystemInfo, VerdictRule
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


def say(session: Session, verdict: str, **about: str) -> VerdictRule:
    """The owner gives a verdict: on an address, a program or a signature."""
    rule = VerdictRule(
        verdict=verdict,
        address=ip_address(about["address"]) if "address" in about else None,
        source=about.get("source"),
        signature=about.get("signature"),
    )
    session.add(rule)
    session.commit()
    return rule


class TestWhatTheOwnerSaid:
    def test_a_signal_called_fine_is_listed_and_counted_but_is_sure_of_nothing(
        self, session: Session, settings: Settings
    ) -> None:
        rule = say(session, "not_suspicious", signature="ET SCAN Potential SSH Scan")
        store(session, settings, alert(severity=Severity.CRITICAL))

        run(session)

        (incident,) = incidents(session)
        assert incident.signal_count == 1
        assert incident.verdict == "not_suspicious"
        assert incident.verdict_counts == {"not_suspicious": 1}
        assert incident.confidence == 0
        assert [reason["rule"] for reason in incident.reasons] == ["muted"]
        (signal,) = signals(session)
        assert (signal.verdict, signal.verdict_rule_id) == ("not_suspicious", rule.id)

    def test_it_is_described_by_what_was_called_fine_until_something_else_comes(
        self, session: Session, settings: Settings
    ) -> None:
        say(session, "low_priority", source="opnsense")
        store(
            session,
            settings,
            alert(n=1, source="opnsense", connection="api", severity=Severity.LOW),
            alert(NOW + timedelta(minutes=1), n=2, source="opnsense", connection="api"),
        )

        run(session)

        (incident,) = incidents(session)
        assert incident.verdict == "low_priority"
        assert incident.severity == Severity.MEDIUM
        assert incident.sources == ["opnsense"]
        assert [str(address) for address in incident.addresses] == [ATTACKER, DEVICE]

    def test_a_signal_that_counts_takes_over_from_the_ones_called_fine(
        self, session: Session, settings: Settings
    ) -> None:
        say(session, "not_suspicious", source="opnsense")
        store(
            session,
            settings,
            alert(n=1, source="opnsense", connection="api", severity=Severity.CRITICAL),
            alert(
                NOW + timedelta(minutes=1),
                n=2,
                severity=Severity.LOW,
                signature="sshd: failed",
                dst_address="192.168.1.21",
            ),
        )

        run(session)

        (incident,) = incidents(session)
        assert incident.verdict is None
        assert incident.signal_count == 2
        assert incident.verdict_counts == {"not_suspicious": 1}
        assert incident.severity == Severity.LOW
        assert incident.top_summary == "sshd: failed"
        assert incident.sources == ["wazuh"]
        assert [str(address) for address in incident.addresses] == [ATTACKER, "192.168.1.21"]
        assert incident.confidence == 10
        assert [reason["rule"] for reason in incident.reasons] == ["strongest", "muted"]
        assert incident.first_seen_at == NOW
        assert incident.last_seen_at == NOW + timedelta(minutes=1)

    def test_signals_called_fine_after_one_that_counts_change_nothing_but_the_count(
        self, session: Session, settings: Settings
    ) -> None:
        say(session, "not_suspicious", source="crowdsec")
        store(
            session,
            settings,
            alert(n=1, severity=Severity.LOW),
            new_event(
                source="crowdsec",
                connection="lapi",
                kind="decision",
                severity=Severity.CRITICAL,
                occurred_at=NOW + timedelta(minutes=1),
                identity=("ban-1",),
                summary="Ban for ssh-bruteforce",
                src_address=ATTACKER,
                dst_address="192.168.1.21",
            ),
        )

        run(session)

        (incident,) = incidents(session)
        assert incident.signal_count == 2
        assert incident.severity == Severity.LOW
        assert incident.sources == ["wazuh"]
        assert not incident.banned
        assert [str(address) for address in incident.addresses] == [ATTACKER, DEVICE]
        assert incident.confidence == 10
        # They are still part of when it went on.
        assert incident.last_seen_at == NOW + timedelta(minutes=1)

    def test_a_signal_called_a_threat_makes_the_incident_certain(
        self, session: Session, settings: Settings
    ) -> None:
        say(session, "threat", address=ATTACKER)
        store(session, settings, alert(severity=Severity.LOW))

        run(session)

        (incident,) = incidents(session)
        assert incident.verdict == "threat"
        assert incident.confidence == 100
        assert [reason["rule"] for reason in incident.reasons] == ["strongest", "threat"]

    def test_what_was_said_of_a_device_does_not_hide_an_attack_on_it(
        self, session: Session, settings: Settings
    ) -> None:
        say(session, "not_suspicious", address=DEVICE)
        store(session, settings, alert())

        run(session)

        (incident,) = incidents(session)
        assert incident.verdict is None
        assert incident.confidence == 25

    def test_the_rule_that_names_more_decides(self, session: Session, settings: Settings) -> None:
        say(session, "not_suspicious", address=ATTACKER)
        loud = say(session, "threat", address=ATTACKER, signature="ET SCAN Potential SSH Scan")
        store(session, settings, alert())

        run(session)

        assert signals(session)[0].verdict_rule_id == loud.id
        assert incidents(session)[0].verdict == "threat"

    def test_signals_beyond_what_an_incident_lists_are_judged_and_counted_too(
        self, session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(correlation, "MAX_SIGNALS", 1)
        say(session, "low_priority", signature="ET SCAN Potential SSH Scan")
        store(session, settings, *(alert(NOW + timedelta(minutes=n), n=n) for n in range(3)))

        run(session)

        (incident,) = incidents(session)
        assert incident.verdict_counts == {"low_priority": 3}
        assert incident.verdict == "low_priority"
        assert len(signals(session)) == 1


class TestWhenTheOwnerChangesTheirMind:
    def attack(self, session: Session, settings: Settings) -> Incident:
        store(
            session,
            settings,
            alert(n=1, severity=Severity.HIGH),
            alert(NOW + timedelta(minutes=1), n=2, source="opnsense", connection="api"),
        )
        run(session)
        return incidents(session)[0]

    def reapply(self, session: Session) -> Incident:
        correlation.reapply(session)
        session.commit()
        return incidents(session)[0]

    def test_a_verdict_given_later_applies_to_the_incidents_that_are_going(
        self, session: Session, settings: Settings
    ) -> None:
        before = self.attack(session, settings)
        assert (before.confidence, before.verdict) == (55, None)

        rule = say(session, "not_suspicious", address=ATTACKER)
        after = self.reapply(session)

        assert (after.confidence, after.verdict) == (0, "not_suspicious")
        assert after.verdict_counts == {"not_suspicious": 2}
        assert after.signal_count == 2
        assert {signal.verdict_rule_id for signal in signals(session)} == {rule.id}

    def test_one_that_is_taken_back_counts_again(
        self, session: Session, settings: Settings
    ) -> None:
        say(session, "not_suspicious", address=ATTACKER)
        store(session, settings, alert(severity=Severity.HIGH))
        run(session)
        assert incidents(session)[0].confidence == 0

        session.execute(delete(VerdictRule))
        session.commit()
        after = self.reapply(session)

        assert (after.confidence, after.verdict, after.verdict_counts) == (40, None, {})
        assert signals(session)[0].verdict is None

    def test_one_that_is_changed_is_applied_as_it_now_is(
        self, session: Session, settings: Settings
    ) -> None:
        rule = say(session, "not_suspicious", address=ATTACKER)
        self.attack(session, settings)
        assert incidents(session)[0].verdict == "not_suspicious"

        rule.verdict = "threat"
        session.commit()
        after = self.reapply(session)

        assert (after.confidence, after.verdict) == (100, "threat")

    def test_it_is_worked_out_as_if_the_signals_had_just_come_in(
        self, session: Session, settings: Settings
    ) -> None:
        before = self.attack(session, settings)
        summary = (
            before.severity,
            before.top_source,
            before.top_summary,
            before.sources,
            before.addresses,
            before.confidence,
            before.reasons,
            before.title,
        )

        say(session, "not_suspicious", address="8.8.8.8")
        after = self.reapply(session)

        assert summary == (
            after.severity,
            after.top_source,
            after.top_summary,
            after.sources,
            after.addresses,
            after.confidence,
            after.reasons,
            after.title,
        )

    def test_an_incident_that_is_over_is_left_as_it_was(
        self, session: Session, settings: Settings
    ) -> None:
        before = self.attack(session, settings)
        before.status = "resolved"
        session.commit()

        say(session, "not_suspicious", address=ATTACKER)
        after = self.reapply(session)

        assert (after.confidence, after.verdict, after.status) == (55, None, "resolved")
        assert signals(session)[0].verdict is None

    def test_one_that_is_dismissed_is_judged_again(
        self, session: Session, settings: Settings
    ) -> None:
        before = self.attack(session, settings)
        before.status = "dismissed"
        session.commit()

        say(session, "low_priority", address=ATTACKER)
        after = self.reapply(session)

        assert (after.confidence, after.verdict) == (0, "low_priority")

    def test_an_incident_that_outgrew_its_timeline_keeps_when_it_went_on_until(
        self, session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(correlation, "MAX_SIGNALS", 2)
        store(session, settings, *(alert(NOW + timedelta(minutes=n), n=n) for n in range(4)))
        run(session)

        say(session, "low_priority", address=ATTACKER)
        after = self.reapply(session)

        # Judged by the two it lists, which is all it can be.
        assert after.signal_count == 2
        assert after.verdict_counts == {"low_priority": 2}
        assert after.first_seen_at == NOW
        assert after.last_seen_at == NOW + timedelta(minutes=3)

    def test_a_signal_that_comes_after_is_judged_by_the_rules_as_they_are(
        self, session: Session, settings: Settings
    ) -> None:
        self.attack(session, settings)
        say(session, "not_suspicious", address=ATTACKER)
        self.reapply(session)
        store(session, settings, alert(NOW + 2 * HOUR, n=3, severity=Severity.CRITICAL))

        run(session)

        (incident,) = incidents(session)
        assert incident.signal_count == 3
        assert incident.verdict == "not_suspicious"
        assert incident.confidence == 0


# The next address of the attacker's block.
NEIGHBOUR = "93.184.216.99"
BLOCK = "93.184.216.0/24"


def scan(at: datetime = NOW, n: int = 1, **changes: Any) -> NewEvent:
    return alert(at, n, **{"summary": "A scan", **changes})


def brute(at: datetime = NOW, n: int = 1, **changes: Any) -> NewEvent:
    return alert(at, n, **{"signature": "Brute force on ssh", **changes})


def other(at: datetime = NOW, n: int = 1, **changes: Any) -> NewEvent:
    return alert(at, n, **{"signature": "ET MALWARE Possible C2", "summary": "Beacon", **changes})


class TestOneEpisodeIsOneIncident:
    def test_scans_from_the_neighbouring_addresses_of_a_block_are_one_incident(
        self, session: Session, settings: Settings
    ) -> None:
        store(
            session,
            settings,
            scan(n=1),
            scan(NOW + timedelta(minutes=1), n=2, src_address=NEIGHBOUR),
            scan(NOW + timedelta(minutes=2), n=3, src_address="93.184.216.200"),
        )

        result = run(session)

        assert result == correlation.Result(events=3, created=1, updated=0)
        (incident,) = incidents(session)
        assert incident.subject == ATTACKER
        assert incident.block == BLOCK
        assert incident.signal_count == 3
        assert [str(address) for address in incident.addresses] == [
            ATTACKER,
            DEVICE,
            NEIGHBOUR,
            "93.184.216.200",
        ]
        assert incident.title == f"ET SCAN Potential SSH Scan ({BLOCK})"

    def test_so_are_brute_forces(self, session: Session, settings: Settings) -> None:
        store(
            session,
            settings,
            brute(n=1),
            brute(NOW + timedelta(minutes=1), n=2, src_address=NEIGHBOUR),
        )

        run(session)

        (incident,) = incidents(session)
        assert (incident.activities, incident.signal_count) == (["brute_force"], 2)

    def test_the_neighbour_of_a_scan_that_does_something_else_is_not_one_actor(
        self, session: Session, settings: Settings
    ) -> None:
        store(
            session,
            settings,
            scan(n=1),
            other(NOW + timedelta(minutes=1), n=2, src_address=NEIGHBOUR),
            brute(NOW + timedelta(minutes=2), n=3, src_address="93.184.216.200"),
        )

        assert run(session).created == 3

    def test_an_address_of_another_block_is_not_a_neighbour(
        self, session: Session, settings: Settings
    ) -> None:
        store(
            session,
            settings,
            scan(n=1),
            scan(NOW + timedelta(minutes=1), n=2, src_address="93.184.217.34"),
            scan(NOW + timedelta(minutes=2), n=3, src_address=OTHER_ATTACKER),
        )

        assert run(session).created == 3

    def test_an_address_of_the_owners_network_has_no_neighbours(
        self, session: Session, settings: Settings
    ) -> None:
        store(
            session,
            settings,
            scan(n=1, src_address="192.168.1.30", dst_address="192.168.1.31"),
            scan(
                NOW + timedelta(minutes=1),
                n=2,
                src_address="192.168.1.32",
                dst_address="192.168.1.31",
            ),
        )

        result = run(session)

        assert result.created == 2
        assert {incident.block for incident in incidents(session)} == {None}

    def test_a_neighbour_joins_the_incident_that_is_still_going_not_one_that_is_over(
        self, session: Session, settings: Settings
    ) -> None:
        later = NOW + episode.gap_of("scan") + timedelta(minutes=1)
        store(session, settings, scan(n=1), scan(later, n=2, src_address=NEIGHBOUR))

        assert run(session).created == 2

    def test_a_neighbour_does_not_join_an_incident_that_is_resolved(
        self, session: Session, settings: Settings
    ) -> None:
        store(session, settings, scan(n=1))
        run(session)
        incidents(session)[0].status = "resolved"
        session.commit()
        store(session, settings, scan(NOW + HOUR, n=2, src_address=NEIGHBOUR))

        assert run(session).created == 1

    def test_the_same_address_joins_whatever_it_does_this_time(
        self, session: Session, settings: Settings
    ) -> None:
        store(session, settings, scan(n=1), other(NOW + timedelta(minutes=1), n=2))

        assert run(session).created == 1


class TestWhenAnEpisodeIsOver:
    def test_a_scan_is_over_after_four_hours_of_quiet(
        self, session: Session, settings: Settings
    ) -> None:
        gap = episode.gap_of("scan")
        store(
            session,
            settings,
            scan(n=1),
            scan(NOW + gap, n=2),
            scan(NOW + 2 * gap + timedelta(minutes=1), n=3),
        )

        result = run(session)

        assert result.created == 2
        first, second = incidents(session)
        assert (first.signal_count, second.signal_count) == (2, 1)

    def test_a_brute_force_goes_on_for_longer(self, session: Session, settings: Settings) -> None:
        later = NOW + episode.gap_of("scan") + timedelta(minutes=1)
        store(session, settings, brute(n=1), brute(later, n=2))

        assert run(session).created == 1

    def test_a_new_day_is_a_new_incident_however_steady_the_activity(
        self, session: Session, settings: Settings
    ) -> None:
        every_three_hours = [NOW + timedelta(hours=3 * step) for step in range(10)]
        store(session, settings, *(scan(at, n=n) for n, at in enumerate(every_three_hours[:8])))
        run(session, NOW + 22 * HOUR)
        store(session, settings, *(scan(at, n=n + 8) for n, at in enumerate(every_three_hours[8:])))

        run(session, NOW + 28 * HOUR)

        first, second = incidents(session)
        assert (first.signal_count, first.last_seen_at) == (8, NOW + 21 * HOUR)
        assert (second.signal_count, second.first_seen_at) == (2, NOW + 24 * HOUR)

    def test_a_late_signal_from_before_a_day_old_incident_is_not_held_to_it(
        self, session: Session, settings: Settings
    ) -> None:
        store(session, settings, scan(NOW + 20 * HOUR, n=1))
        run(session, NOW + 21 * HOUR)
        store(session, settings, scan(NOW + 17 * HOUR + timedelta(minutes=30), n=2))

        assert run(session, NOW + 22 * HOUR).created == 0


class TestTheShapeOfAnEpisode:
    def test_it_counts_the_waves_the_ports_and_the_kinds_of_activity(
        self, session: Session, settings: Settings
    ) -> None:
        at = [0, 2, 4, 90, 92, 300]
        store(
            session,
            settings,
            *(
                scan(NOW + timedelta(minutes=minute), n=n, dst_port=port)
                for n, (minute, port) in enumerate(
                    zip(at, [22, 80, 22, 443, None, 8080], strict=True)
                )
            ),
            brute(NOW + timedelta(minutes=301), n=9, dst_port=22),
        )

        run(session)

        (incident,) = incidents(session)
        assert incident.waves == 3
        assert incident.ports == [22, 80, 443, 8080]
        assert incident.activities == ["brute_force", "scan"]

    def test_a_late_signal_in_a_quiet_spell_does_not_start_a_wave(
        self, session: Session, settings: Settings
    ) -> None:
        store(session, settings, scan(n=1), scan(NOW + HOUR, n=2))
        run(session)
        store(session, settings, scan(NOW + timedelta(minutes=30), n=3))

        run(session)

        assert incidents(session)[0].waves == 2

    def test_only_so_many_ports_are_kept(
        self, session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(episode, "MAX_PORTS", 2)
        store(
            session,
            settings,
            *(
                scan(NOW + timedelta(minutes=n), n=n, dst_port=port)
                for n, port in enumerate([1, 2, 3])
            ),
        )

        run(session)

        assert incidents(session)[0].ports == [1, 2]

    def test_what_the_owner_called_fine_adds_nothing_to_it(
        self, session: Session, settings: Settings
    ) -> None:
        say(session, "not_suspicious", signature="ET SCAN Potential SSH Scan")
        store(
            session,
            settings,
            scan(n=1, dst_port=22),
            brute(NOW + timedelta(minutes=1), n=2, dst_port=2222),
        )

        run(session)

        (incident,) = incidents(session)
        assert (incident.activities, incident.ports) == (["brute_force"], [2222])
        # But it came in the time it came in.
        assert incident.signal_count == 2


def legacy(
    session: Session,
    subject: str,
    times: list[datetime],
    *,
    status: str = "open",
    signature: str = "ET SCAN Potential SSH Scan",
    summary: str = "An alert",
    verdict: str | None = None,
    dst_port: int | None = None,
) -> Incident:
    """An incident as it was before episodes were known: none of what they say is worked out."""
    incident = Incident(
        subject=subject,
        title="legacy",
        severity=2,
        confidence=25,
        status=status,
        first_seen_at=min(times),
        last_seen_at=max(times),
        signal_count=len(times),
        sources=["wazuh"],
        addresses=[ip_address(subject)] if subject[0].isdigit() else [],
        top_source="wazuh",
        top_summary="legacy",
        verdict_counts={verdict: len(times)} if verdict else {},
        waves=0,
        status_changed_at=times[0] if status != "open" else None,
    )
    session.add(incident)
    session.flush()
    for number, at in enumerate(times):
        session.add(
            IncidentSignal(
                incident_id=incident.id,
                event_id=incident.id * 1000 + number,
                occurred_at=at,
                source="wazuh",
                kind="alert",
                severity=2,
                summary=summary,
                signature=signature,
                src_address=ip_address(subject) if subject[0].isdigit() else None,
                dst_port=dst_port,
                verdict=verdict,
            )
        )
    session.commit()
    return incident


class TestIncidentsFromBeforeEpisodesWereKnown:
    def test_the_shape_of_each_is_worked_out_from_its_signals(self, session: Session) -> None:
        legacy(
            session,
            ATTACKER,
            [NOW, NOW + timedelta(minutes=2), NOW + HOUR],
            dst_port=22,
        )
        legacy(session, "rule:wazuh:Something", [NOW], signature="Something")

        result = run(session)

        assert result == correlation.Result()
        attacker, rule = incidents(session)
        assert (attacker.block, attacker.waves, attacker.activities, attacker.ports) == (
            BLOCK,
            2,
            ["scan"],
            [22],
        )
        assert (rule.block, rule.waves, rule.activities, rule.ports) == (None, 1, [], [])

    def test_it_is_done_once(self, session: Session) -> None:
        legacy(session, ATTACKER, [NOW])
        run(session)
        incidents(session)[0].waves = 5
        session.commit()

        run(session)

        assert incidents(session)[0].waves == 5

    def test_a_resolved_one_is_shaped_but_stays_as_it_is(self, session: Session) -> None:
        legacy(session, ATTACKER, [NOW], status="resolved")
        legacy(session, NEIGHBOUR, [NOW + HOUR], status="resolved")

        result = run(session)

        assert result.merged == 0
        assert [incident.waves for incident in incidents(session)] == [1, 1]

    def test_what_the_owner_called_fine_is_what_they_are_described_by_when_nothing_else_is(
        self, session: Session
    ) -> None:
        legacy(session, ATTACKER, [NOW], verdict="not_suspicious", dst_port=22)

        run(session)

        (incident,) = incidents(session)
        assert (incident.activities, incident.ports) == (["scan"], [22])

    def test_an_incident_with_no_signals_is_one_wave(self, session: Session) -> None:
        legacy(session, ATTACKER, [NOW])
        session.execute(delete(IncidentSignal))
        session.commit()

        run(session)

        assert incidents(session)[0].waves == 1

    def test_the_ones_that_are_one_episode_are_merged(self, session: Session) -> None:
        legacy(session, ATTACKER, [NOW, NOW + HOUR], dst_port=22)
        legacy(session, NEIGHBOUR, [NOW + 3 * HOUR], dst_port=80)
        legacy(session, "93.184.216.200", [NOW + 5 * HOUR], dst_port=443)

        result = run(session)

        assert result == correlation.Result(merged=2)
        (incident,) = incidents(session)
        assert incident.subject == ATTACKER
        assert incident.signal_count == 4
        assert (incident.first_seen_at, incident.last_seen_at) == (NOW, NOW + 5 * HOUR)
        assert incident.ports == [22, 80, 443]
        assert incident.waves == 4
        assert incident.title == f"legacy ({BLOCK})" or BLOCK in incident.title
        assert {signal.incident_id for signal in signals(session)} == {incident.id}

    def test_the_one_that_began_first_keeps_the_rest_whichever_was_listed_first(
        self, session: Session
    ) -> None:
        later = legacy(session, NEIGHBOUR, [NOW + 3 * HOUR])
        first = legacy(session, ATTACKER, [NOW])

        run(session)

        (incident,) = incidents(session)
        assert incident.id == first.id
        assert incident.id != later.id

    def test_it_does_not_join_what_is_further_apart_than_the_gap_or_a_day_long_together(
        self, session: Session
    ) -> None:
        legacy(session, ATTACKER, [NOW, NOW + 20 * HOUR])
        legacy(session, NEIGHBOUR, [NOW + 22 * HOUR, NOW + 25 * HOUR])
        legacy(session, "93.184.216.200", [NOW + 40 * HOUR])

        result = run(session, NOW + 41 * HOUR)

        assert result.merged == 0
        assert len(incidents(session)) == 3

    def test_nor_what_has_nothing_in_common(self, session: Session) -> None:
        legacy(session, ATTACKER, [NOW])
        legacy(session, NEIGHBOUR, [NOW + HOUR], signature="ET MALWARE Possible C2")
        legacy(session, "93.184.216.200", [NOW + HOUR], signature="Brute force on ssh")

        assert run(session).merged == 0

    def test_nor_what_someone_has_a_say_in_that_the_other_has_not(self, session: Session) -> None:
        legacy(session, ATTACKER, [NOW], status="investigating")
        legacy(session, NEIGHBOUR, [NOW + HOUR])

        result = run(session)

        assert result.merged == 0
        assert [incident.status for incident in incidents(session)] == ["investigating", "open"]

    def test_but_two_that_are_being_looked_at_are_one_and_keep_the_latest_change_of_status(
        self, session: Session
    ) -> None:
        legacy(session, ATTACKER, [NOW], status="investigating")
        legacy(session, NEIGHBOUR, [NOW + HOUR], status="investigating")

        run(session)

        (incident,) = incidents(session)
        assert incident.status == "investigating"
        assert incident.status_changed_at == NOW + HOUR
        assert incident.created_at <= incident.updated_at

    def test_nor_two_that_have_not_been_given_a_change_of_status_lose_none(
        self, session: Session
    ) -> None:
        legacy(session, ATTACKER, [NOW])
        legacy(session, NEIGHBOUR, [NOW + HOUR])

        run(session)

        assert incidents(session)[0].status_changed_at is None


class TestMergingKeepsWhatWasSaid:
    def test_the_verdicts_on_the_signals_of_both_stay_on_them(
        self, session: Session, settings: Settings
    ) -> None:
        rule = say(session, "low_priority", address=NEIGHBOUR)
        store(
            session,
            settings,
            scan(n=1),
            scan(NOW + 8 * HOUR, n=2, src_address=NEIGHBOUR),
        )
        run(session, NOW + 9 * HOUR)
        assert len(incidents(session)) == 2

        # What was missing arrives late and joins the later one, which makes them one episode.
        store(session, settings, scan(NOW + 4 * HOUR, n=3))
        result = run(session, NOW + 10 * HOUR)

        assert result.merged == 1
        (incident,) = incidents(session)
        assert incident.signal_count == 3
        assert incident.verdict_counts == {"low_priority": 1}
        assert {(signal.src_address, signal.verdict) for signal in signals(session)} == {
            (ip_address(ATTACKER), None),
            (ip_address(NEIGHBOUR), "low_priority"),
        }
        assert [signal.verdict_rule_id for signal in signals(session) if signal.verdict] == [
            rule.id
        ]

    def test_what_an_incident_counted_but_did_not_list_is_still_counted(
        self, session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(correlation, "MAX_SIGNALS", 1)
        store(
            session,
            settings,
            scan(n=1),
            scan(NOW + timedelta(minutes=1), n=2),
            scan(NOW + 8 * HOUR, n=3, src_address=NEIGHBOUR),
            scan(NOW + 8 * HOUR + timedelta(minutes=1), n=4, src_address=NEIGHBOUR),
        )
        run(session, NOW + 9 * HOUR)
        store(session, settings, scan(NOW + 4 * HOUR, n=5))

        run(session, NOW + 10 * HOUR)

        (incident,) = incidents(session)
        assert incident.signal_count == 5
        assert len(signals(session)) == 2
