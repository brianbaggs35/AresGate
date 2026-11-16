"""The review queue: what the AI cleared and what it suggests clearing, and what the owner does
about each."""

from dataclasses import replace

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import clearing, clearing_settings, review_queue
from app.ai.clearing_settings import Policy
from app.audit import Action
from app.config import Settings
from app.models import AiClearVeto, AuditEvent, Incident, IncidentSignal, VerdictRule
from app.threats.settings import Tuning
from tests.test_ai_clearing import ON, read, scan
from tests.test_incidents_engine import NOW, OTHER_ATTACKER, alert, run, store

SUGGESTING = Policy()


def suggested(session: Session, settings: Settings, **changes: object) -> Incident:
    """An incident the AI has read as nothing it is sure of."""
    found = scan(session, settings)
    session.add(read(found, **changes))
    session.flush()
    return found


def another(session: Session, settings: Settings) -> Incident:
    """A scan from another address, an incident of its own."""
    store(
        session,
        settings,
        alert(NOW, n=10, src_address=OTHER_ATTACKER),
        alert(NOW, n=11, src_address=OTHER_ATTACKER),
    )
    run(session)
    return session.scalars(select(Incident).where(Incident.subject == OTHER_ATTACKER)).one()


class TestWhatWaits:
    def test_an_incident_the_ai_read_as_nothing_waits_for_the_owner(
        self, session: Session, settings: Settings
    ) -> None:
        found = suggested(session, settings)

        (item,) = review_queue.waiting(session, SUGGESTING, Tuning())

        assert item.incident.id == found.id
        assert item.reading.verdict == "not_suspicious"

    def test_nothing_waits_where_the_ai_is_off(self, session: Session, settings: Settings) -> None:
        suggested(session, settings)

        assert review_queue.waiting(session, replace(SUGGESTING, mode="off"), Tuning()) == []

    def test_what_the_ai_would_clear_by_itself_waits_too_where_it_is_stopped(
        self, session: Session, settings: Settings
    ) -> None:
        suggested(session, settings)

        assert len(review_queue.waiting(session, ON, Tuning())) == 1

    def test_not_what_the_settings_do_not_allow_the_ai_to_clear(
        self, session: Session, settings: Settings
    ) -> None:
        suggested(session, settings, confidence=60)

        assert review_queue.waiting(session, SUGGESTING, Tuning()) == []

    def test_not_what_the_ai_did_not_call_nothing(
        self, session: Session, settings: Settings
    ) -> None:
        suggested(session, settings, verdict=None)

        assert review_queue.waiting(session, SUGGESTING, Tuning()) == []

    def test_not_what_has_a_verdict_or_is_over(self, session: Session, settings: Settings) -> None:
        found = suggested(session, settings)
        found.status = "resolved"
        session.flush()
        assert review_queue.waiting(session, SUGGESTING, Tuning()) == []

        found.status = "open"
        found.verdict = "threat"
        session.flush()
        assert review_queue.waiting(session, SUGGESTING, Tuning()) == []

    def test_not_what_the_owner_turned_down_or_has_said_something_of(
        self, session: Session, settings: Settings
    ) -> None:
        found = suggested(session, settings)
        assert review_queue.dismiss_suggestion(session, found) is not None
        session.flush()

        assert review_queue.waiting(session, SUGGESTING, Tuning()) == []

    def test_not_what_has_no_signature_to_say_it_by(
        self, session: Session, settings: Settings
    ) -> None:
        suggested(session, settings)
        for signal in session.scalars(select(IncidentSignal)):
            signal.signature = None
        session.flush()

        assert review_queue.waiting(session, SUGGESTING, Tuning()) == []

    def test_the_newest_reading_is_first(self, session: Session, settings: Settings) -> None:
        first = suggested(session, settings)
        second = another(session, settings)
        session.add(read(second, read_at=NOW.replace(year=NOW.year + 1)))
        session.flush()

        found = [item.incident.id for item in review_queue.waiting(session, SUGGESTING, Tuning())]

        assert found[0] == second.id
        assert first.id in found


class TestWhatWasCleared:
    def test_the_verdicts_the_ai_gave_are_listed_with_what_it_read(
        self, session: Session, settings: Settings
    ) -> None:
        found = scan(session, settings)
        reading = read(found)
        session.add(reading)
        session.flush()
        rule = clearing.clear(session, found, reading, Tuning(), NOW, ON)

        (item,) = review_queue.cleared(session)

        assert rule is not None
        assert (item.rule.id, item.incident, item.reading) == (rule.id, found, reading)

    def test_a_verdict_whose_incident_is_gone_is_still_listed(self, session: Session) -> None:
        session.add(
            VerdictRule(
                verdict="not_suspicious",
                source="wazuh",
                signature="x",
                given_by="ai",
                ai_confidence=90,
            )
        )
        session.flush()

        (item,) = review_queue.cleared(session)

        assert (item.incident, item.reading) == (None, None)

    def test_the_owners_own_verdicts_are_not_listed(self, session: Session) -> None:
        session.add(VerdictRule(verdict="threat", source="wazuh", signature="x"))
        session.flush()

        assert review_queue.cleared(session) == []

    def test_it_counts_both(self, session: Session, settings: Settings) -> None:
        found = suggested(session, settings)
        other = another(session, settings)
        reading = read(other)
        session.add(reading)
        session.flush()
        clearing.clear(session, other, reading, Tuning(), NOW, ON)
        session.flush()

        assert found.id != other.id
        assert review_queue.counts(session)[1] == 1


class TestConfirming:
    def test_what_the_ai_cleared_becomes_the_owners_word(
        self, session: Session, settings: Settings
    ) -> None:
        found = scan(session, settings)
        reading = read(found)
        rule = clearing.clear(session, found, reading, Tuning(), NOW, ON)
        assert rule is not None

        facts = review_queue.confirm_cleared(rule, NOW)

        assert facts is not None
        assert facts["verdict_id"] == rule.id
        assert (rule.given_by, rule.ai_confidence) == ("owner", None)
        assert review_queue.cleared(session) == []

    def test_what_is_the_owners_already_is_not_confirmed_again(self) -> None:
        assert review_queue.confirm_cleared(VerdictRule(given_by="owner"), NOW) is None

    def test_a_suggestion_is_given_as_the_owners_verdict(
        self, session: Session, settings: Settings
    ) -> None:
        found = suggested(session, settings)
        reading = session.get_one(type(read(found)), found.id)

        given = review_queue.confirm_suggestion(session, found, reading, None, NOW)

        assert given is not None
        rule, facts = given
        assert (rule.given_by, rule.verdict, rule.ai_confidence) == (
            "owner",
            "not_suspicious",
            None,
        )
        assert facts["incident_id"] == found.id
        assert facts["confidence"] == 91
        session.refresh(found)
        assert found.verdict == "not_suspicious"

    def test_the_owner_can_say_another_verdict_than_the_ai_did(
        self, session: Session, settings: Settings
    ) -> None:
        found = suggested(session, settings)
        reading = session.get_one(type(read(found)), found.id)

        given = review_queue.confirm_suggestion(session, found, reading, "low_priority", NOW)

        assert given is not None
        assert given[0].verdict == "low_priority"

    def test_nothing_is_given_where_the_owner_has_said_it_already(
        self, session: Session, settings: Settings
    ) -> None:
        found = suggested(session, settings)
        reading = session.get_one(type(read(found)), found.id)
        assert review_queue.confirm_suggestion(session, found, reading, None, NOW) is not None

        assert review_queue.confirm_suggestion(session, found, reading, None, NOW) is None

    def test_nothing_is_given_where_there_is_no_signature_to_say_it_by(
        self, session: Session, settings: Settings
    ) -> None:
        found = suggested(session, settings)
        reading = session.get_one(type(read(found)), found.id)
        for signal in session.scalars(select(IncidentSignal)):
            signal.signature = None
        session.flush()

        assert review_queue.confirm_suggestion(session, found, reading, None, NOW) is None
        assert review_queue.dismiss_suggestion(session, found) is None


class TestTurningDown:
    def test_it_tells_the_ai_not_to_suggest_that_again(
        self, session: Session, settings: Settings
    ) -> None:
        found = suggested(session, settings)

        facts = review_queue.dismiss_suggestion(session, found)
        session.flush()

        assert facts is not None
        assert facts["incident_id"] == found.id
        assert len(session.scalars(select(AiClearVeto)).all()) == 1
        assert review_queue.dismiss_suggestion(session, found) is not None
        session.flush()
        assert len(session.scalars(select(AiClearVeto)).all()) == 1


class TestTheTrail:
    def step(
        self, session: Session, action: Action, incident_id: int, who: str | None, **more: object
    ) -> None:
        session.add(
            AuditEvent(
                action=action.value,
                outcome="success",
                username=who,
                detail={"incident_id": incident_id, **more},
                occurred_at=NOW,
            )
        )
        session.flush()

    def test_it_says_what_happened_and_who_did_it(self, session: Session) -> None:
        self.step(
            session, Action.VERDICT_GIVEN_BY_AI, 5, None, verdict="not_suspicious", confidence=91
        )
        self.step(session, Action.AI_CLEAR_CONFIRMED, 5, "admin")
        self.step(session, Action.AI_CLEAR_CONFIRMED, 6, "admin")
        self.step(session, Action.THREATS_SETTINGS_CHANGED, 5, "admin")

        trail = review_queue.trail(session, 5)

        assert [(step.action, step.by) for step in trail] == [
            ("verdict.given_by_ai", "the AI"),
            ("ai.clear_confirmed", "admin"),
        ]
        assert (trail[0].verdict, trail[0].confidence) == ("not_suspicious", 91)
        assert (trail[1].verdict, trail[1].confidence) == (None, None)

    def test_an_owner_with_no_name_is_you(self, session: Session) -> None:
        self.step(session, Action.AI_SUGGESTION_DISMISSED, 7, None)

        assert review_queue.trail(session, 7)[0].by == "you"

    def test_the_settings_are_what_decide_whether_anything_waits(
        self, session: Session, settings: Settings
    ) -> None:
        suggested(session, settings)
        assert review_queue.counts(session)[0] == 1

        clearing_settings.save(session, replace(SUGGESTING, mode="off"), NOW)

        assert review_queue.counts(session)[0] == 0
