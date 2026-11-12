"""AI judgement of families: which kinds of incident are judged without being asked, what the AI
is told about them, how its answer is read and kept, and the loop that does it. The provider is a
server on this machine that answers the way Anthropic's API does."""

import asyncio
import json
import logging
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import anyio
import anyio.to_thread
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.ai import families, run, service
from app.ai.gateway import Answer, Unavailable
from app.ai.redaction import Level, Redactor
from app.ai.triage import LESSON_HEADING
from app.config import Settings
from app.models import AiCall, Incident, IncidentFamily, ReviewFeedback
from app.review import service as review
from app.review import settings as review_settings
from app.threats import families as grouping
from tests.stubs import Handler, Seen, Serve
from tests.test_ai_gateway import Log, anthropic_says, context
from tests.test_ai_service import NOW
from tests.test_ai_triage import incident, ready, signals, with_level

MINUTE = timedelta(minutes=1)


def kind(session: Session, count: int, words: str = "ET SCAN Potential SSH Scan", **more: object):
    """``count`` incidents from different addresses that all say the same, and their family."""
    first = session.scalar(select(func.count()).select_from(Incident)) or 0
    for number in range(count):
        address = f"45.33.32.{(first + number) % 250 + 1}"
        incident(
            session,
            **{"subject": address, "top_summary": f"{words} from {address}", **more},
        )
    grouping.assign(session)
    session.commit()
    return session.scalars(
        select(IncidentFamily).where(IncidentFamily.label.like(f"{words}%"))
    ).one()


def judgement(*found: int, **changes: object) -> dict[str, object]:
    return {
        "families": [
            {
                "id": f"F{number}",
                "classification": "probe",
                "confidence": 93,
                "reason": "Internet scanners.",
                **changes,
            }
            for number in found
        ]
    }


def judges(*found: int, **changes: object) -> Handler:
    return anthropic_says(json.dumps(judgement(*found, **changes)))


def asked_about_families(session: Session, *, minutes_ago: int = 5) -> int:
    call = AiCall(
        occurred_at=NOW - minutes_ago * MINUTE,
        purpose=families.PURPOSE,
        about="1 family",
        provider="anthropic",
        model="claude-haiku-5-5",
        level="balanced",
        ok=True,
        prompt="x",
    )
    session.add(call)
    session.commit()
    return call.id


class TestWhichAreJudgedWithoutBeingAsked:
    def at_level(self, session: Session, settings: Settings, level: str) -> None:
        ready(session, settings)
        with_level(session, level)

    def test_nothing_is_judged_when_ai_is_off_or_has_no_provider(
        self, session: Session, settings: Settings
    ) -> None:
        kind(session, 30)
        assert families.plan(session, NOW) == []

        ready(session, settings)
        service.usage(session, NOW).provider = None
        session.commit()

        assert families.plan(session, NOW) == []

    def test_the_lowest_level_judges_none(self, session: Session, settings: Settings) -> None:
        self.at_level(session, settings, "very_low")
        kind(session, 30)

        assert families.plan(session, NOW) == []

    def test_a_kind_has_to_be_big_enough_to_be_worth_a_request(
        self, session: Session, settings: Settings
    ) -> None:
        self.at_level(session, settings, "medium")
        small = kind(session, 4, "ET SCAN small")
        big = kind(session, 5, "ET SCAN big")

        assert families.plan(session, NOW) == [big.id]
        assert small.id not in families.plan(session, NOW)

    def test_the_biggest_come_first(self, session: Session, settings: Settings) -> None:
        self.at_level(session, settings, "maximum")
        few = kind(session, 2, "ET SCAN few")
        many = kind(session, 6, "ET SCAN many")

        assert families.plan(session, NOW) == [many.id, few.id]

    def test_a_kind_the_owner_has_called_is_not_judged(
        self, session: Session, settings: Settings
    ) -> None:
        self.at_level(session, settings, "maximum")
        owned = kind(session, 3, "ET SCAN owned")
        owned.owner_call = "background"
        session.commit()

        assert families.plan(session, NOW) == []

    def test_a_kind_that_was_judged_is_not_judged_again_until_it_has_grown(
        self, session: Session, settings: Settings
    ) -> None:
        self.at_level(session, settings, "medium")
        found = kind(session, 5)
        found.judged_at = NOW - 3 * 60 * MINUTE
        found.judged_incidents = 5
        session.commit()

        assert families.plan(session, NOW) == []

        found.judged_incidents = 1
        session.commit()

        assert families.plan(session, NOW) == [found.id]

    def test_it_waits_a_while_before_judging_a_kind_again(
        self, session: Session, settings: Settings
    ) -> None:
        self.at_level(session, settings, "medium")
        found = kind(session, 5)
        found.judged_at = NOW - 5 * MINUTE
        found.judged_incidents = 1
        session.commit()

        assert families.plan(session, NOW) == []

    def test_the_lowest_level_that_judges_never_judges_one_twice(
        self, session: Session, settings: Settings
    ) -> None:
        self.at_level(session, settings, "low")
        found = kind(session, 20)
        found.judged_at = NOW - 3 * 60 * MINUTE
        found.judged_incidents = 1
        session.commit()

        assert families.plan(session, NOW) == []

    def test_only_so_many_requests_are_made_in_an_hour(
        self, session: Session, settings: Settings
    ) -> None:
        self.at_level(session, settings, "low")
        kind(session, 20)
        asked_about_families(session)

        assert families.plan(session, NOW) == []

    def test_what_was_asked_more_than_an_hour_ago_does_not_count(
        self, session: Session, settings: Settings
    ) -> None:
        self.at_level(session, settings, "low")
        found = kind(session, 20)
        asked_about_families(session, minutes_ago=90)

        assert families.plan(session, NOW) == [found.id]

    def test_incidents_that_are_over_do_not_make_a_kind(
        self, session: Session, settings: Settings
    ) -> None:
        self.at_level(session, settings, "maximum")
        found = kind(session, 3)
        for each in session.scalars(select(Incident)):
            each.status = "resolved"
        session.commit()

        assert found.id not in families.plan(session, NOW)

    def test_no_more_than_a_request_can_hold_are_judged_at_once(
        self, session: Session, settings: Settings
    ) -> None:
        self.at_level(session, settings, "maximum")
        for number in range(families.MAX_FAMILIES + 3):
            kind(session, 2, f"ET SCAN number {chr(97 + number)}")

        assert len(families.plan(session, NOW)) == families.MAX_FAMILIES


class TestWhatTheAiIsAsked:
    def prompt(self, session: Session, ids: list[int], level: Level = Level.BALANCED) -> str:
        _, found = families.question_for(session, ids)
        redactor = Redactor(session, level, NOW)
        return redactor.finish(families.prompt_for(found, redactor))

    def test_it_is_told_what_each_kind_says_and_how_much_of_it_there_is(
        self, session: Session
    ) -> None:
        found = kind(session, 3, ports=[22, 80], banned=True, stages=["recon"])

        said = self.prompt(session, [found.id])

        assert "F1: ET SCAN Potential SSH Scan from <address>" in said
        assert "program that reported it most seriously: wazuh; from: the internet" in said
        assert "3 incidents with 9 alerts from 3 different addresses" in said
        assert "banned: 3 of 3" in said
        assert "stages of an attack seen: recon" in said
        assert "22 (3), 80 (3)" in said
        assert "45.33.32" not in said.split("example from")[0]

    def test_it_is_reminded_of_what_the_owner_disagreed_with(self, session: Session) -> None:
        found = kind(session, 3)
        session.add(
            ReviewFeedback(
                subject="family",
                subject_id=1,
                title="Printing at night",
                ai_class="noise",
                ai_confidence=91,
                answer="disagree",
                reason="That printer is mine.",
            )
        )
        session.flush()
        question, _ = families.question_for(session, [found.id])

        said = question.build(Redactor(session, Level.BALANCED, NOW))

        assert said.startswith(LESSON_HEADING)
        assert (
            "- You called Printing at night noise (91% sure) and the owner disagreed: "
            "That printer is mine." in said
        )
        assert "Families to judge:" in said

    def test_it_is_not_reminded_when_the_owner_would_rather_it_did_not_learn(
        self, session: Session
    ) -> None:
        found = kind(session, 3)
        session.add(
            ReviewFeedback(
                subject="family",
                subject_id=1,
                title="x",
                ai_class="noise",
                ai_confidence=91,
                answer="disagree",
            )
        )
        review_settings.save(session, review_settings.Policy(learn=False))
        session.flush()
        question, _ = families.question_for(session, [found.id])

        said = question.build(Redactor(session, Level.BALANCED, NOW))

        assert LESSON_HEADING not in said

    def test_a_kind_with_nothing_to_say_says_none(self, session: Session) -> None:
        found = kind(session, 1, "ET SCAN lonely", sources=[], ports=[], stages=[])

        said = self.prompt(session, [found.id])

        assert "reported by: nobody" in said
        assert "stages of an attack seen: none" in said
        assert "destination ports touched (incidents): none" in said

    def test_the_kinds_are_numbered_in_the_order_they_were_given(self, session: Session) -> None:
        one = kind(session, 2, "ET SCAN one")
        two = kind(session, 2, "ET SCAN two")

        said = self.prompt(session, [two.id, one.id])

        assert said.index("F1: ET SCAN two") < said.index("F2: ET SCAN one")

    def test_a_kind_of_the_owners_own_network_or_a_rule_is_told_so(self, session: Session) -> None:
        inside = kind(session, 1, "ET INSIDE", subject="192.168.1.7", title="Inside")
        session.query(Incident).filter(Incident.family_id == inside.id).update(
            {"subject": "192.168.1.7"}
        )
        session.commit()
        rule = IncidentFamily(key="r" * 40, source="wazuh", label="A rule", reach=grouping.RULE)
        session.add(rule)
        session.flush()
        incident(session, subject="rule:wazuh:5710", family_id=rule.id)
        inside.reach = grouping.NETWORK
        session.commit()

        said = self.prompt(session, [inside.id, rule.id])

        assert "from: the owner's own network" in said
        assert "from: a rule that names no address" in said
        assert "different rules" in said

    def test_a_long_stay_is_said_in_hours(self, session: Session) -> None:
        found = kind(session, 2)
        session.query(Incident).update({"first_seen_at": NOW - timedelta(hours=30)})
        session.commit()

        assert "over 30 hours" in self.prompt(session, [found.id])

    def test_examples_show_what_the_alerts_say_with_addresses_hidden(
        self, session: Session
    ) -> None:
        found = kind(session, 2)
        best = session.scalars(
            select(Incident).where(Incident.family_id == found.id).order_by(Incident.id.desc())
        ).first()
        assert best is not None
        signals(session, best, 3)
        session.commit()

        said = self.prompt(session, [found.id])

        assert "example from F1" in said
        assert "ET SCAN 0" in said
        assert "192.168.1.20" not in said

    def test_the_question_has_the_start_that_is_the_same_every_time(self, session: Session) -> None:
        found = kind(session, 2)

        question, kinds = families.question_for(session, [found.id])

        assert question.purpose == "families"
        assert question.about == "1 family"
        assert question.start is not None
        assert "How to tell a real threat" in question.start(Redactor(session, Level.BALANCED, NOW))
        assert [item.family.id for item in kinds] == [found.id]
        assert question.max_tokens == 120 + 200

    def test_a_kind_with_no_incidents_going_is_left_out(self, session: Session) -> None:
        found = kind(session, 2)
        session.query(Incident).update({"status": "dismissed"})
        session.commit()

        question, kinds = families.question_for(session, [found.id])

        assert kinds == []
        assert question.about == "0 families"

    def test_many_kinds_are_told_in_the_plural(self) -> None:
        assert families.about(1) == "1 family"
        assert families.about(3) == "3 families"


class TestWhatTheAnswerMeans:
    def test_a_complete_answer_is_read(self) -> None:
        said = families.parse(json.dumps(judgement(1, 2)), 2)

        assert said == {
            1: families.Judgement("probe", 93, "Internet scanners."),
            2: families.Judgement("probe", 93, "Internet scanners."),
        }

    def test_an_answer_in_a_code_fence_or_a_sentence_is_read(self) -> None:
        text = json.dumps(judgement(1))

        assert families.parse(f"```json\n{text}\n```", 1) is not None
        assert families.parse(f"Here you go: {text} Hope it helps.", 1) is not None

    @pytest.mark.parametrize(
        "text",
        ["", "nothing here", "[]", '{"families": 3}', '{"other": []}', "{broken", "{not json}"],
    )
    def test_what_is_not_an_answer_is_none(self, text: str) -> None:
        assert families.parse(text, 1) is None

    @pytest.mark.parametrize(
        "changes",
        [
            {"id": 1},
            {"id": "G1"},
            {"id": "F0"},
            {"id": "F9"},
            {"classification": "bad"},
            {"classification": None},
            {"confidence": "high"},
            {"confidence": True},
        ],
    )
    def test_a_kind_it_got_wrong_is_left_out_and_not_the_whole_answer(
        self, changes: dict[str, Any]
    ) -> None:
        body = judgement(1, 2)
        body["families"][0].update(changes)  # type: ignore[index]

        said = families.parse(json.dumps(body), 2)

        assert said is not None
        assert list(said) == [2]

    def test_what_is_not_an_object_in_the_list_is_skipped(self) -> None:
        body = {"families": ["F1", *judgement(1)["families"]]}  # type: ignore[misc]

        assert list(families.parse(json.dumps(body), 1) or {}) == [1]

    def test_numbers_are_kept_to_their_range_and_a_reason_to_its_length(self) -> None:
        body = judgement(1, confidence=140, reason="x" * 500)

        said = families.parse(json.dumps(body), 1)

        assert said is not None
        assert said[1].confidence == 100
        assert len(said[1].reason) <= families.MAX_REASON

    def test_a_missing_reason_is_empty(self) -> None:
        body = judgement(1)
        del body["families"][0]["reason"]  # type: ignore[index]

        said = families.parse(json.dumps(body), 1)

        assert said is not None
        assert said[1].reason == ""


class TestKeepingWhatItSaid:
    @pytest.fixture(autouse=True)
    def _call(self, session: Session) -> None:
        self.call = asked_about_families(session)

    def answer(self, text: str, *, ok: bool = True, truncated: bool = False) -> Answer:
        return Answer(
            ok=ok,
            text=text,
            reason=None if ok else "It timed out.",
            call_id=self.call,
            truncated=truncated,
            provider="anthropic",
            model="claude-haiku-5-5",
        )

    def found(self, session: Session) -> tuple[IncidentFamily, list[families.Facts]]:
        family = kind(session, 3)
        _, facts = families.question_for(session, [family.id])
        return family, facts

    def test_nothing_asked_says_why(self, session: Session) -> None:
        _, facts = self.found(session)

        said = families.keep(session, facts, Unavailable("AI is turned off."), NOW)

        assert said == families.NotJudged("AI is turned off.")

    def test_a_provider_that_failed_says_so(self, session: Session) -> None:
        _, facts = self.found(session)

        said = families.keep(session, facts, self.answer("", ok=False), NOW)

        assert isinstance(said, families.NotJudged)
        assert said.reason == "The AI provider didn't answer. It timed out."

    def test_an_answer_that_cannot_be_read_says_so_and_keeps_nothing(
        self, session: Session
    ) -> None:
        family, facts = self.found(session)

        said = families.keep(session, facts, self.answer("It is a scan."), NOW)

        assert isinstance(said, families.NotJudged)
        assert "not in a form AresGate could read" in said.reason
        assert "cut short" not in said.reason
        assert family.ai_class is None

    def test_an_answer_that_was_cut_short_says_so(self, session: Session) -> None:
        _, facts = self.found(session)

        said = families.keep(session, facts, self.answer("{", truncated=True), NOW)

        assert isinstance(said, families.NotJudged)
        assert "cut short" in said.reason

    def test_a_judgement_is_kept_with_who_made_it_and_told_to_the_incidents(
        self, session: Session
    ) -> None:
        review_settings.save(session, review_settings.Policy("auto"))
        family, facts = self.found(session)

        said = families.keep(session, facts, self.answer(json.dumps(judgement(1))), NOW)

        assert said == families.Judged(1, 3)
        session.commit()
        session.expire_all()
        assert (family.ai_class, family.ai_confidence) == ("probe", 93)
        assert family.ai_reason == "Internet scanners."
        assert family.judged_at == NOW
        assert family.judged_incidents == 3
        assert (family.provider, family.model) == ("anthropic", "claude-haiku-5-5")
        members = session.scalars(select(Incident).where(Incident.family_id == family.id)).all()
        assert {(each.ai_class, each.ai_confidence, each.ai_basis) for each in members} == {
            ("probe", 93, "family")
        }

    def test_a_judgement_waits_for_the_owner_by_default_and_sets_nothing_aside(
        self, session: Session
    ) -> None:
        family, facts = self.found(session)

        families.keep(session, facts, self.answer(json.dumps(judgement(1))), NOW)
        session.commit()
        session.expire_all()

        assert (family.review, family.reviewed_at) == ("pending", None)
        members = session.scalars(select(Incident).where(Incident.family_id == family.id)).all()
        assert {each.ai_class for each in members} == {None}

    def test_a_judgement_that_raises_the_alarm_counts_while_it_waits(
        self, session: Session
    ) -> None:
        family, facts = self.found(session)

        families.keep(
            session, facts, self.answer(json.dumps(judgement(1, classification="attack"))), NOW
        )
        session.commit()
        session.expire_all()

        assert family.review == "pending"
        members = session.scalars(select(Incident).where(Incident.family_id == family.id)).all()
        assert {each.ai_class for each in members} == {"attack"}

    def test_only_what_it_is_unsure_of_waits_when_the_owner_asks_for_that(
        self, session: Session
    ) -> None:
        review_settings.save(session, review_settings.Policy("uncertain", 95))
        family, facts = self.found(session)

        families.keep(session, facts, self.answer(json.dumps(judgement(1, confidence=93))), NOW)
        assert family.review == "pending"
        families.keep(session, facts, self.answer(json.dumps(judgement(1, confidence=96))), NOW)
        assert family.review == "auto"

    def test_what_the_owner_agreed_with_is_not_asked_again_when_it_says_the_same(
        self, session: Session
    ) -> None:
        family, facts = self.found(session)
        families.keep(session, facts, self.answer(json.dumps(judgement(1))), NOW)
        review.answer(session, "family", family.id, "agree", now=NOW)

        families.keep(session, facts, self.answer(json.dumps(judgement(1))), NOW)

        assert (family.review, family.reviewed_at) == ("agreed", NOW)

    def test_a_different_judgement_is_looked_at_afresh(self, session: Session) -> None:
        family, facts = self.found(session)
        families.keep(session, facts, self.answer(json.dumps(judgement(1))), NOW)
        review.answer(session, "family", family.id, "agree", now=NOW)

        families.keep(
            session, facts, self.answer(json.dumps(judgement(1, classification="noise"))), NOW
        )

        assert (family.review, family.reviewed_at) == ("pending", None)

    def test_an_empty_reason_is_not_kept(self, session: Session) -> None:
        family, facts = self.found(session)

        families.keep(session, facts, self.answer(json.dumps(judgement(1, reason=""))), NOW)

        assert family.ai_reason is None


class TestAskingNow:
    def test_the_ai_judges_it_and_the_incidents_are_told(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        server = serve(judges(1))
        ready(session, settings)
        family = kind(session, 3)
        where = context(settings, Log(), server.url)

        async def from_a_thread() -> families.Outcome:
            return await anyio.to_thread.run_sync(
                families.ask_now, session, where, [family.id], NOW
            )

        said = anyio.run(from_a_thread)

        assert said == families.Judged(1, 3)
        body = json.loads(server.seen[0].body)
        assert "How to tell a real threat" in "".join(block["text"] for block in body["system"])
        assert "F1: ET SCAN Potential SSH Scan from <address>" in body["messages"][0]["content"]
        assert "45.33.32" not in body["messages"][0]["content"].split("example from")[0]
        call = session.scalars(select(AiCall)).one()
        assert (call.purpose, call.about) == ("families", "1 family")
        session.expire_all()
        assert family.ai_class == "probe"
        assert family.call_id == call.id

    def test_nothing_is_asked_when_ai_is_off(self, session: Session, settings: Settings) -> None:
        family = kind(session, 3)

        said = families.ask_now(session, context(settings, Log()), [family.id], NOW)

        assert isinstance(said, families.NotJudged)
        assert said.reason.startswith("AI is turned off.")
        assert session.scalars(select(AiCall)).all() == []

    def test_a_kind_with_nothing_going_is_not_asked_about(
        self, session: Session, settings: Settings
    ) -> None:
        ready(session, settings)

        said = families.ask_now(session, context(settings, Log()), [12345])

        assert said == families.NotJudged("None of those has an incident going on.")


class TestTheLoop:
    def reader(self, session: Session, settings: Settings, serve: Serve, handler: Handler) -> Any:
        server = serve(handler)
        ready(session, settings)
        with_level(session, "maximum")
        return context(settings, Log(), server.url), server

    def new_session(self, session: Session) -> Callable[[], Session]:
        return sessionmaker(bind=session.get_bind(), expire_on_commit=False)

    def test_it_judges_what_the_level_asks_for_before_it_reads(
        self, session: Session, settings: Settings, serve: Serve, caplog: pytest.LogCaptureFixture
    ) -> None:
        def handle(seen: Seen):
            body = json.loads(seen.body)
            if "families" in json.dumps(body.get("output_config", {})):
                return judges(1)(seen)
            return anthropic_says("not a reading")(seen)

        where, server = self.reader(session, settings, serve, handle)
        family = kind(session, 3)

        with caplog.at_level(logging.INFO, "app.ai.run"):
            count = asyncio.run(run.judge_once(self.new_session(session), where))

        assert count == 1
        assert "The AI judged 1 families, an answer for 3 incidents" in caplog.text
        session.expire_all()
        assert family.ai_class == "probe"
        assert len(server.seen) == 1

    def test_nothing_is_judged_when_there_is_nothing_to_judge(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        where, server = self.reader(session, settings, serve, judges(1))

        assert asyncio.run(run.judge_once(self.new_session(session), where)) == 0
        assert server.seen == []

    def test_a_failure_is_logged_and_nothing_is_kept(
        self, session: Session, settings: Settings, serve: Serve, caplog: pytest.LogCaptureFixture
    ) -> None:
        where, _ = self.reader(session, settings, serve, anthropic_says("it is a scan"))
        family = kind(session, 3)

        with caplog.at_level(logging.WARNING, "app.ai.run"):
            count = asyncio.run(run.judge_once(self.new_session(session), where))

        assert count == 0
        assert "The AI didn't judge the families" in caplog.text
        session.expire_all()
        assert family.ai_class is None

    def test_a_kind_that_has_gone_is_not_asked_about(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        where, server = self.reader(session, settings, serve, judges(1))

        said = asyncio.run(run.judge_families(self.new_session(session), where, [12345]))

        assert said == families.NotJudged("None of those has an incident going on.")
        assert server.seen == []

    def test_nothing_is_judged_when_the_ai_is_turned_off_between_planning_and_asking(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        where, server = self.reader(session, settings, serve, judges(1))
        family = kind(session, 3)
        service.usage(session, NOW).enabled = False
        session.commit()

        said = asyncio.run(run.judge_families(self.new_session(session), where, [family.id]))

        assert isinstance(said, families.NotJudged)
        assert said.reason.startswith("AI is turned off.")
        assert server.seen == []

    def test_a_run_counts_what_it_judged_and_what_it_read(
        self, session: Session, settings: Settings, serve: Serve
    ) -> None:
        def handle(seen: Seen):
            body = json.dumps(json.loads(seen.body).get("output_config", {}))
            if '"families"' in body:
                return judges(1)(seen)
            return anthropic_says("not a reading")(seen)

        where, _ = self.reader(session, settings, serve, handle)
        kind(session, 3, severity=3, confidence=70)

        count = asyncio.run(run.read_once(self.new_session(session), where))

        assert count == 1


def test_a_family_can_be_found_by_a_test_that_counts_rows(session: Session) -> None:
    kind(session, 2)

    assert session.scalar(select(func.count()).select_from(IncidentFamily)) == 1
