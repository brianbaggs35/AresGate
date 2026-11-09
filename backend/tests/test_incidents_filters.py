from dataclasses import replace
from datetime import timedelta
from ipaddress import ip_address
from typing import Any

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.events.event import Severity
from app.incidents import attention, filters
from app.incidents import engine as correlation
from app.incidents.filters import Filters
from app.models import Event, Incident, IncidentSignal, NoiseSettings, VerdictRule
from tests.test_incidents_engine import (
    ATTACKER,
    BLOCK,
    DEVICE,
    HOUR,
    NEIGHBOUR,
    NOW,
    alert,
    incidents,
    run,
    say,
    scan,
    signals,
    store,
)

OTHER_DEVICE = "192.168.1.30"


def keep(session: Session, **changes: Any) -> None:
    """The owner saves their filters, with these settings changed and the rest as they are."""
    filters.save(session, replace(filters.load(session), **changes))
    session.commit()


class TestWhatIsInside:
    @pytest.mark.parametrize(
        "address",
        [
            "10.1.2.3",
            "172.16.0.9",
            "172.31.255.1",
            "192.168.1.20",
            "100.64.0.1",
            "169.254.7.7",
            "fd12:3456::1",
            "fe80::1",
        ],
    )
    def test_the_addresses_that_can_only_be_on_a_network_of_the_owners(self, address: str) -> None:
        assert filters.inside(ip_address(address))

    @pytest.mark.parametrize("address", ["93.184.216.34", "8.8.8.8", "172.32.0.1", "2606:4700::1"])
    def test_and_the_ones_that_are_not(self, address: str) -> None:
        assert not filters.inside(ip_address(address))

    def test_nothing_is_not(self) -> None:
        assert not filters.inside(None)

    def test_sql_and_python_agree(self, session: Session, settings: Settings) -> None:
        named = ["10.1.2.3", "100.64.0.1", "fd12:3456::1", "fe80::1", ATTACKER, "2606:4700::1"]
        store(
            session,
            settings,
            *(alert(n=n, src_address=address) for n, address in enumerate(named)),
        )

        rows = session.execute(
            select(Event.src_address, filters.inside_clause(Event.src_address))
        ).all()

        assert len(rows) == len(named)
        assert {(str(address), found) for address, found in rows} == {
            (address, filters.inside(ip_address(address))) for address in named
        }


def signal(**changes: Any) -> IncidentSignal:
    fields: dict[str, Any] = {
        "source": "wazuh",
        "kind": "alert",
        "severity": int(Severity.MEDIUM),
        "src_address": ip_address(ATTACKER),
        "dst_address": ip_address(DEVICE),
        **changes,
    }
    return IncidentSignal(**fields)


class TestJudging:
    def test_nothing_is_set_aside_until_the_owner_says(self) -> None:
        assert filters.judge(signal(severity=1), Filters()) is None
        assert filters.judge(signal(src_address=ip_address(OTHER_DEVICE)), Filters()) is None

    @pytest.mark.parametrize(
        ("severity", "reason"),
        [(1, "severity"), (2, "severity"), (3, None), (4, None)],
    )
    def test_a_program_can_be_asked_to_count_only_what_is_serious_enough(
        self, severity: int, reason: str | None
    ) -> None:
        found = Filters(source_floors={"wazuh": int(Severity.HIGH)})

        assert filters.judge(signal(severity=severity), found) == reason

    def test_a_floor_is_about_the_program_it_is_set_for(self) -> None:
        found = Filters(source_floors={"ntopng": int(Severity.CRITICAL)})

        assert filters.judge(signal(source="wazuh", severity=1), found) is None
        assert filters.judge(signal(source="ntopng", severity=3), found) == "severity"

    def test_between_two_addresses_inside_is_set_aside_when_asked(self) -> None:
        found = Filters(quiet_inside=True)

        assert filters.judge(signal(src_address=ip_address(OTHER_DEVICE)), found) == "inside"

    @pytest.mark.parametrize(
        "changes",
        [
            {},
            {"dst_address": None},
            {"src_address": None},
            {"src_address": ip_address(OTHER_DEVICE), "dst_address": ip_address(ATTACKER)},
        ],
    )
    def test_but_not_when_one_end_is_outside_or_unknown(self, changes: dict[str, Any]) -> None:
        assert filters.judge(signal(**changes), Filters(quiet_inside=True)) is None

    def test_a_ban_is_never_set_aside(self) -> None:
        found = Filters(quiet_inside=True, source_floors={"crowdsec": int(Severity.CRITICAL)})
        ban = signal(
            source="crowdsec",
            kind="decision",
            severity=1,
            src_address=ip_address(OTHER_DEVICE),
        )

        assert filters.judge(ban, found) is None

    def test_a_signal_that_is_both_is_set_aside_for_its_severity(self) -> None:
        found = Filters(quiet_inside=True, source_floors={"wazuh": int(Severity.HIGH)})

        assert (
            filters.judge(signal(severity=1, src_address=ip_address(OTHER_DEVICE)), found)
            == "severity"
        )


class TestKeepingThem:
    def test_the_defaults_apply_until_they_are_saved(self, session: Session) -> None:
        assert filters.load(session) == Filters(35, False, {})
        assert filters.load(session).confidence_floor == filters.DEFAULT_FLOOR

    def test_what_is_saved_is_what_is_loaded(self, session: Session) -> None:
        saved = Filters(50, True, {"wazuh": 3})

        assert filters.save(session, saved)
        session.commit()

        assert filters.load(session) == saved
        assert session.scalars(select(NoiseSettings)).one().id == 1

    def test_saving_again_changes_the_one_row(self, session: Session) -> None:
        keep(session, quiet_inside=True)

        assert filters.save(session, Filters(35, False, {"ntopng": 2}))
        session.commit()

        assert filters.load(session) == Filters(35, False, {"ntopng": 2})
        assert len(list(session.scalars(select(NoiseSettings)))) == 1

    def test_saving_what_is_already_so_changes_nothing(self, session: Session) -> None:
        assert not filters.save(session, Filters())
        assert session.scalars(select(NoiseSettings)).first() is None

        keep(session, confidence_floor=60)

        assert not filters.save(session, Filters(60, False, {}))


class TestWhatTheEngineDoes:
    def test_a_signal_under_the_floor_is_kept_and_counted_but_the_incident_is_sure_of_nothing(
        self, session: Session, settings: Settings
    ) -> None:
        keep(session, source_floors={"wazuh": int(Severity.HIGH)})
        store(session, settings, alert(severity=Severity.MEDIUM))

        run(session)

        (incident,) = incidents(session)
        (kept,) = signals(session)
        assert kept.filtered_by == "severity"
        assert kept.verdict is None
        assert (incident.signal_count, incident.filtered_count) == (1, 1)
        assert (incident.confidence, incident.verdict) == (0, None)
        assert [reason["rule"] for reason in incident.reasons] == ["filtered"]
        assert incident.verdict_counts == {}

    def test_one_that_counts_describes_the_incident_and_the_other_is_left_out(
        self, session: Session, settings: Settings
    ) -> None:
        keep(session, source_floors={"wazuh": int(Severity.HIGH)})
        store(
            session,
            settings,
            alert(n=1, severity=Severity.HIGH),
            alert(NOW + timedelta(minutes=1), n=2, severity=Severity.LOW, summary="Low noise"),
            alert(NOW + timedelta(minutes=2), n=3, source="opnsense", severity=Severity.CRITICAL),
        )

        run(session)

        (incident,) = incidents(session)
        assert incident.signal_count == 2
        assert incident.filtered_count == 1
        assert incident.severity == Severity.CRITICAL
        assert incident.sources == ["opnsense", "wazuh"]
        assert [signal.filtered_by for signal in signals(session)] == [None, "severity", None]
        assert incident.reasons[-1]["rule"] == "filtered"
        assert incident.reasons[-1]["text"].startswith("Left out: 1 of its 2 signals")

    def test_what_is_between_two_devices_is_set_aside_when_asked(
        self, session: Session, settings: Settings
    ) -> None:
        keep(session, quiet_inside=True)
        store(
            session,
            settings,
            alert(n=1, src_address=OTHER_DEVICE, dst_address=DEVICE),
            alert(NOW + timedelta(minutes=1), n=2),
        )

        run(session)

        assert {(str(s.src_address), s.filtered_by) for s in signals(session)} == {
            (OTHER_DEVICE, "inside"),
            (ATTACKER, None),
        }
        outside, inside = sorted(incidents(session), key=lambda item: item.subject != ATTACKER)
        assert (outside.confidence, outside.filtered_count) == (25, 0)
        assert (inside.confidence, inside.filtered_count) == (0, 1)

    def test_a_ban_between_two_devices_still_counts(
        self, session: Session, settings: Settings
    ) -> None:
        keep(session, quiet_inside=True)
        store(
            session,
            settings,
            alert(source="crowdsec", kind="decision", src_address=OTHER_DEVICE),
        )

        run(session)

        (incident,) = incidents(session)
        assert incident.banned
        assert (incident.filtered_count, incident.confidence) == (0, 45)

    def test_a_verdict_outranks_a_filter(self, session: Session, settings: Settings) -> None:
        keep(session, source_floors={"wazuh": int(Severity.CRITICAL)})
        say(session, "not_suspicious", address=ATTACKER)
        store(session, settings, alert(n=1), alert(NOW + HOUR / 2, n=2, src_address=NEIGHBOUR))

        run(session)

        verdicts = {str(s.src_address): (s.verdict, s.filtered_by) for s in signals(session)}
        assert verdicts == {
            ATTACKER: ("not_suspicious", None),
            NEIGHBOUR: (None, "severity"),
        }
        assert sum(item.filtered_count for item in incidents(session)) == 1

    def test_a_threat_is_not_set_aside_whatever_the_filters_say(
        self, session: Session, settings: Settings
    ) -> None:
        keep(session, source_floors={"wazuh": int(Severity.CRITICAL)})
        say(session, "threat", address=ATTACKER)
        store(session, settings, alert(severity=Severity.LOW))

        run(session)

        (incident,) = incidents(session)
        (kept,) = signals(session)
        assert (kept.verdict, kept.filtered_by) == ("threat", None)
        assert (incident.confidence, incident.filtered_count) == (100, 0)

    def test_an_incident_is_described_by_the_signals_that_are_not_set_aside_once_one_comes(
        self, session: Session, settings: Settings
    ) -> None:
        keep(session, source_floors={"wazuh": int(Severity.HIGH)})
        store(session, settings, alert(n=1, severity=Severity.LOW, dst_port=22))
        run(session)
        assert incidents(session)[0].ports == [22]

        store(session, settings, alert(NOW + HOUR / 2, n=2, severity=Severity.HIGH, dst_port=80))
        run(session)

        (incident,) = incidents(session)
        assert incident.ports == [80]
        assert (incident.severity, incident.signal_count, incident.filtered_count) == (3, 2, 1)

    def test_nothing_changes_for_incidents_when_nothing_is_set(
        self, session: Session, settings: Settings
    ) -> None:
        store(session, settings, alert(severity=Severity.LOW), alert(NOW, n=2, src_address=DEVICE))

        run(session)

        assert all(item.filtered_count == 0 for item in incidents(session))
        assert all(item.filtered_by is None for item in signals(session))


class TestWhenTheOwnerChangesTheFilters:
    def attack(self, session: Session, settings: Settings) -> Incident:
        store(
            session,
            settings,
            alert(n=1, severity=Severity.HIGH),
            alert(NOW + timedelta(minutes=1), n=2, severity=Severity.LOW),
        )
        run(session)
        return incidents(session)[0]

    def reapply(self, session: Session) -> Incident:
        correlation.reapply(session)
        session.commit()
        return incidents(session)[0]

    def test_a_filter_set_later_applies_to_the_incidents_that_are_going(
        self, session: Session, settings: Settings
    ) -> None:
        before = self.attack(session, settings)
        assert (before.confidence, before.filtered_count) == (40, 0)

        keep(session, source_floors={"wazuh": int(Severity.CRITICAL)})
        after = self.reapply(session)

        assert (after.confidence, after.filtered_count, after.signal_count) == (0, 2, 2)
        assert {signal.filtered_by for signal in signals(session)} == {"severity"}

    def test_one_that_is_taken_off_counts_again(self, session: Session, settings: Settings) -> None:
        keep(session, source_floors={"wazuh": int(Severity.HIGH)})
        self.attack(session, settings)
        assert incidents(session)[0].filtered_count == 1

        keep(session, source_floors={})
        after = self.reapply(session)

        assert (after.confidence, after.filtered_count) == (40, 0)
        assert [signal.filtered_by for signal in signals(session)] == [None, None]

    def test_an_incident_that_is_over_keeps_what_was_said_at_the_time(
        self, session: Session, settings: Settings
    ) -> None:
        keep(session, source_floors={"wazuh": int(Severity.HIGH)})
        self.attack(session, settings)
        incidents(session)[0].status = "resolved"
        session.commit()

        keep(session, source_floors={})
        after = self.reapply(session)

        assert (after.confidence, after.filtered_count) == (40, 1)

    def test_a_verdict_given_later_takes_the_signal_from_the_filter(
        self, session: Session, settings: Settings
    ) -> None:
        keep(session, source_floors={"wazuh": int(Severity.HIGH)})
        self.attack(session, settings)

        say(session, "low_priority", address=ATTACKER)
        after = self.reapply(session)

        assert after.filtered_count == 0
        assert after.verdict_counts == {"low_priority": 2}

    def test_the_verdicts_behave_as_before_when_the_verdict_goes(
        self, session: Session, settings: Settings
    ) -> None:
        keep(session, source_floors={"wazuh": int(Severity.HIGH)})
        say(session, "low_priority", address=ATTACKER)
        self.attack(session, settings)

        session.execute(delete(VerdictRule))
        session.commit()
        after = self.reapply(session)

        assert (after.filtered_count, after.verdict_counts) == (1, {})


class TestMergingKeepsWhatWasSet:
    def test_the_signals_set_aside_in_both_are_counted_in_the_one_they_become(
        self, session: Session, settings: Settings
    ) -> None:
        keep(session, source_floors={"wazuh": int(Severity.HIGH)})
        store(
            session,
            settings,
            scan(n=1, severity=Severity.HIGH),
            scan(NOW + 8 * HOUR, n=2, src_address=NEIGHBOUR, severity=Severity.LOW),
        )
        run(session, NOW + 9 * HOUR)
        assert len(incidents(session)) == 2

        store(session, settings, scan(NOW + 4 * HOUR, n=3, severity=Severity.LOW))
        result = run(session, NOW + 10 * HOUR)

        assert result.merged == 1
        (incident,) = incidents(session)
        assert incident.block == BLOCK
        assert (incident.signal_count, incident.filtered_count) == (3, 2)
        assert incident.severity == Severity.HIGH


class TestIncidentsFromBeforeEpisodesWereKnown:
    def test_a_signal_set_aside_does_not_shape_the_incident(self, session: Session) -> None:
        incident = Incident(
            subject=ATTACKER,
            title="legacy",
            severity=2,
            confidence=25,
            status="open",
            first_seen_at=NOW,
            last_seen_at=NOW + HOUR,
            signal_count=2,
            sources=["wazuh"],
            top_source="wazuh",
            top_summary="x",
            waves=0,
        )
        session.add(incident)
        session.flush()
        for n, (port, aside) in enumerate([(22, None), (80, "severity")]):
            session.add(
                IncidentSignal(
                    incident_id=incident.id,
                    event_id=n,
                    occurred_at=NOW + n * HOUR,
                    source="wazuh",
                    kind="alert",
                    severity=2,
                    summary="x",
                    signature="ET SCAN Potential SSH Scan",
                    src_address=ip_address(ATTACKER),
                    dst_port=port,
                    filtered_by=aside,
                )
            )
        session.commit()

        run(session)

        assert incidents(session)[0].ports == [22]


class TestHowManyStandEachWay:
    def test_the_incidents_going_on_are_counted_by_how_they_stand(
        self, session: Session, settings: Settings
    ) -> None:
        say(session, "not_suspicious", address="8.8.8.8")
        store(
            session,
            settings,
            alert(n=1, severity=Severity.HIGH),
            alert(n=2, src_address="1.1.1.1", severity=Severity.LOW),
            alert(n=3, src_address="8.8.8.8", severity=Severity.CRITICAL),
            alert(n=4, src_address="9.9.9.9", severity=Severity.HIGH),
        )
        run(session)
        incidents(session)[-1].status = "dismissed"
        session.commit()

        found = attention.tally(session, 35)

        assert (found.muted, found.unsure, found.needs_you, found.urgent) == (1, 1, 1, 0)
        assert found.active == 3
        assert attention.tally(session, 40).needs_you == 1
        assert attention.tally(session, 41).unsure == 2
