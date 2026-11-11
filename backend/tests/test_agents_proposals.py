"""What the cleanup agent suggests and what is done with it: suggestions are kept once, applied in
ways that can be taken back, and the surest are applied by the agent itself only where it may."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import proposals
from app.audit import Action
from app.incidents import cleanup
from app.models import Agent, AgentProposal, AuditEvent, Incident, VerdictRule
from app.models.base import utcnow
from tests.test_agents_api import BASE, headers, ran, stored
from tests.test_ai_service import NOW
from tests.test_ai_triage import ATTACKER, incident, kept, signals
from tests.test_incidents_cleanup import scans

DAY = timedelta(days=1)


def found(session: Session) -> list[cleanup.Candidate]:
    return cleanup.find(session, NOW)


def run_of(session: Session, agent: Agent) -> int:
    return ran(session, agent).id


def record(
    session: Session,
    agent: Agent,
    candidates: list[cleanup.Candidate],
    rejected: set[str],
    *,
    auto: bool,
) -> tuple[list[AgentProposal], list[AgentProposal]]:
    return proposals.record(
        session, agent.id, run_of(session, agent), candidates, rejected, NOW, auto=auto
    )


def keep(session: Session, agent_id: int, **changes: object) -> AgentProposal:
    fields: dict[str, object] = {
        "agent_id": agent_id,
        "kind": "duplicates",
        "key": "duplicates-x",
        "title": "Two say the same",
        "detail": "d",
        "action": "dismiss",
        "incident_ids": [],
        "confidence": 85,
        "status": "pending",
        "created_at": NOW,
        **changes,
    }
    row = AgentProposal(**fields)
    session.add(row)
    session.commit()
    return row


class TestKeepingSuggestions:
    def test_what_was_found_is_kept_once_and_what_was_turned_down_or_rejected_is_not(
        self, session: Session
    ) -> None:
        agent = stored(session)
        scans(session, 2)
        incident(session, subject="198.51.100.40", last_seen_at=NOW - 9 * DAY, title="Old")
        session.commit()
        every = found(session)

        made, done = record(session, agent, every, {every[0].key}, auto=False)

        assert [item.key for item in made] == [every[1].key]
        assert done == []
        assert made[0].status == "pending"
        assert made[0].incident_ids == list(every[1].incidents)
        again, _ = record(session, agent, every, set(), auto=False)
        assert [item.key for item in again] == [every[0].key]
        assert record(session, agent, every, set(), auto=False)[0] == []

    def test_the_agent_applies_only_what_it_is_surest_of_and_only_when_it_may(
        self, session: Session
    ) -> None:
        agent = stored(session)
        first, second = scans(session, 2)
        mild = incident(session, subject="198.51.100.9", title="Scan of ssh", severity=1)
        incident(session, subject="198.51.100.40", last_seen_at=NOW - 9 * DAY, title="Old")
        session.commit()
        assert first
        assert second
        assert mild.id
        every = found(session)

        made, done = record(session, agent, every, set(), auto=True)

        assert {item.kind: item.status for item in made} == {
            "stale": "applied",
            "duplicates": "pending",
        }
        assert [item.kind for item in done] == ["stale"]
        assert done[0].decided_by == "agent"
        audited = session.scalars(
            select(AuditEvent).where(AuditEvent.action == Action.AGENT_PROPOSAL_APPLIED.value)
        ).all()
        assert [event.detail["by"] for event in audited if event.detail] == ["agent"]

    def test_a_suggestion_that_would_change_nothing_is_not_counted_as_done(
        self, session: Session
    ) -> None:
        agent = stored(session)
        old = incident(session, last_seen_at=NOW - 9 * DAY)
        session.commit()
        every = found(session)
        old.status = "resolved"
        session.commit()

        made, done = record(session, agent, every, set(), auto=True)

        assert [item.status for item in made] == ["dismissed"]
        assert done == []


class TestApplying:
    def test_duplicates_are_dismissed_and_can_be_put_back(self, session: Session) -> None:
        agent = stored(session)
        first, second, third = scans(session)
        session.commit()
        [candidate] = cleanup.duplicates(session)
        [proposal], _ = record(session, agent, [candidate], set(), auto=False)

        changed = proposals.apply(session, proposal, "owner", NOW)
        session.commit()

        assert changed == 2
        assert proposal.status == "applied"
        assert proposal.decided_by == "owner"
        statuses = {item.id: item.status for item in session.scalars(select(Incident))}
        assert statuses == {first: "open", second: "dismissed", third: "dismissed"}

        restored = proposals.undo(session, proposal, NOW)
        session.commit()

        assert restored == 2
        assert proposal.status == "undone"
        assert {item.status for item in session.scalars(select(Incident))} == {"open"}

    def test_stale_incidents_are_resolved(self, session: Session) -> None:
        agent = stored(session)
        old = incident(session, last_seen_at=NOW - 9 * DAY)
        session.commit()
        [proposal], _ = record(session, agent, cleanup.stale(session, NOW), set(), auto=False)

        proposals.apply(session, proposal, "owner", NOW)

        assert session.get_one(Incident, old.id).status == "resolved"

    def test_a_verdict_is_given_for_what_the_ai_is_sure_is_noise_and_taken_back(
        self, session: Session
    ) -> None:
        agent = stored(session)
        noisy = incident(session)
        signals(session, noisy)
        kept(session, noisy, classification="noise", confidence=90)
        session.commit()
        [proposal], _ = proposals.record(
            session,
            agent.id,
            run_of(session, agent),
            cleanup.benign(session),
            set(),
            NOW,
            auto=False,
        )

        changed = proposals.apply(session, proposal, "owner", NOW)
        session.commit()

        assert changed == 1
        [rule] = session.scalars(select(VerdictRule)).all()
        assert (str(rule.address), rule.verdict, rule.note) == (
            ATTACKER,
            "not_suspicious",
            "Set by the cleanup agent.",
        )

        proposals.undo(session, proposal, NOW)
        session.commit()

        assert session.scalars(select(VerdictRule)).all() == []

    def test_incidents_dealt_with_since_are_left_alone(self, session: Session) -> None:
        agent = stored(session)
        first, second, third = scans(session)
        session.commit()
        [candidate] = cleanup.duplicates(session)
        [proposal], _ = record(session, agent, [candidate], set(), auto=False)
        session.get_one(Incident, second).status = "resolved"
        session.commit()

        assert proposals.apply(session, proposal, "owner", NOW) == 1
        assert session.get_one(Incident, second).status == "resolved"
        assert first
        assert third

    def test_a_decided_suggestion_cannot_be_decided_again(self, session: Session) -> None:
        agent = stored(session)
        done = keep(session, agent.id, status="applied")
        turned_down = keep(session, agent.id, key="b", status="dismissed")

        for call in (
            lambda: proposals.apply(session, done, "owner", NOW),
            lambda: proposals.dismiss(turned_down, NOW),
        ):
            with pytest.raises(proposals.Settled, match="already been"):
                call()
        with pytest.raises(proposals.Settled, match="Only a suggestion that was applied"):
            proposals.undo(session, turned_down, NOW)


class TestDismissing:
    def test_a_suggestion_turned_down_stays_down(self, session: Session) -> None:
        agent = stored(session)
        proposal = keep(session, agent.id)

        proposals.dismiss(proposal, NOW)

        assert (proposal.status, proposal.decided_by, proposal.decided_at) == (
            "dismissed",
            "owner",
            NOW,
        )


def test_old_decisions_and_suggestions_nobody_decided_on_are_forgotten(session: Session) -> None:
    agent = stored(session)
    keep(session, agent.id, key="old-done", status="applied", decided_at=NOW - 100 * DAY)
    keep(session, agent.id, key="new-done", status="applied", decided_at=NOW - DAY)
    keep(session, agent.id, key="old-wait", created_at=NOW - 40 * DAY)
    keep(session, agent.id, key="new-wait", created_at=NOW - DAY)

    proposals.forget(session, NOW)

    assert sorted(session.scalars(select(AgentProposal.key))) == ["new-done", "new-wait"]


class TestTheApi:
    def suggested(self, session: Session, **changes: object) -> AgentProposal:
        agent = stored(session, template="noise_cleaner", name="Tidy")
        first, second = scans(session, 2)
        session.commit()
        assert first
        return keep(session, agent.id, incident_ids=[second], keep_id=first, **changes)

    def test_what_waits_and_what_was_decided_is_listed(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        waiting = self.suggested(session, key="a", confidence=70)
        agent_id = waiting.agent_id
        keep(session, agent_id, key="b", confidence=95)
        keep(session, agent_id, key="c", status="applied", decided_by="agent", decided_at=utcnow())
        keep(session, agent_id, key="d", status="undone", decided_at=utcnow() - 40 * DAY)

        body = client.get(f"{BASE}/proposals").json()

        assert [item["confidence"] for item in body["pending"]] == [95, 70]
        assert [item["status"] for item in body["recent"]] == ["applied"]
        assert body["recent"][0]["decided_by"] == "agent"
        assert body["pending"][0]["agent_name"] == "Tidy"

    def test_the_overview_and_the_agent_count_what_waits(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        waiting = self.suggested(session)
        keep(session, waiting.agent_id, key="b", status="dismissed", decided_at=utcnow())

        overview = client.get(BASE).json()
        detail = client.get(f"{BASE}/{waiting.agent_id}").json()

        assert overview["proposals"] == 1
        assert overview["agents"][0]["proposals"] == 1
        assert [item["id"] for item in detail["suggestions"]["pending"]] == [waiting.id]
        assert len(detail["suggestions"]["recent"]) == 1

    def test_a_suggestion_is_applied_taken_back_and_each_is_in_the_activity_log(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        waiting = self.suggested(session)
        target = waiting.incident_ids[0]

        applied = client.post(f"{BASE}/proposals/{waiting.id}/apply", headers=headers(csrf_token))

        assert applied.status_code == 200, applied.text
        assert applied.json()["status"] == "applied"
        assert applied.json()["decided_by"] == "owner"
        session.expire_all()
        assert session.get_one(Incident, target).status == "dismissed"

        back = client.post(f"{BASE}/proposals/{waiting.id}/undo", headers=headers(csrf_token))

        assert back.json()["status"] == "undone"
        session.expire_all()
        assert session.get_one(Incident, target).status == "open"
        actions = [
            event.action
            for event in session.scalars(select(AuditEvent).order_by(AuditEvent.id))
            if event.action.startswith("agent.proposal")
        ]
        assert actions == ["agent.proposal_applied", "agent.proposal_undone"]

    def test_a_suggestion_can_be_turned_down(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        waiting = self.suggested(session)

        response = client.post(
            f"{BASE}/proposals/{waiting.id}/dismiss", headers=headers(csrf_token)
        )

        assert response.json()["status"] == "dismissed"

    def test_one_that_is_decided_says_so_and_one_that_is_not_there_is_not_found(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        done = self.suggested(session, status="dismissed")

        refused = client.post(f"{BASE}/proposals/{done.id}/apply", headers=headers(csrf_token))
        missing = client.post(f"{BASE}/proposals/9999/apply", headers=headers(csrf_token))

        assert refused.status_code == 409
        assert "already been dismissed" in refused.json()["detail"]
        assert missing.status_code == 404

    def test_a_change_needs_the_security_token(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        waiting = self.suggested(session)

        response = client.post(f"{BASE}/proposals/{waiting.id}/apply")

        assert response.status_code == 403
