"""Reviewing what the AI decided: where a decision starts, what the owner can say of it, and what
it comes to for the incident."""

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.redaction import Level, Redactor
from app.models import AiTriage, Incident, IncidentFamily, ReviewFeedback, ReviewSettings
from app.review import service, settings
from app.threats import calls

NOW = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)


def incident(session: Session, n: int = 1, family: IncidentFamily | None = None) -> Incident:
    found = Incident(
        subject=f"8.8.8.{n}",
        title=f"Scan {n}",
        severity=2,
        confidence=50,
        first_seen_at=NOW,
        last_seen_at=NOW,
        top_source="wazuh",
        top_summary="x",
        family_id=family.id if family else None,
    )
    session.add(found)
    session.flush()
    return found


def family(session: Session, key: str = "k", **changes: Any) -> IncidentFamily:
    found = IncidentFamily(
        key=key * 40,
        source="wazuh",
        label=f"Scanning {key}",
        reach="internet",
        **{
            "ai_class": "noise",
            "ai_confidence": 90,
            "ai_reason": "Scanners.",
            "judged_at": NOW,
            **changes,
        },
    )
    session.add(found)
    session.flush()
    return found


def reading(
    session: Session, found: Incident, kind: str = "probe", confidence: int = 80, **more: Any
) -> AiTriage:
    row = AiTriage(
        incident_id=found.id,
        read_at=NOW,
        signals_read=1,
        classification=kind,
        confidence=confidence,
        headline="A probe.",
        story="s",
        checks=[],
        provider="anthropic",
        model="m",
        **more,
    )
    session.add(row)
    session.flush()
    return row


class TestWhereADecisionStarts:
    def test_with_nothing_saved_every_decision_waits(self, session: Session) -> None:
        assert settings.load(session) == settings.Policy("all", 85, True)
        assert settings.load(session).status(99) == "pending"

    def test_the_ai_can_decide_on_its_own(self) -> None:
        assert settings.Policy("auto").status(10) == "auto"

    def test_only_what_it_is_unsure_of_waits_when_asked(self) -> None:
        policy = settings.Policy("uncertain", 85)

        assert policy.status(84) == "pending"
        assert policy.status(85) == "auto"

    def test_a_call_that_changes_nothing_needs_no_look(self) -> None:
        policy = settings.Policy("all")

        assert service.starts(policy, "unclear", 99) == "auto"
        assert service.starts(policy, "noise", 99) == "pending"
        assert service.starts(policy, "compromise", 99) == "pending"

    def test_what_the_owner_answered_is_not_asked_again_when_it_says_the_same(self) -> None:
        assert service.carried("agreed", "noise", "noise", "pending") == "agreed"
        assert service.carried("disagreed", "noise", "noise", "pending") == "disagreed"

    def test_a_different_call_is_looked_at_afresh(self) -> None:
        assert service.carried("agreed", "noise", "attack", "pending") == "pending"
        assert service.carried("auto", "noise", "noise", "pending") == "pending"
        assert service.carried("agreed", None, "noise", "auto") == "auto"


class TestSavingTheSettings:
    def test_the_defaults_are_not_stored(self, session: Session) -> None:
        assert settings.save(session, settings.Policy()) is False
        assert session.get(ReviewSettings, 1) is None

    def test_a_change_is_stored_and_read_back(self, session: Session) -> None:
        assert settings.save(session, settings.Policy("uncertain", 90, False)) is True

        assert settings.load(session) == settings.Policy("uncertain", 90, False)

    def test_the_same_again_is_no_change(self, session: Session) -> None:
        settings.save(session, settings.Policy("auto", 70, True))

        assert settings.save(session, settings.Policy("auto", 70, True)) is False

    def test_it_can_go_back_to_the_defaults_once_stored(self, session: Session) -> None:
        settings.save(session, settings.Policy("auto"))

        assert settings.save(session, settings.Policy()) is True
        assert settings.load(session) == settings.Policy()


class TestWhatCounts:
    @pytest.mark.parametrize(
        ("review", "kind", "counted"),
        [
            ("auto", "noise", True),
            ("agreed", "probe", True),
            ("pending", "noise", False),
            ("pending", "attack", True),
            ("pending", "compromise", True),
            ("disagreed", "attack", False),
            ("disagreed", "noise", False),
            (None, None, True),
        ],
    )
    def test_a_decision_counts_by_where_its_review_stands(
        self, review: str | None, kind: str | None, counted: bool
    ) -> None:
        assert calls.counts(review, kind) is counted

    def test_a_waiting_family_judgement_does_not_set_its_incidents_aside(
        self, session: Session
    ) -> None:
        judged = family(session, review="pending")
        found = incident(session, family=judged)

        calls.sync(session)
        session.expire_all()

        assert found.ai_class is None

    def test_a_waiting_reading_that_raises_the_alarm_counts_at_once(self, session: Session) -> None:
        found = incident(session)
        reading(session, found, "attack", 90, review="pending")

        calls.sync(session)
        session.expire_all()

        assert (found.ai_class, found.ai_basis) == ("attack", "reading")

    def test_what_the_owner_disagreed_with_falls_back_to_what_is_left(
        self, session: Session
    ) -> None:
        judged = family(session, ai_class="probe", ai_confidence=90)
        found = incident(session, family=judged)
        reading(session, found, "attack", 95, review="disagreed")

        calls.sync(session)
        session.expire_all()

        assert (found.ai_class, found.ai_basis) == ("probe", "family")


class TestAnswering:
    def test_agreeing_makes_a_waiting_judgement_count_and_remembers_it(
        self, session: Session
    ) -> None:
        judged = family(session, review="pending")
        found = incident(session, family=judged)

        done = service.answer(session, "family", judged.id, "agree", "Looks right.", now=NOW)
        session.expire_all()

        assert done.review == "agreed"
        assert found.ai_class == "noise"
        assert judged.reviewed_at == NOW
        feedback = session.scalars(select(ReviewFeedback)).one()
        assert (feedback.subject, feedback.answer, feedback.reason) == (
            "family",
            "agree",
            "Looks right.",
        )
        assert (feedback.title, feedback.ai_class, feedback.ai_confidence) == (
            "Scanning k",
            "noise",
            90,
        )

    def test_disagreeing_takes_a_counting_judgement_back(self, session: Session) -> None:
        judged = family(session, ai_class="probe", ai_confidence=90)
        found = incident(session, family=judged)
        calls.sync(session)
        session.expire_all()
        assert found.ai_class == "probe"

        done = service.answer(session, "family", judged.id, "disagree", None, now=NOW)
        session.expire_all()

        assert done.review == "disagreed"
        assert found.ai_class is None
        assert session.scalars(select(ReviewFeedback.reason)).one() is None

    def test_a_reading_can_be_answered_too(self, session: Session) -> None:
        found = incident(session)
        reading(session, found, "noise", 90, review="pending")

        done = service.answer(session, "incident", found.id, "agree", now=NOW)
        session.expire_all()

        assert (done.subject, done.review, done.incidents) == ("incident", "agreed", 1)
        assert found.ai_class == "noise"
        assert session.scalars(select(ReviewFeedback.title)).one() == "Scan 1"

    def test_taking_an_answer_back_sends_it_to_wait_again(self, session: Session) -> None:
        judged = family(session, review="pending")
        found = incident(session, family=judged)
        service.answer(session, "family", judged.id, "agree", now=NOW)

        done = service.answer(session, "family", judged.id, "undo", now=NOW)
        session.expire_all()

        assert done.review == "pending"
        assert done.reviewed_at is None
        assert found.ai_class is None
        assert session.scalars(select(ReviewFeedback)).all() == []

    def test_taking_back_what_was_never_answered_leaves_nothing_to_delete(
        self, session: Session
    ) -> None:
        judged = family(session, review="auto")

        done = service.answer(session, "family", judged.id, "undo", now=NOW)

        assert done.review == "pending"

    def test_a_reason_is_trimmed_and_cut_to_fit(self, session: Session) -> None:
        judged = family(session)

        service.answer(session, "family", judged.id, "disagree", "  " + "x" * 400 + "  ")

        reason = session.scalars(select(ReviewFeedback.reason)).one()
        assert reason is not None
        assert len(reason) == service.MAX_REASON

    def test_a_blank_reason_is_no_reason(self, session: Session) -> None:
        judged = family(session)

        service.answer(session, "family", judged.id, "disagree", "   ")

        assert session.scalars(select(ReviewFeedback.reason)).one() is None

    def test_disagreeing_can_keep_a_kind_in_front_of_the_owner(self, session: Session) -> None:
        judged = family(session)

        service.answer(session, "family", judged.id, "disagree", keep_kind=True, now=NOW)

        assert (judged.owner_call, judged.owner_call_at) == ("watch", NOW)

    def test_agreeing_can_keep_a_kind_set_aside(self, session: Session) -> None:
        judged = family(session, ai_class="probe")

        service.answer(session, "family", judged.id, "agree", keep_kind=True, now=NOW)

        assert judged.owner_call == "background"

    def test_a_call_that_raises_the_alarm_is_never_kept_set_aside(self, session: Session) -> None:
        judged = family(session, ai_class="attack")

        service.answer(session, "family", judged.id, "agree", keep_kind=True)

        assert judged.owner_call is None

    def test_an_incident_has_no_kind_to_keep(self, session: Session) -> None:
        found = incident(session)
        reading(session, found, "noise", 90)

        done = service.answer(session, "incident", found.id, "agree", keep_kind=True)

        assert done.review == "agreed"

    @pytest.mark.parametrize("subject", ["incident", "family"])
    def test_what_is_not_there_cannot_be_answered(self, session: Session, subject: Any) -> None:
        with pytest.raises(service.NotFound):
            service.answer(session, subject, 999, "agree")

    def test_a_call_that_changes_nothing_cannot_be_answered(self, session: Session) -> None:
        found = incident(session)
        reading(session, found, "unclear", 40)
        unclear = family(session, ai_class="unclear")
        never = family(session, key="j", judged_at=None)

        with pytest.raises(service.NotFound):
            service.answer(session, "incident", found.id, "agree")
        with pytest.raises(service.NotFound):
            service.answer(session, "family", unclear.id, "agree")
        with pytest.raises(service.NotFound):
            service.answer(session, "family", never.id, "agree")

    def test_agreeing_with_all_that_wait_skips_the_rest(self, session: Session) -> None:
        waiting = family(session, key="a", review="pending")
        answered = family(session, key="b", review="disagreed")
        found = incident(session)
        reading(session, found, "noise", 90, review="pending")

        done = service.agree_all(
            session,
            [
                ("family", waiting.id),
                ("family", answered.id),
                ("family", 999),
                ("incident", found.id),
            ],
            NOW,
        )

        assert done == 2
        assert (waiting.review, answered.review) == ("agreed", "disagreed")


class TestTheQueue:
    def fill(self, session: Session) -> dict[str, Any]:
        big = family(session, key="a", review="pending")
        for n in range(3):
            incident(session, n + 1, big)
        small = family(session, key="b", review="pending", ai_class="probe")
        incident(session, 10, small)
        loud = incident(session, 20)
        reading(session, loud, "attack", 70, review="pending")
        quiet = incident(session, 21)
        reading(session, quiet, "noise", 95, review="auto")
        done = family(session, key="c", review="agreed", reviewed_at=NOW)
        return {"big": big, "small": small, "loud": loud, "quiet": quiet, "done": done}

    def test_what_raises_the_alarm_comes_first_then_what_sets_aside_the_most(
        self, session: Session
    ) -> None:
        found = self.fill(session)

        items, total = service.queue(session, "waiting", 10)

        assert total == 3
        assert [(item.subject, item.id) for item in items] == [
            ("incident", found["loud"].id),
            ("family", found["big"].id),
            ("family", found["small"].id),
        ]
        assert [item.active for item in items] == [1, 3, 1]

    def test_what_counted_at_once_and_what_was_answered_are_listed_apart(
        self, session: Session
    ) -> None:
        found = self.fill(session)

        decided, decided_total = service.queue(session, "decided", 10)
        answered, answered_total = service.queue(session, "answered", 10)

        assert (decided_total, answered_total) == (1, 1)
        assert [item.id for item in decided] == [found["quiet"].id]
        assert answered[0].id == found["done"].id

    def test_it_is_paged(self, session: Session) -> None:
        self.fill(session)

        second, total = service.queue(session, "waiting", 2, 2)

        assert total == 3
        assert len(second) == 1

    def test_it_says_what_the_owner_said_when_they_gave_a_reason(self, session: Session) -> None:
        found = self.fill(session)
        service.answer(session, "family", found["big"].id, "disagree", "That is my camera.")

        answered, _ = service.queue(session, "answered", 10)

        item = next(each for each in answered if each.id == found["big"].id)
        assert (item.review, item.reason) == ("disagreed", "That is my camera.")

    def test_it_counts_each_state(self, session: Session) -> None:
        self.fill(session)

        tally = service.counts(session)

        assert (tally.waiting, tally.decided, tally.agreed, tally.disagreed) == (3, 1, 1, 0)
        assert service.waiting(session) == 3

    def test_an_empty_queue_is_empty(self, session: Session) -> None:
        assert service.queue(session, "waiting", 10) == ([], 0)


class TestHowFarItCanBeTrusted:
    def answers(self, session: Session, agreed: int, disagreed: int) -> None:
        for n in range(agreed + disagreed):
            session.add(
                ReviewFeedback(
                    subject="family",
                    subject_id=n,
                    title="t",
                    ai_class="noise",
                    ai_confidence=90,
                    answer="agree" if n < agreed else "disagree",
                )
            )
        session.flush()

    def test_it_is_unknown_before_anything_is_answered(self, session: Session) -> None:
        found = service.standing(session)

        assert (found.answered, found.rate, found.trusted) == (0, None, False)

    def test_it_is_trusted_when_it_is_nearly_always_agreed_with(self, session: Session) -> None:
        self.answers(session, 39, 1)

        found = service.standing(session)

        assert (found.agreed, found.disagreed, found.trusted) == (39, 1, True)
        assert found.rate == pytest.approx(0.975)

    def test_it_is_not_trusted_on_too_few_answers_or_too_many_disagreements(
        self, session: Session
    ) -> None:
        self.answers(session, 5, 0)
        assert service.standing(session).trusted is False

    def test_it_is_not_trusted_when_it_is_often_wrong(self, session: Session) -> None:
        self.answers(session, 20, 5)

        assert service.standing(session).trusted is False


def redactor(session: Session) -> Redactor:
    return Redactor(session, Level.BALANCED, NOW)


class TestWhatTheAiIsTold:
    def test_it_is_told_what_the_owner_disagreed_with_and_why(self, session: Session) -> None:
        judged = family(session)
        service.answer(session, "family", judged.id, "disagree", "That is my camera.")
        service.answer(session, "family", family(session, key="z").id, "agree")

        taught = service.lessons(session, redactor(session), settings.Policy())

        assert taught == [
            "- You called Scanning k noise (90% sure) and the owner disagreed: That is my camera."
        ]

    def test_a_disagreement_without_a_reason_is_told_without_one(self, session: Session) -> None:
        service.answer(session, "family", family(session).id, "disagree")

        taught = service.lessons(session, redactor(session), settings.Policy())

        assert taught == ["- You called Scanning k noise (90% sure) and the owner disagreed"]

    def test_only_the_newest_few_are_told(self, session: Session) -> None:
        for n in range(service.LESSONS + 2):
            service.answer(session, "family", family(session, key=f"{n:x}").id, "disagree")

        taught = service.lessons(session, redactor(session), settings.Policy())

        assert len(taught) == service.LESSONS
        assert "Scanning 6" in taught[0]

    def test_nothing_is_told_when_the_owner_does_not_want_it_learned_from(
        self, session: Session
    ) -> None:
        service.answer(session, "family", family(session).id, "disagree", "no")

        assert service.lessons(session, redactor(session), settings.Policy(learn=False)) == []
