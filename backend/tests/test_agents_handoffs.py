"""Agents asking each other for help: a hand-off is kept as it was asked, starts a run of the
other kind of agent, and is refused, with the reason, when it would break a limit."""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import handoffs
from app.agents.handoffs import Asked
from app.audit import Action
from app.models import AgentHandoff, AgentRun, AgentSettings
from tests.test_agents_api import audited, ran
from tests.test_agents_run import made
from tests.test_ai_service import NOW


def ask(
    kind: str = "incident_investigator",
    *,
    subject: str = "Incident 4",
    seen: bool = True,
    incident: int | None = 4,
) -> Asked:
    return Asked(kind, subject, "It scanned three devices.", incident, seen=seen)


def asker(session: Session) -> AgentRun:
    """A run of an orchestrator that was started by the owner."""
    agent = made(session, "security_orchestrator", name="Orchestrator")
    run = ran(session, agent, "running", trigger="manual")
    return run


class TestMakingAHandoff:
    def test_it_starts_a_run_of_the_agent_of_that_kind_and_is_kept_as_asked(
        self, session: Session
    ) -> None:
        run = asker(session)
        investigator = made(session, "incident_investigator", name="Investigator")

        [kept] = handoffs.hand_off(session, run, [ask()], NOW)

        assert (kept.status, kept.refusal, kept.depth) == ("queued", None, 1)
        assert (kept.from_agent_id, kept.to_agent_id) == (run.agent_id, investigator.id)
        assert (kept.subject, kept.incident_id) == ("Incident 4", 4)
        started = session.get_one(AgentRun, kept.to_run_id)
        assert (started.agent_id, started.trigger, started.status) == (
            investigator.id,
            "handoff",
            "queued",
        )
        [event] = audited(session, Action.AGENT_HANDOFF)
        assert event.detail == {
            "handoff": kept.id,
            "from": run.agent_id,
            "to": investigator.id,
            "kind": "incident_investigator",
            "run": run.id,
            "refusal": "",
        }

    def test_a_run_started_by_a_handoff_knows_how_deep_it_is_and_who_asked(
        self, session: Session
    ) -> None:
        run = asker(session)
        investigator = made(session, "incident_investigator", name="Investigator")
        [first] = handoffs.hand_off(session, run, [ask()], NOW)
        assert first.to_run_id is not None

        assert handoffs.depth_of(session, run.id) == 0
        assert handoffs.depth_of(session, first.to_run_id) == 1
        assert handoffs.chain(session, first.to_run_id) == [investigator.id, run.agent_id]


class TestRefusing:
    def refused(self, session: Session, run: AgentRun, asked: Asked) -> str:
        [kept] = handoffs.hand_off(session, run, [asked], NOW)
        assert kept.status == "refused"
        assert kept.to_run_id is None
        assert audited(session, Action.AGENT_HANDOFF)[-1].outcome == "failure"
        return kept.refusal or ""

    def test_a_kind_that_tests_the_network_cannot_be_asked(self, session: Session) -> None:
        run = asker(session)
        made(session, "exposure_scanner")

        words = self.refused(session, run, ask("exposure_scanner"))

        assert "only the owner starts" in words

    def test_a_kind_that_is_not_known_cannot_be_asked(self, session: Session) -> None:
        run = asker(session)

        assert "cannot be asked" in self.refused(session, run, ask("not_a_kind"))

    def test_a_subject_it_never_looked_at_is_refused(self, session: Session) -> None:
        run = asker(session)
        made(session, "incident_investigator")

        words = self.refused(session, run, ask(seen=False, subject="incident 999", incident=None))

        assert words == "It named something it never looked at."

    def test_a_kind_with_no_agent_that_is_on_is_refused(self, session: Session) -> None:
        run = asker(session)
        made(session, "incident_investigator", enabled=False)

        words = self.refused(session, run, ask())

        assert words == "You have no Incident investigator agent that is on."

    def test_an_agent_cannot_ask_for_itself_or_for_one_that_asked_it(
        self, session: Session
    ) -> None:
        run = asker(session)

        assert "circle" in self.refused(session, run, ask("security_orchestrator"))

        investigator = made(session, "incident_investigator", name="Investigator")
        [first] = handoffs.hand_off(session, run, [ask()], NOW)
        assert first.to_run_id is not None
        second_run = session.get_one(AgentRun, first.to_run_id)
        assert investigator.id == second_run.agent_id
        assert "circle" in self.refused(session, second_run, ask("security_orchestrator"))

    def test_it_goes_no_deeper_than_the_limit(self, session: Session) -> None:
        run = asker(session)
        runs = [run]
        for kind in ("incident_investigator", "threat_hunter"):
            made(session, kind, name=kind)
            [kept] = handoffs.hand_off(session, runs[-1], [ask(kind)], NOW)
            assert kept.to_run_id is not None
            runs.append(session.get_one(AgentRun, kept.to_run_id))
        made(session, "network_analyst")

        words = self.refused(session, runs[-1], ask("network_analyst"))

        assert words == f"Hand-offs go {handoffs.MAX_DEPTH} deep at most."

    def test_a_run_asks_for_at_most_three(self, session: Session) -> None:
        run = asker(session)
        kinds = ["incident_investigator", "threat_hunter", "network_analyst", "endpoint_analyst"]
        for kind in kinds:
            made(session, kind, name=kind)

        kept = handoffs.hand_off(session, run, [ask(kind) for kind in kinds], NOW)

        assert [item.status for item in kept] == ["queued", "queued", "queued", "refused"]
        assert (
            kept[-1].refusal == f"An agent asks for at most {handoffs.PER_RUN} hand-offs in a run."
        )

    def test_only_so_many_are_made_in_a_day(self, session: Session) -> None:
        run = asker(session)
        made(session, "incident_investigator")
        for number in range(handoffs.PER_DAY):
            session.add(
                AgentHandoff(
                    run_id=run.id,
                    from_agent_id=run.agent_id,
                    to_kind="threat_hunter",
                    subject="x",
                    reason="y",
                    status="queued",
                    depth=1,
                    created_at=NOW - timedelta(hours=number),
                )
            )
        session.commit()

        words = self.refused(session, run, ask())

        assert "10 hand-offs have been made in the last day" in words
        assert handoffs.made_today(session, NOW) == handoffs.PER_DAY

    def test_an_agent_that_is_busy_is_not_asked_again(self, session: Session) -> None:
        run = asker(session)
        investigator = made(session, "incident_investigator", name="Investigator")
        ran(session, investigator, "queued")

        words = self.refused(session, run, ask())

        assert words == "Investigator already has a run waiting or going."

    def test_the_agents_spending_limit_holds(self, session: Session) -> None:
        run = asker(session)
        made(session, "incident_investigator")
        session.add(AgentSettings(id=1, daily_limit_micros=0, updated_at=NOW))
        session.commit()

        words = self.refused(session, run, ask())

        assert "limit" in words
        assert (
            session.scalars(select(AgentRun).where(AgentRun.trigger == "handoff")).first() is None
        )
