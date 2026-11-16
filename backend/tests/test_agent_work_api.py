"""What the agents hand to each other and to the owner over the API: hand-offs, the steps the
response planner proposes and the owner decides, and the timelines."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.audit import Action
from app.models import AgentHandoff, AgentPlanStep, AgentRun, User
from app.models.base import utcnow
from tests.test_agents_api import BASE, audited, headers, ran, stored


def step(session: Session, agent_id: int, **changes: object) -> AgentPlanStep:
    fields: dict[str, object] = {
        "agent_id": agent_id,
        "key": "k",
        "title": "Isolate the camera",
        "detail": "Move it.",
        "risk": "It goes offline.",
        "incident_id": 3,
        "status": "pending",
        "created_at": utcnow(),
        **changes,
    }
    row = AgentPlanStep(**fields)
    session.add(row)
    session.commit()
    return row


def test_it_is_only_for_someone_signed_in(client: TestClient, account: User) -> None:
    for method, path in (
        ("get", f"{BASE}/handoffs"),
        ("get", f"{BASE}/plan-steps"),
        ("post", f"{BASE}/plan-steps/1/approve"),
        ("post", f"{BASE}/plan-steps/1/dismiss"),
        ("get", f"{BASE}/timeline?incident_id=1"),
        ("get", f"{BASE}/1/runs/1/timeline"),
    ):
        assert client.request(method, path).status_code == 401, (method, path)


class TestHandoffs:
    def test_they_are_listed_with_the_limits_and_who_asked_whom(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        boss = stored(session, "security_orchestrator", name="Orchestrator")
        worker = stored(session, "incident_investigator", name="Investigator")
        first = ran(session, boss)
        second = ran(session, worker, trigger="handoff")
        session.add_all(
            [
                AgentHandoff(
                    run_id=first.id,
                    from_agent_id=boss.id,
                    to_kind="incident_investigator",
                    to_agent_id=worker.id,
                    to_run_id=second.id,
                    subject="Incident 4",
                    incident_id=4,
                    reason="Look.",
                    status="queued",
                    depth=1,
                    created_at=utcnow(),
                ),
                AgentHandoff(
                    run_id=first.id,
                    from_agent_id=boss.id,
                    to_kind="network_analyst",
                    subject="Device 2",
                    reason="Why.",
                    status="refused",
                    refusal="You have no Network threat analyst agent that is on.",
                    depth=1,
                    created_at=utcnow(),
                ),
            ]
        )
        session.commit()

        body = client.get(f"{BASE}/handoffs").json()

        assert (body["max_depth"], body["per_day"], body["made_today"]) == (2, 10, 1)
        refused, queued = body["handoffs"]
        assert (refused["status"], refused["to_agent"], refused["to_agent_id"]) == (
            "refused",
            "Network threat analyst",
            None,
        )
        assert (queued["from_agent"], queued["to_agent"], queued["incident_id"]) == (
            "Orchestrator",
            "Investigator",
            4,
        )
        assert queued["to_run_id"] == second.id

    def test_a_run_started_by_one_says_so(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        worker = stored(session, "incident_investigator")
        run = ran(session, worker, trigger="handoff")

        body = client.get(f"{BASE}/{worker.id}/runs/{run.id}").json()

        assert body["trigger"] == "handoff"


class TestSteps:
    def test_the_waiting_and_the_recently_decided_are_listed_and_can_be_narrowed_to_an_incident(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        planner = stored(session, "response_planner", name="Planner")
        waiting = step(session, planner.id)
        step(session, planner.id, key="a", incident_id=9)
        decided = step(session, planner.id, key="b", status="approved", decided_at=utcnow())
        step(
            session,
            planner.id,
            key="c",
            status="dismissed",
            decided_at=utcnow().replace(year=2020),
        )

        body = client.get(f"{BASE}/plan-steps").json()

        assert [item["id"] for item in body["pending"]] == [waiting.id + 1, waiting.id]
        assert [item["id"] for item in body["recent"]] == [decided.id]
        assert body["pending"][1]["agent_name"] == "Planner"
        narrowed = client.get(f"{BASE}/plan-steps", params={"incident_id": 3}).json()
        assert [item["id"] for item in narrowed["pending"]] == [waiting.id]
        assert [item["id"] for item in narrowed["recent"]] == [decided.id]

    def test_a_step_is_approved_or_dismissed_once_and_each_is_in_the_activity_log(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        planner = stored(session, "response_planner")
        first = step(session, planner.id)
        second = step(session, planner.id, key="two")

        approved = client.post(f"{BASE}/plan-steps/{first.id}/approve", headers=headers(csrf_token))
        dismissed = client.post(
            f"{BASE}/plan-steps/{second.id}/dismiss", headers=headers(csrf_token)
        )
        again = client.post(f"{BASE}/plan-steps/{first.id}/dismiss", headers=headers(csrf_token))

        assert (approved.json()["status"], dismissed.json()["status"]) == ("approved", "dismissed")
        assert approved.json()["decided_at"] is not None
        assert again.status_code == 409
        assert "already been approved" in again.json()["detail"]
        [event] = audited(session, Action.AGENT_PLAN_APPROVED)
        assert event.detail == {
            "step": first.id,
            "agent": planner.id,
            "incident": 3,
            "title": "Isolate the camera",
        }
        assert len(audited(session, Action.AGENT_PLAN_DISMISSED)) == 1

    def test_a_step_that_is_not_there_is_not_found_and_a_change_needs_the_token(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        planner = stored(session, "response_planner")
        waiting = step(session, planner.id)

        missing = client.post(f"{BASE}/plan-steps/999/approve", headers=headers(csrf_token))
        bare = client.post(f"{BASE}/plan-steps/{waiting.id}/approve")

        assert missing.status_code == 404
        assert bare.status_code == 403


class TestTimelines:
    def test_a_run_has_one_that_is_not_found_for_another_agents_run(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        agent = stored(session)
        other = stored(session)
        run = ran(session, agent, finished_at=utcnow(), summary="Quiet.")

        body = client.get(f"{BASE}/{agent.id}/runs/{run.id}/timeline").json()

        assert [(item["kind"], item["title"]) for item in body] == [("concluded", "Quiet.")]
        assert body[0]["agent"] == "Stored"
        assert client.get(f"{BASE}/{other.id}/runs/{run.id}/timeline").status_code == 404
        assert client.get(f"{BASE}/{agent.id}/runs/999/timeline").status_code == 404

    def test_an_incident_has_one_and_it_needs_an_incident(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        agent = stored(session, "response_planner", name="Planner")
        step(session, agent.id)

        body = client.get(f"{BASE}/timeline", params={"incident_id": 3}).json()

        assert [item["kind"] for item in body] == ["planned"]
        assert body[0]["run_id"] is None
        assert client.get(f"{BASE}/timeline").status_code == 422
        assert client.get(f"{BASE}/timeline", params={"incident_id": 0}).status_code == 422


def test_a_run_is_not_kept_by_the_handoff_that_made_it(session: Session) -> None:
    boss = stored(session, "security_orchestrator")
    worker = stored(session, "incident_investigator")
    first, second = ran(session, boss), ran(session, worker, trigger="handoff")
    row = AgentHandoff(
        run_id=first.id,
        from_agent_id=boss.id,
        to_kind="incident_investigator",
        to_run_id=second.id,
        subject="x",
        reason="y",
        status="queued",
        depth=1,
        created_at=utcnow(),
    )
    session.add(row)
    session.commit()

    session.delete(second)
    session.commit()
    session.refresh(row)

    assert row.to_run_id is None
    assert session.get(AgentRun, first.id) is not None
