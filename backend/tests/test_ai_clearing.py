"""The AI clears a false positive: when it may give a verdict, what the verdict says of who gave
it, and that the owner can take it back."""

from dataclasses import replace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import clearing
from app.audit import Action
from app.config import Settings
from app.events.event import Severity
from app.incidents import attention
from app.models import (
    AiClearVeto,
    AiTriage,
    AuditEvent,
    Incident,
    IncidentChain,
    IncidentSignal,
    VerdictRule,
)
from app.threats.settings import Tuning
from tests.test_incidents_engine import ATTACKER, NOW, alert, run, store

ON = Tuning(ai_gives_verdicts=True)
SIGNATURE = "ET SCAN Potential SSH Scan"


def scan(session: Session, settings: Settings, **changes: object) -> Incident:
    """A scan from one address, which the AI has not read."""
    store(session, settings, alert(NOW, n=1, severity=Severity.MEDIUM), alert(NOW, n=2))
    run(session)
    found = session.scalars(select(Incident)).one()
    for name, value in changes.items():
        setattr(found, name, value)
    session.flush()
    return found


def read(incident: Incident, **changes: object) -> AiTriage:
    """What the AI made of it: noise it is sure of, and says so."""
    fields: dict[str, object] = {
        "incident_id": incident.id,
        "read_at": NOW,
        "signals_read": incident.signal_count,
        "classification": "noise",
        "confidence": 91,
        "headline": "A scanner on the internet",
        "story": "It tried a port.",
        "verdict": "not_suspicious",
        "verdict_reason": "It is the scanner the owner runs.",
        "provider": "anthropic",
        "model": "claude-haiku-5-5",
    }
    fields.update(changes)
    return AiTriage(**fields)


def cleared(
    session: Session, settings: Settings, tuning: Tuning = ON, **changes: object
) -> tuple[Incident, VerdictRule | None]:
    found = scan(session, settings)
    rule = clearing.clear(session, found, read(found, **changes), tuning, NOW)
    session.commit()
    session.refresh(found)
    return found, rule


class TestGivingAVerdict:
    def test_it_says_who_gave_it_and_how_sure_they_were(
        self, session: Session, settings: Settings
    ) -> None:
        found, rule = cleared(session, settings)

        assert rule is not None
        assert (rule.verdict, str(rule.address), rule.source, rule.signature) == (
            "not_suspicious",
            ATTACKER,
            "wazuh",
            SIGNATURE,
        )
        assert rule.given_by == "ai"
        assert rule.note == "It is the scanner the owner runs."
        assert (rule.ai_confidence, rule.ai_provider, rule.ai_model) == (
            91,
            "anthropic",
            "claude-haiku-5-5",
        )
        assert rule.ai_incident_id == found.id

    def test_the_incident_is_muted_by_it_and_says_so(
        self, session: Session, settings: Settings
    ) -> None:
        found, rule = cleared(session, settings)

        assert rule is not None
        assert found.verdict == "not_suspicious"
        assert attention.standing(found) is attention.Standing.MUTED
        assert clearing.of(session, [found]) == {found.id: rule}
        signals = session.scalars(select(IncidentSignal)).all()
        assert {signal.verdict_rule_id for signal in signals} == {rule.id}

    def test_it_is_in_the_audit_log(self, session: Session, settings: Settings) -> None:
        _, rule = cleared(session, settings)

        assert rule is not None
        (event,) = session.scalars(
            select(AuditEvent).where(AuditEvent.action == Action.VERDICT_GIVEN_BY_AI)
        )
        assert event.detail == clearing.facts(rule)
        assert event.detail is not None
        assert (event.detail["confidence"], event.detail["provider"]) == (91, "anthropic")
        assert event.detail["incident_id"] == rule.ai_incident_id

    def test_low_priority_clears_too(self, session: Session, settings: Settings) -> None:
        found, rule = cleared(session, settings, verdict="low_priority")

        assert rule is not None
        assert found.verdict == "low_priority"

    def test_without_a_reason_it_says_what_it_made_of_it(
        self, session: Session, settings: Settings
    ) -> None:
        _, rule = cleared(session, settings, verdict_reason=None)

        assert rule is not None
        assert rule.note == "A scanner on the internet"

    def test_an_incident_about_no_address_is_cleared_by_what_it_is(
        self, session: Session, settings: Settings
    ) -> None:
        found = scan(session, settings, subject="rule:wazuh:" + SIGNATURE)

        rule = clearing.clear(session, found, read(found), ON, NOW)

        assert rule is not None
        assert rule.address is None
        assert rule.signature == SIGNATURE


class TestWhenItMayNot:
    @pytest.mark.parametrize(
        "tuning",
        [Tuning(), replace(ON, ai_gives_verdicts=False)],
        ids=["by default", "switched off"],
    )
    def test_not_unless_the_owner_allows_it(
        self, session: Session, settings: Settings, tuning: Tuning
    ) -> None:
        found, rule = cleared(session, settings, tuning)

        assert rule is None
        assert found.verdict is None
        assert session.scalars(select(VerdictRule)).all() == []

    @pytest.mark.parametrize(
        "changes",
        [
            {"confidence": 79},
            {"verdict": None},
            {"verdict": "threat"},
            {"verdict": "threat", "confidence": 99},
        ],
        ids=["unsure", "no verdict", "a threat", "a sure threat"],
    )
    def test_not_for_what_it_is_not_sure_is_nothing(
        self, session: Session, settings: Settings, changes: dict[str, object]
    ) -> None:
        found = scan(session, settings)

        assert clearing.clear(session, found, read(found, **changes), ON, NOW) is None

    @pytest.mark.parametrize(
        "changes",
        [
            {"verdict": "threat"},
            {"verdict": "not_suspicious"},
            {"status": "resolved"},
            {"status": "dismissed"},
            {"severity": Severity.CRITICAL},
            {"chain_id": 1},
            {"stages": ["recon", "exploit"]},
            {"ai_class": "attack", "ai_confidence": 90},
        ],
        ids=[
            "the owner called it a threat",
            "the owner called it harmless",
            "resolved",
            "dismissed",
            "critical",
            "a step of a chain",
            "a chain of stages",
            "an AI that is sure it is an attack",
        ],
    )
    def test_not_for_what_is_more_than_scanning_or_the_owner_has_decided(
        self, session: Session, settings: Settings, changes: dict[str, object]
    ) -> None:
        found = scan(session, settings)
        if "chain_id" in changes:
            chain = IncidentChain(device="aa:bb:cc:00:11:22", first_seen_at=NOW, last_seen_at=NOW)
            session.add(chain)
            session.flush()
            changes = {"chain_id": chain.id}
        for name, value in changes.items():
            setattr(found, name, value)
        session.flush()

        assert clearing.clear(session, found, read(found), ON, NOW) is None
        assert session.scalars(select(VerdictRule)).all() == []

    def test_not_for_alerts_with_no_signature(self, session: Session, settings: Settings) -> None:
        found = scan(session, settings)
        for signal in session.scalars(select(IncidentSignal)):
            signal.signature = None

        assert clearing.clear(session, found, read(found), ON, NOW) is None

    def test_not_again_once_the_owner_took_it_back(
        self, session: Session, settings: Settings
    ) -> None:
        found, rule = cleared(session, settings)
        assert rule is not None
        clearing.take_back(session, rule)
        session.delete(rule)
        session.commit()

        assert clearing.clear(session, found, read(found), ON, NOW) is None
        assert session.scalars(select(VerdictRule)).all() == []

    def test_not_over_a_verdict_the_owner_gave_about_the_same(
        self, session: Session, settings: Settings
    ) -> None:
        found = scan(session, settings)
        session.add(
            VerdictRule(verdict="threat", address=ATTACKER, source="wazuh", signature=SIGNATURE)
        )
        session.flush()

        assert clearing.clear(session, found, read(found), ON, NOW) is None


class TestTheOwnersWord:
    def test_a_verdict_the_owner_changes_is_theirs_and_forgets_the_ai(
        self, session: Session, settings: Settings
    ) -> None:
        _, rule = cleared(session, settings)
        assert rule is not None

        assert clearing.claim(rule) is True

        assert (rule.given_by, rule.ai_confidence, rule.ai_provider, rule.ai_model) == (
            "owner",
            None,
            None,
            None,
        )
        assert rule.ai_incident_id is None
        assert clearing.claim(rule) is False

    def test_an_incident_the_owner_also_said_something_about_is_theirs(
        self, session: Session, settings: Settings
    ) -> None:
        found, rule = cleared(session, settings)
        assert rule is not None
        owners = VerdictRule(verdict="low_priority", source="wazuh")
        session.add(owners)
        session.flush()
        session.scalars(select(IncidentSignal)).first().verdict_rule_id = owners.id  # pyright: ignore[reportOptionalMemberAccess]
        session.flush()

        assert clearing.of(session, [found]) == {}

    def test_an_incident_nothing_muted_has_no_ai_to_credit(
        self, session: Session, settings: Settings
    ) -> None:
        found = scan(session, settings)

        assert clearing.of(session, [found]) == {}

    def test_taking_back_is_remembered_once(self, session: Session, settings: Settings) -> None:
        _, rule = cleared(session, settings)
        assert rule is not None

        clearing.take_back(session, rule)
        clearing.take_back(session, rule)
        session.flush()

        (veto,) = session.scalars(select(AiClearVeto))
        assert (str(veto.address), veto.source, veto.signature) == (
            ATTACKER,
            "wazuh",
            SIGNATURE,
        )
