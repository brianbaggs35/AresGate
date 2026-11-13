"""The agents' API: making, changing and removing agents, asking for runs, and what is shown of
each agent and run."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import catalog
from app.audit import Action
from app.models import Agent, AgentRun, AgentStep, AuditEvent, User
from app.models.base import utcnow
from tests.helpers import OTHER_ORIGIN

BASE = "/api/agents"


def headers(token: str) -> dict[str, str]:
    return {"X-CSRF-Token": token}


def make(client: TestClient, token: str, **body: object) -> dict[str, object]:
    response = client.post(
        BASE, json={"template": "threat_hunter", "name": "Hunter", **body}, headers=headers(token)
    )
    assert response.status_code == 201, response.text
    return response.json()


def stored(session: Session, template: str = "threat_hunter", **changes: object) -> Agent:
    fields: dict[str, object] = {"name": "Stored", "template": template, "goal": ""}
    fields.update(changes)
    agent = Agent(**fields)
    session.add(agent)
    session.commit()
    return agent


def ran(session: Session, agent: Agent, status: str = "succeeded", **changes: object) -> AgentRun:
    fields: dict[str, object] = {
        "agent_id": agent.id,
        "trigger": "manual",
        "status": status,
        "requested_at": utcnow(),
    }
    fields.update(changes)
    run = AgentRun(**fields)
    session.add(run)
    session.commit()
    return run


def item(severity: str, title: str = "") -> dict[str, object]:
    return {"severity": severity, "title": title, "detail": "", "cites": []}


def audited(session: Session, action: Action) -> list[AuditEvent]:
    session.expire_all()
    return list(session.scalars(select(AuditEvent).where(AuditEvent.action == action.value)))


def test_it_is_only_for_someone_signed_in(client: TestClient, account: User) -> None:
    for method, path in (
        ("get", BASE),
        ("post", BASE),
        ("get", f"{BASE}/1"),
        ("put", f"{BASE}/1"),
        ("delete", f"{BASE}/1"),
        ("post", f"{BASE}/1/runs"),
        ("get", f"{BASE}/1/runs/1"),
        ("post", f"{BASE}/1/runs/1/cancel"),
    ):
        response = client.request(method, path)
        assert response.status_code == 401, (method, path)


def test_a_change_from_another_website_is_refused(client: TestClient, csrf_token: str) -> None:
    response = client.post(
        BASE,
        json={"template": "threat_hunter", "name": "x"},
        headers={**headers(csrf_token), "Origin": OTHER_ORIGIN},
    )

    assert response.status_code == 403


class TestTheOverview:
    def test_an_install_with_none_offers_what_one_can_be_made_from(
        self, client: TestClient, csrf_token: str
    ) -> None:
        body = client.get(BASE).json()

        assert body["agents"] == []
        assert [item["key"] for item in body["templates"]] == [
            item.key for item in catalog.TEMPLATES
        ]
        scanner = next(item for item in body["templates"] if item["key"] == "exposure_scanner")
        assert scanner["active"] is True
        assert scanner["interval_minutes"] is None
        assert scanner["tools"] == ["device"]

    def test_it_says_why_the_ai_would_not_be_asked(
        self, client: TestClient, csrf_token: str
    ) -> None:
        assert client.get(BASE).json()["ai"]

    def test_each_agent_is_shown_with_how_it_is_going(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        agent = stored(session, interval_minutes=60)
        ran(session, agent, "failed")
        ran(
            session,
            agent,
            "succeeded",
            findings=[item("low", "a"), item("high", "b")],
            summary="Done.",
            rounds=2,
        )

        shown = client.get(BASE).json()["agents"][0]

        assert shown["recent"] == ["failed", "succeeded"]
        assert shown["state"] == "idle"
        assert shown["template_name"] == "Threat hunter"
        assert shown["icon"] == "radar"
        assert shown["last_run"]["findings"] == 2
        assert shown["last_run"]["worst"] == "high"
        assert shown["last_run"]["summary"] == "Done."
        assert shown["last_run"]["rounds"] == 2

    def test_a_run_with_no_findings_has_no_worst(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        ran(session, stored(session))

        assert client.get(BASE).json()["agents"][0]["last_run"]["worst"] is None

    @pytest.mark.parametrize(
        ("status", "enabled", "state"),
        [
            ("queued", True, "queued"),
            ("running", True, "running"),
            ("succeeded", False, "paused"),
            ("cancelled", True, "idle"),
        ],
    )
    def test_what_an_agent_is_doing(
        self,
        client: TestClient,
        csrf_token: str,
        session: Session,
        status: str,
        enabled: bool,
        state: str,
    ) -> None:
        agent = stored(session, enabled=enabled, interval_minutes=60)
        ran(session, agent, status)

        assert client.get(BASE).json()["agents"][0]["state"] == state

    def test_an_agent_that_never_ran_has_no_last_run_and_is_idle(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        stored(session)

        shown = client.get(BASE).json()["agents"][0]

        assert (shown["last_run"], shown["recent"], shown["state"]) == (None, [], "idle")

    def test_an_agent_that_has_no_schedule_is_never_paused(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        stored(session, enabled=False)

        assert client.get(BASE).json()["agents"][0]["state"] == "idle"

    def test_an_agent_of_a_kind_that_is_gone_is_still_shown(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        stored(session, template="retired")

        shown = client.get(BASE).json()["agents"][0]

        assert (shown["template_name"], shown["icon"], shown["active"]) == ("retired", "bot", False)

    def test_the_agents_are_in_the_order_they_were_made(
        self, client: TestClient, csrf_token: str
    ) -> None:
        make(client, csrf_token, name="First")
        make(client, csrf_token, name="Second")

        names = [item["name"] for item in client.get(BASE).json()["agents"]]

        assert names == ["First", "Second"]


class TestMakingOne:
    def test_it_is_made_from_a_template_and_audited(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        made = make(client, csrf_token, name="  Hunter  ", goal=" Watch the camera ")

        assert made["name"] == "Hunter"
        assert made["goal"] == "Watch the camera"
        assert made["enabled"] is True
        assert made["interval_minutes"] is None
        assert made["next_run_at"] is None
        assert made["state"] == "idle"
        assert len(audited(session, Action.AGENT_CREATED)) == 1

    def test_a_schedule_sets_when_it_runs_first(self, client: TestClient, csrf_token: str) -> None:
        made = make(client, csrf_token, interval_minutes=30)

        assert made["interval_minutes"] == 30
        assert made["next_run_at"] is not None

    def test_one_that_is_off_has_no_next_run(self, client: TestClient, csrf_token: str) -> None:
        made = make(client, csrf_token, interval_minutes=30, enabled=False)

        assert (made["next_run_at"], made["state"]) == (None, "paused")

    def test_a_kind_that_does_not_exist_is_refused(
        self, client: TestClient, csrf_token: str
    ) -> None:
        response = client.post(
            BASE, json={"template": "nothing", "name": "x"}, headers=headers(csrf_token)
        )

        assert response.status_code == 422
        assert "isn't a kind of agent" in response.json()["detail"]

    def test_one_that_tests_the_network_cannot_be_on_a_schedule(
        self, client: TestClient, csrf_token: str
    ) -> None:
        response = client.post(
            BASE,
            json={"template": "exposure_scanner", "name": "x", "interval_minutes": 60},
            headers=headers(csrf_token),
        )

        assert response.status_code == 422
        assert "only runs when you start it" in response.json()["detail"]

    def test_one_that_tests_the_network_may_be_allowed_to_when_it_is_made(
        self, client: TestClient, csrf_token: str
    ) -> None:
        made = make(client, csrf_token, template="exposure_scanner", allow_active=True)

        assert made["allow_active"] is True

    def test_one_that_does_not_test_the_network_is_never_allowed_to(
        self, client: TestClient, csrf_token: str
    ) -> None:
        assert make(client, csrf_token, allow_active=True)["allow_active"] is False

    @pytest.mark.parametrize(
        "body",
        [
            {"name": ""},
            {"name": "x" * 81},
            {"interval_minutes": 4},
            {"interval_minutes": 7 * 24 * 60 + 1},
            {"goal": "x" * 2001},
            {"unknown": True},
        ],
    )
    def test_what_is_not_allowed_is_refused(
        self, client: TestClient, csrf_token: str, body: dict[str, object]
    ) -> None:
        response = client.post(
            BASE,
            json={"template": "threat_hunter", "name": "x", **body},
            headers=headers(csrf_token),
        )

        assert response.status_code == 422


class TestOne:
    def test_it_comes_with_its_runs_its_kind_and_its_graph(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        agent = stored(session)
        first = ran(session, agent)
        second = ran(session, agent)

        body = client.get(f"{BASE}/{agent.id}").json()

        assert [item["id"] for item in body["runs"]] == [second.id, first.id]
        assert body["template_info"]["key"] == "threat_hunter"
        assert {"source": "plan", "target": "act", "conditional": False} in body["graph"]
        assert any(edge["conditional"] for edge in body["graph"])

    def test_one_of_a_kind_that_is_gone_is_shown_as_a_hunter(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        agent = stored(session, template="retired")

        body = client.get(f"{BASE}/{agent.id}").json()

        assert body["template_info"]["key"] == "threat_hunter"

    def test_one_that_does_not_exist_is_not_found(
        self, client: TestClient, csrf_token: str
    ) -> None:
        response = client.get(f"{BASE}/999")

        assert (response.status_code, response.json()["detail"]) == (
            404,
            "There is no such agent.",
        )


class TestChangingOne:
    def change(self, client: TestClient, token: str, agent_id: object, **body: object):
        sent = {
            "name": "Renamed",
            "goal": "Something else",
            "interval_minutes": None,
            "enabled": True,
            "allow_active": False,
            **body,
        }
        return client.put(f"{BASE}/{agent_id}", json=sent, headers=headers(token))

    def test_it_is_changed_and_audited(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        agent = stored(session)

        response = self.change(client, csrf_token, agent.id)

        assert response.status_code == 200
        assert (response.json()["name"], response.json()["goal"]) == ("Renamed", "Something else")
        assert len(audited(session, Action.AGENT_CHANGED)) == 1

    def test_a_new_schedule_starts_the_count_from_now(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        agent = stored(session)

        shown = self.change(client, csrf_token, agent.id, interval_minutes=15).json()

        assert shown["interval_minutes"] == 15
        assert shown["next_run_at"] is not None

    def test_turning_a_schedule_off_forgets_the_next_run(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        agent = stored(session, interval_minutes=15, next_run_at=utcnow() + timedelta(minutes=5))

        shown = self.change(client, csrf_token, agent.id, interval_minutes=15, enabled=False).json()

        assert (shown["next_run_at"], shown["state"]) == (None, "paused")

    def test_a_change_that_leaves_the_schedule_alone_leaves_the_next_run_alone(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        soon = utcnow() + timedelta(minutes=5)
        agent = stored(session, interval_minutes=15, next_run_at=soon)

        shown = self.change(client, csrf_token, agent.id, interval_minutes=15).json()

        assert shown["next_run_at"].startswith(soon.strftime("%Y-%m-%dT%H:%M"))

    def test_what_it_may_do_is_only_for_a_kind_that_tests_the_network(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        scanner = stored(session, template="exposure_scanner")
        hunter = stored(session)

        allowed = self.change(client, csrf_token, scanner.id, allow_active=True).json()
        refused = self.change(client, csrf_token, hunter.id, allow_active=True).json()

        assert (allowed["allow_active"], refused["allow_active"]) == (True, False)

    def test_one_that_tests_the_network_cannot_be_put_on_a_schedule(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        scanner = stored(session, template="exposure_scanner")

        response = self.change(client, csrf_token, scanner.id, interval_minutes=60)

        assert response.status_code == 422

    def test_one_of_a_kind_that_is_gone_can_still_be_renamed(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        agent = stored(session, template="retired")

        response = self.change(client, csrf_token, agent.id, interval_minutes=60, allow_active=True)

        assert response.status_code == 200
        assert response.json()["allow_active"] is False

    def test_one_that_does_not_exist_is_not_found(
        self, client: TestClient, csrf_token: str
    ) -> None:
        assert self.change(client, csrf_token, 999).status_code == 404


class TestRemovingOne:
    def test_it_goes_with_its_runs_and_steps(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        agent = stored(session)
        run = ran(session, agent)
        session.add(AgentStep(run_id=run.id, seq=1, node="plan", title="Planned"))
        session.commit()

        response = client.delete(f"{BASE}/{agent.id}", headers=headers(csrf_token))

        assert response.status_code == 204
        session.expire_all()
        assert session.scalars(select(Agent)).all() == []
        assert session.scalars(select(AgentRun)).all() == []
        assert session.scalars(select(AgentStep)).all() == []
        assert len(audited(session, Action.AGENT_DELETED)) == 1

    def test_one_that_does_not_exist_is_not_found(
        self, client: TestClient, csrf_token: str
    ) -> None:
        response = client.delete(f"{BASE}/999", headers=headers(csrf_token))
        assert response.status_code == 404


class TestRuns:
    def test_a_run_is_asked_for_and_audited(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        agent = stored(session)

        response = client.post(f"{BASE}/{agent.id}/runs", headers=headers(csrf_token))

        assert response.status_code == 201
        assert (response.json()["status"], response.json()["trigger"]) == ("queued", "manual")
        assert len(audited(session, Action.AGENT_RUN_REQUESTED)) == 1

    def test_one_that_is_waiting_or_going_is_not_asked_for_twice(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        agent = stored(session)
        ran(session, agent, "running")

        response = client.post(f"{BASE}/{agent.id}/runs", headers=headers(csrf_token))

        assert response.status_code == 409
        assert "already has a run" in response.json()["detail"]

    def test_one_that_tests_the_network_has_to_be_allowed_first(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        agent = stored(session, template="exposure_scanner")

        response = client.post(f"{BASE}/{agent.id}/runs", headers=headers(csrf_token))

        assert response.status_code == 409
        assert "Allow this agent" in response.json()["detail"]
        assert session.scalars(select(AgentRun)).all() == []

    def test_one_that_does_not_exist_is_not_found(
        self, client: TestClient, csrf_token: str
    ) -> None:
        response = client.post(f"{BASE}/999/runs", headers=headers(csrf_token))
        assert response.status_code == 404

    def test_a_run_is_shown_with_its_steps_and_findings(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        agent = stored(session)
        run = ran(
            session,
            agent,
            findings=[
                {
                    "severity": "medium",
                    "title": "Scans",
                    "detail": "Many.",
                    "cites": [{"kind": "incident", "id": "3"}],
                    "status": "ongoing",
                },
                {"severity": "info"},
            ],
            call_ids=[4, 5],
            error="Nothing went wrong.",
        )
        session.add_all(
            [
                AgentStep(run_id=run.id, seq=2, node="act", title="Looked", detail={"n": 1}),
                AgentStep(run_id=run.id, seq=1, node="plan", title="Planned"),
            ]
        )
        session.commit()

        body = client.get(f"{BASE}/{agent.id}/runs/{run.id}").json()

        assert [step["title"] for step in body["steps"]] == ["Planned", "Looked"]
        assert body["steps"][1]["detail"] == {"n": 1}
        for shown in body["findings_list"]:
            del shown["first_seen_at"]
        assert body["findings_list"] == [
            {
                "severity": "medium",
                "title": "Scans",
                "detail": "Many.",
                "cites": [{"kind": "incident", "id": "3"}],
                "status": "ongoing",
                "action": "",
                "confidence": "medium",
                "runs_seen": 1,
                "evidence": [],
                "verify": "",
                "benign": "",
            },
            {
                "severity": "info",
                "title": "",
                "detail": "",
                "cites": [],
                "status": "new",
                "action": "",
                "confidence": "medium",
                "runs_seen": 1,
                "evidence": [],
                "verify": "",
                "benign": "",
            },
        ]
        assert body["by_severity"] == {"medium": 1, "info": 1}
        assert body["changes"] is None
        assert body["call_ids"] == [4, 5]
        assert body["error"] == "Nothing went wrong."

    def test_how_long_a_finding_has_been_reported_and_what_has_gone_since_the_run_before(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        agent = stored(session)
        now = utcnow()

        def finding(title: str, **more: object) -> dict[str, object]:
            return {"severity": "high", "title": title, "detail": "", "cites": [], **more}

        ran(session, agent, finished_at=now - timedelta(days=3), findings=[finding("Telnet open")])
        ran(session, agent, "failed", finished_at=now - timedelta(days=2))
        first = ran(
            session,
            agent,
            finished_at=now - timedelta(days=2),
            findings=[finding("Telnet open."), finding("Odd logins")],
        )
        middle = ran(
            session,
            agent,
            finished_at=now - timedelta(days=1),
            findings=[
                finding(
                    "telnet open",
                    confidence="low",
                    action="Close it.",
                    evidence=["Port 23 answered.", 7],
                    verify="Try it from the guest network.",
                    benign="The camera needs it.",
                )
            ],
        )
        last = ran(
            session,
            agent,
            finished_at=now,
            findings=[finding("Telnet open", confidence="certain"), finding("A new one")],
        )

        body = client.get(f"{BASE}/{agent.id}/runs/{last.id}").json()

        telnet, new = body["findings_list"]
        assert telnet["runs_seen"] == 4
        assert telnet["first_seen_at"].startswith((now - timedelta(days=3)).strftime("%Y-%m-%dT%H"))
        assert telnet["confidence"] == "medium"
        assert new["runs_seen"] == 1
        assert body["changes"]["gone"] == []
        assert body["changes"]["since"].startswith((now - timedelta(days=1)).strftime("%Y-%m-%dT"))
        assert body["by_severity"] == {"high": 2}

        shown = client.get(f"{BASE}/{agent.id}/runs/{middle.id}").json()
        assert shown["changes"]["gone"] == [{"severity": "high", "title": "Odd logins"}]
        assert shown["findings_list"][0]["confidence"] == "low"
        assert shown["findings_list"][0]["action"] == "Close it."
        assert shown["findings_list"][0]["evidence"] == ["Port 23 answered.", "7"]
        assert shown["findings_list"][0]["verify"] == "Try it from the guest network."
        assert shown["findings_list"][0]["benign"] == "The camera needs it."
        assert client.get(f"{BASE}/{agent.id}/runs/{first.id}").json()["changes"] is not None

    def test_the_first_run_has_nothing_before_it_to_differ_from(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        agent = stored(session)
        run = ran(session, agent, finished_at=utcnow())

        assert client.get(f"{BASE}/{agent.id}/runs/{run.id}").json()["changes"] is None

    def test_a_run_of_another_agent_is_not_found(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        mine = stored(session)
        other = stored(session, name="Other")
        run = ran(session, other)

        assert client.get(f"{BASE}/{mine.id}/runs/{run.id}").status_code == 404
        assert client.get(f"{BASE}/{mine.id}/runs/999").status_code == 404

    def test_a_scheduled_run_says_so(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        agent = stored(session)
        run = ran(session, agent, trigger="schedule")

        assert client.get(f"{BASE}/{agent.id}/runs/{run.id}").json()["trigger"] == "schedule"


class TestStoppingOne:
    def cancel(self, client: TestClient, token: str, agent: Agent, run: AgentRun):
        return client.post(f"{BASE}/{agent.id}/runs/{run.id}/cancel", headers=headers(token))

    def test_one_that_is_waiting_never_starts(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        agent = stored(session)
        run = ran(session, agent, "queued")

        response = self.cancel(client, csrf_token, agent, run)

        assert response.json()["status"] == "cancelled"
        assert len(audited(session, Action.AGENT_RUN_CANCELLED)) == 1

    def test_one_that_is_going_is_asked_to_stop(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        agent = stored(session)
        run = ran(session, agent, "running")

        response = self.cancel(client, csrf_token, agent, run)

        assert response.json()["status"] == "running"
        session.expire_all()
        assert session.get_one(AgentRun, run.id).cancel_requested is True

    def test_one_that_is_over_is_as_it_was(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        agent = stored(session)
        run = ran(session, agent, "succeeded")

        response = self.cancel(client, csrf_token, agent, run)

        assert response.json()["status"] == "succeeded"
        assert audited(session, Action.AGENT_RUN_CANCELLED) == []

    def test_one_that_does_not_exist_is_not_found(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        agent = stored(session)

        response = client.post(f"{BASE}/{agent.id}/runs/999/cancel", headers=headers(csrf_token))

        assert response.status_code == 404
