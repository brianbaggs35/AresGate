"""Chains: an exploit aimed at a device, and the device calling out soon after, are one attack."""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.config import Settings
from app.events.event import NewEvent, Severity
from app.events.store import record as record_events
from app.incidents import attention
from app.incidents import engine as correlation
from app.models import Incident, IncidentChain, IncidentSignal
from app.threats import chains
from tests.helpers import new_event

NOW = datetime(2026, 11, 11, 6, 0, tzinfo=UTC)
LATER = NOW + timedelta(hours=12)
ATTACKER = "93.184.216.34"
OTHER_ATTACKER = "8.8.8.8"
SERVER = "8.8.4.4"
DEVICE = "192.168.1.20"
OTHER_DEVICE = "192.168.1.21"
EXPLOIT = "ET EXPLOIT Apache Log4j RCE Attempt (CVE-2021-44228)"
BEACON = "ET MALWARE Cobalt Strike Beacon Observed"
CALL = "ET POLICY Unusual outbound connection"


def exploit(at: datetime = NOW, n: int = 1, **changes: Any) -> NewEvent:
    """An outside address trying a flaw on a device."""
    fields: dict[str, Any] = {
        "occurred_at": at,
        "identity": (f"exploit-{n}",),
        "src_address": ATTACKER,
        "dst_address": DEVICE,
        "signature": EXPLOIT,
        "severity": Severity.HIGH,
    }
    return new_event(**{**fields, **changes})


def call_out(
    after: timedelta = timedelta(minutes=20), n: int = 1, words: str = BEACON, **changes: Any
) -> NewEvent:
    """The device sending something to an address on the internet."""
    fields: dict[str, Any] = {
        "occurred_at": NOW + after,
        "identity": (f"call-{n}",),
        "src_address": DEVICE,
        "dst_address": SERVER,
        "signature": words,
        "severity": Severity.HIGH,
    }
    return new_event(**{**fields, **changes})


def file(session: Session, settings: Settings, *events: NewEvent) -> list[Incident]:
    """Stores the events as collectors would have, files them into incidents and links the
    chains, as a run of the worker does."""
    for event in events:
        record_events(session, settings, [event], event.occurred_at)
    session.commit()
    correlation.correlate(session, LATER)
    chains.link(session, LATER)
    session.commit()
    session.expire_all()
    return list(session.scalars(select(Incident).order_by(Incident.id)))


def by_subject(found: list[Incident]) -> dict[str, Incident]:
    return {each.subject: each for each in found}


class TestAnAttackAcrossTwoDevices:
    def test_an_exploit_and_a_beacon_from_the_device_are_a_confirmed_chain(
        self, session: Session, settings: Settings
    ) -> None:
        found = by_subject(file(session, settings, exploit(), call_out()))

        attacker, callout = found[ATTACKER], found[SERVER]
        assert attacker.chain_id is not None
        assert attacker.chain_id == callout.chain_id
        assert (attacker.chain_role, attacker.chain_link) == ("attacker", "confirmed")
        assert (callout.chain_role, callout.chain_link) == ("callout", "confirmed")
        assert attacker.chain_reason is not None
        assert f"aimed at {DEVICE}" in attacker.chain_reason
        assert callout.chain_reason is not None
        assert "did what a device that was taken over does" in callout.chain_reason
        assert "20 minutes after the attack" in callout.chain_reason
        chain = session.get_one(IncidentChain, attacker.chain_id)
        assert chain.device == DEVICE
        assert chain.confirmed
        assert chain.steps == 2
        assert chain.first_seen_at == NOW
        assert chain.last_seen_at == NOW + timedelta(minutes=20)

    def test_the_whole_chain_is_a_threat_however_unsure_the_rules_are(
        self, session: Session, settings: Settings
    ) -> None:
        found = file(session, settings, exploit(), call_out())

        assert {attention.lane_of(each) for each in found} == {attention.Lane.THREAT}

    def test_a_device_that_only_called_out_is_an_inferred_link_and_says_so(
        self, session: Session, settings: Settings
    ) -> None:
        found = by_subject(
            file(session, settings, exploit(), call_out(timedelta(minutes=45), words=CALL))
        )

        callout = found[SERVER]
        assert (callout.chain_role, callout.chain_link) == ("callout", "inferred")
        assert callout.chain_reason is not None
        assert "this link is inferred" in callout.chain_reason
        assert "45 minutes after the attack" in callout.chain_reason
        assert found[ATTACKER].chain_link == "confirmed"
        chain = session.get_one(IncidentChain, callout.chain_id)
        assert not chain.confirmed

    def test_a_later_sign_that_it_worked_confirms_an_inferred_link(
        self, session: Session, settings: Settings
    ) -> None:
        first = file(session, settings, exploit(), call_out(words=CALL))
        assert by_subject(first)[SERVER].chain_link == "inferred"

        found = by_subject(file(session, settings, call_out(timedelta(minutes=50), n=2)))

        assert found[SERVER].chain_link == "confirmed"
        assert "50 minutes after the attack" in (found[SERVER].chain_reason or "")
        assert session.scalars(select(IncidentChain)).one().confirmed

    def test_a_sign_that_it_worked_from_before_the_attack_does_not_confirm_it(
        self, session: Session, settings: Settings
    ) -> None:
        before = call_out(-timedelta(minutes=10), n=2)
        after = call_out(timedelta(minutes=20), words=CALL)

        found = by_subject(file(session, settings, exploit(), before, after))

        assert found[SERVER].chain_link == "inferred"

    def test_it_is_said_in_moments_and_in_hours(self) -> None:
        assert chains.how_long(timedelta(seconds=20)) == "moments"
        assert chains.how_long(timedelta(minutes=1)) == "1 minute"
        assert chains.how_long(timedelta(hours=3)) == "3 hours"

    def test_two_attackers_of_one_device_are_one_chain(
        self, session: Session, settings: Settings
    ) -> None:
        second = exploit(NOW + timedelta(minutes=5), n=2, src_address=OTHER_ATTACKER)

        found = file(session, settings, exploit(), second, call_out())

        assert len({each.chain_id for each in found}) == 1
        assert sorted(each.chain_role or "" for each in found) == [
            "attacker",
            "attacker",
            "callout",
        ]
        assert session.scalars(select(IncidentChain)).one().steps == 3

    def test_a_chain_is_linked_again_without_changing_anything(
        self, session: Session, settings: Settings
    ) -> None:
        file(session, settings, exploit(), call_out())

        assert chains.link(session, LATER) == 0

    def test_an_attacker_in_the_chain_of_one_device_is_not_taken_into_another(
        self, session: Session, settings: Settings
    ) -> None:
        elsewhere = exploit(n=2, dst_address=OTHER_DEVICE)
        other_call = call_out(timedelta(minutes=30), n=2, src_address=OTHER_DEVICE)

        found = by_subject(file(session, settings, exploit(), elsewhere, call_out(), other_call))

        assert found[ATTACKER].chain_role == "attacker"
        assert session.get_one(IncidentChain, found[ATTACKER].chain_id).device == DEVICE
        assert session.scalars(select(IncidentChain)).one().steps == 2

    def test_a_callout_in_the_chain_of_another_device_is_left_there(
        self, session: Session, settings: Settings
    ) -> None:
        other_exploit = exploit(n=2, src_address=OTHER_ATTACKER, dst_address=OTHER_DEVICE)
        other_call = call_out(timedelta(minutes=30), n=2, src_address=OTHER_DEVICE)
        file(session, settings, exploit(), call_out(), other_exploit)

        found = by_subject(file(session, settings, other_call))

        assert session.get_one(IncidentChain, found[SERVER].chain_id).device == DEVICE
        assert found[OTHER_ATTACKER].chain_id is None

    def test_a_chain_whose_step_has_gone_is_dropped(
        self, session: Session, settings: Settings
    ) -> None:
        found = by_subject(file(session, settings, exploit(), call_out()))
        session.execute(delete(Incident).where(Incident.id == found[SERVER].id))
        session.commit()

        chains.link(session, LATER)
        session.commit()
        session.expire_all()

        assert session.scalars(select(IncidentChain)).all() == []
        assert session.get_one(Incident, found[ATTACKER].id).chain_id is None
        assert session.get_one(Incident, found[ATTACKER].id).chain_role is None


class TestNothingIsLinkedThatIsNotThere:
    def test_scanning_alone_is_not_an_attack_on_the_device(
        self, session: Session, settings: Settings
    ) -> None:
        scan = exploit(signature="ET SCAN Potential SSH Scan")

        found = file(session, settings, scan, call_out())

        assert [each.chain_id for each in found] == [None, None]

    def test_a_call_out_before_the_attack_is_not_what_followed_it(
        self, session: Session, settings: Settings
    ) -> None:
        found = file(session, settings, exploit(NOW + timedelta(minutes=30)), call_out())

        assert [each.chain_id for each in found] == [None, None]

    def test_a_call_out_long_after_the_attack_is_not_what_followed_it(
        self, session: Session, settings: Settings
    ) -> None:
        found = file(session, settings, exploit(), call_out(chains.WINDOW + timedelta(minutes=1)))

        assert [each.chain_id for each in found] == [None, None]

    def test_an_exploit_aimed_at_another_device_is_not_this_ones(
        self, session: Session, settings: Settings
    ) -> None:
        found = file(session, settings, exploit(dst_address=OTHER_DEVICE), call_out())

        assert [each.chain_id for each in found] == [None, None]

    def test_a_call_out_that_is_not_serious_is_not_enough(
        self, session: Session, settings: Settings
    ) -> None:
        found = file(session, settings, exploit(), call_out(words=CALL, severity=Severity.LOW))

        assert [each.chain_id for each in found] == [None, None]

    def test_traffic_between_two_devices_on_the_network_is_not_a_call_out(
        self, session: Session, settings: Settings
    ) -> None:
        found = file(session, settings, exploit(), call_out(dst_address=OTHER_DEVICE))

        assert [each.chain_id for each in found] == [None, None]

    def test_an_exploit_from_inside_the_network_is_not_an_attack_from_outside(
        self, session: Session, settings: Settings
    ) -> None:
        found = file(session, settings, exploit(src_address=OTHER_DEVICE), call_out())

        assert [each.chain_id for each in found if each.chain_id] == []

    def test_a_signal_the_owner_called_quiet_is_not_used(
        self, session: Session, settings: Settings
    ) -> None:
        file(session, settings, exploit(), call_out(), exploit(n=9, src_address=OTHER_ATTACKER))
        session.execute(update(IncidentSignal).values(verdict="not_suspicious", filtered_by=None))
        session.execute(delete(IncidentChain))
        session.commit()

        assert chains.link(session, LATER) == 0
        assert session.scalars(select(IncidentChain)).all() == []

    def test_a_signal_a_noise_filter_set_aside_is_not_used(
        self, session: Session, settings: Settings
    ) -> None:
        file(session, settings, exploit(), call_out())
        session.execute(update(IncidentSignal).values(filtered_by="inside"))
        session.execute(delete(IncidentChain))
        session.commit()

        assert chains.link(session, LATER) == 0

    def test_an_incident_that_has_been_over_a_long_time_is_not_looked_at(
        self, session: Session, settings: Settings
    ) -> None:
        file(session, settings, exploit(), call_out())
        session.execute(delete(IncidentChain))
        session.commit()

        assert chains.link(session, LATER + timedelta(days=3)) == 0
