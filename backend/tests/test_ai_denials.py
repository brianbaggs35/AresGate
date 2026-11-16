"""What the owner denied the assistant: kept, so that it is not proposed again, until a month has
passed or the incident has moved on."""

from datetime import timedelta
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import chat, denials
from app.audit import Action
from app.config import Settings
from app.models import AiDeniedProposal, AuditEvent, Incident, User, utcnow
from tests.stubs import Serve
from tests.test_ai_chat import Scripted, look, reply
from tests.test_ai_chat_api import BASE as CHAT
from tests.test_ai_chat_api import begin, provider
from tests.test_ai_triage import incident, ready

BASE = "/api/ai/denials"
NOW = utcnow()


def headers(token: str) -> dict[str, str]:
    return {"X-CSRF-Token": token}


def deny(client: TestClient, token: str, found: list[Incident], **body: Any) -> Any:
    return client.post(
        BASE,
        headers=headers(token),
        json={
            "kind": "status",
            "value": "dismissed",
            "incident_ids": [item.id for item in found],
            **body,
        },
    )


def suggestion(*found: Incident, value: str = "dismissed", kind: str = "status") -> dict[str, Any]:
    first, *others = found
    return {
        "kind": kind,
        "target": f"incident {first.id}",
        "value": value,
        "note": None,
        "also": [f"incident {other.id}" for other in others],
    }


def audited(session: Session, action: Action) -> list[AuditEvent]:
    session.expire_all()
    return list(session.scalars(select(AuditEvent).where(AuditEvent.action == action.value)))


def test_it_is_only_for_someone_signed_in(client: TestClient, account: User) -> None:
    for method, path in (
        ("get", BASE),
        ("post", BASE),
        ("delete", BASE),
        ("delete", f"{BASE}/1"),
    ):
        assert client.request(method, path).status_code == 401, (method, path)


class TestRecording:
    def test_a_denial_is_recorded_for_each_incident_that_exists(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        one, two = incident(session), incident(session, subject="203.0.113.9")
        session.commit()

        response = client.post(
            BASE,
            headers=headers(csrf_token),
            json={"kind": "status", "value": "dismissed", "incident_ids": [one.id, two.id, 9999]},
        )

        assert response.status_code == 201
        assert response.json() == {"recorded": 2}
        listed = client.get(BASE).json()
        assert listed["days"] == denials.DAYS
        assert {item["incident_id"] for item in listed["items"]} == {one.id, two.id}
        first = listed["items"][0]
        assert (first["kind"], first["value"]) == ("status", "dismissed")
        assert first["title"]
        assert first["expires_at"] > first["denied_at"]
        [event] = audited(session, Action.AI_PROPOSAL_DENIED)
        assert event.detail == {"kind": "status", "value": "dismissed", "incidents": 2}

    def test_a_denial_of_nothing_that_exists_records_nothing(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        response = client.post(
            BASE,
            headers=headers(csrf_token),
            json={"kind": "verdict", "value": "threat", "incident_ids": [9999]},
        )

        assert response.json() == {"recorded": 0}
        assert client.get(BASE).json()["items"] == []

    def test_denying_again_makes_it_stand_from_now(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        found = incident(session)
        session.commit()
        deny(client, csrf_token, [found])
        row = session.scalars(select(AiDeniedProposal)).one()
        row.denied_at = NOW - timedelta(days=20)
        session.commit()

        deny(client, csrf_token, [found])

        session.expire_all()
        assert session.scalars(select(AiDeniedProposal)).one().denied_at > NOW - timedelta(days=1)

    def test_what_makes_no_sense_is_refused(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        found = incident(session)
        session.commit()

        for body in (
            {"kind": "status", "value": "threat", "incident_ids": [found.id]},
            {"kind": "verdict", "value": "dismissed", "incident_ids": [found.id]},
            {"kind": "status", "value": "dismissed", "incident_ids": []},
            {"kind": "status", "value": "dismissed", "incident_ids": [0]},
            {"kind": "status", "value": "dismissed", "incident_ids": [found.id] * 21},
            {"kind": "open", "value": "dismissed", "incident_ids": [found.id]},
            {"kind": "status", "value": "dismissed", "incident_ids": [found.id], "more": 1},
        ):
            response = client.post(BASE, headers=headers(csrf_token), json=body)
            assert response.status_code == 422, body

    def test_it_needs_the_token_that_says_the_page_asked(
        self, client: TestClient, csrf_token: str
    ) -> None:
        assert client.post(BASE, json={}).status_code == 403
        assert client.delete(BASE).status_code == 403


class TestWhatStands:
    def test_a_denial_stands_for_a_month(self, session: Session) -> None:
        found = incident(session)
        denials.record(session, "status", "dismissed", [found.id], NOW - timedelta(days=29))
        session.commit()

        assert denials.standing(session, NOW) == {("status", "dismissed", found.id)}
        assert denials.standing(session, NOW + timedelta(days=2)) == frozenset()

    def test_it_stops_standing_when_the_incident_has_moved_on(self, session: Session) -> None:
        found = incident(session)
        denials.record(session, "status", "dismissed", [found.id], NOW)
        session.commit()
        found.status = "investigating"
        session.commit()
        assert denials.standing(session, NOW) == frozenset()

        found.status = "open"
        found.verdict = "threat"
        session.commit()
        assert denials.standing(session, NOW) == frozenset()

        found.verdict = None
        session.commit()
        assert denials.standing(session, NOW) == {("status", "dismissed", found.id)}

    def test_a_proposal_stands_denied_only_if_every_incident_in_it_does(
        self, session: Session
    ) -> None:
        one, two = incident(session), incident(session, subject="203.0.113.9")
        denials.record(session, "status", "dismissed", [one.id], NOW)
        session.commit()
        denied = denials.standing(session, NOW)

        def proposal(*ids: Incident, kind: str = "status", value: str | None = "dismissed") -> Any:
            first, *rest = ids
            return {
                "kind": kind,
                "target_key": str(first.id),
                "also": [str(other.id) for other in rest],
                "value": value,
            }

        assert denials.is_denied(proposal(one), denied)
        assert not denials.is_denied(proposal(one, two), denied)
        assert not denials.is_denied(proposal(two), denied)
        assert not denials.is_denied(proposal(one, value="resolved"), denied)
        assert not denials.is_denied(proposal(one, kind="verdict"), denied)
        assert not denials.is_denied(proposal(one, kind="open"), denied)
        assert not denials.is_denied(proposal(one, value=None), denied)
        assert not denials.is_denied({"kind": "status", "value": "dismissed"}, denied)

    def test_a_suggestion_to_open_a_page_is_never_dropped(self, session: Session) -> None:
        opening = [{"kind": "open", "target_key": "3", "also": [], "value": None}]

        assert denials.without_denied(session, opening, NOW) == opening


class TestForgetting:
    def test_one_is_forgotten_and_the_owner_can_see_it_in_the_log(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        found = incident(session)
        session.commit()
        deny(client, csrf_token, [found])
        [item] = client.get(BASE).json()["items"]

        response = client.delete(f"{BASE}/{item['id']}", headers=headers(csrf_token))

        assert response.status_code == 204
        assert client.get(BASE).json()["items"] == []
        [event] = audited(session, Action.AI_DENIALS_FORGOTTEN)
        assert event.detail == {"count": 1}

    def test_there_is_no_forgetting_what_is_not_there(
        self, client: TestClient, csrf_token: str
    ) -> None:
        response = client.delete(f"{BASE}/7", headers=headers(csrf_token))

        assert response.status_code == 404

    def test_all_can_be_forgotten_and_nothing_is_logged_when_there_was_nothing(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        one, two = incident(session), incident(session, subject="203.0.113.9")
        session.commit()
        deny(client, csrf_token, [one, two])

        first = client.delete(BASE, headers=headers(csrf_token))
        second = client.delete(BASE, headers=headers(csrf_token))

        assert first.json() == {"forgotten": 2}
        assert second.json() == {"forgotten": 0}
        [event] = audited(session, Action.AI_DENIALS_FORGOTTEN)
        assert event.detail == {"count": 2}

    def test_an_incident_that_is_deleted_takes_its_denials_with_it(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        found = incident(session)
        session.commit()
        deny(client, csrf_token, [found])

        session.delete(found)
        session.commit()

        assert session.scalars(select(AiDeniedProposal)).all() == []


class TestTheAssistant:
    def test_it_is_told_what_was_denied_and_the_proposal_is_not_made_again(
        self,
        client: TestClient,
        csrf_token: str,
        app: FastAPI,
        serve: Serve,
        session: Session,
        settings: Settings,
    ) -> None:
        ready(session, settings)
        one, two = incident(session), incident(session, subject="203.0.113.9")
        session.commit()
        deny(client, csrf_token, [one])
        scripted = Scripted(
            reply(lookups=[look("open_incidents")], answer=""),
            reply(
                answer="Dismiss them.",
                actions=[suggestion(one), suggestion(two), suggestion(one, value="resolved")],
            ),
        )
        provider(app, serve, scripted)

        body = begin(client, csrf_token, "What now?").json()

        assert f"status dismissed for incident {one.id}" in scripted.prompts[0]
        kept = body["messages"][1]["actions"]
        assert [(item["value"], item["target_key"]) for item in kept] == [
            ("dismissed", str(two.id)),
            ("resolved", str(one.id)),
        ]

    def test_it_is_told_nothing_when_nothing_was_denied(
        self,
        client: TestClient,
        csrf_token: str,
        app: FastAPI,
        serve: Serve,
        session: Session,
        settings: Settings,
    ) -> None:
        ready(session, settings)
        scripted = Scripted(reply(answer="Quiet."))
        provider(app, serve, scripted)

        begin(client, csrf_token, "Anything?")

        assert "denied these suggestions" not in scripted.prompts[0]

    def test_a_proposal_already_in_a_conversation_shows_as_denied_once_it_is(
        self,
        client: TestClient,
        csrf_token: str,
        app: FastAPI,
        serve: Serve,
        session: Session,
        settings: Settings,
    ) -> None:
        ready(session, settings)
        found = incident(session)
        session.commit()
        provider(
            app,
            serve,
            Scripted(
                reply(lookups=[look("open_incidents")], answer=""),
                reply(answer="Dismiss it.", actions=[suggestion(found)]),
            ),
        )
        started = begin(client, csrf_token, "What now?").json()
        assert started["messages"][1]["actions"][0]["denied"] is False

        deny(client, csrf_token, [found])

        shown = client.get(f"{CHAT}/{started['id']}").json()
        assert shown["messages"][1]["actions"][0]["denied"] is True

    def test_the_model_is_told_the_incidents_of_each_kind_of_denial_in_order(
        self, session: Session
    ) -> None:
        many = [
            incident(session, subject=f"203.0.113.{n}") for n in range(1, chat.MAX_INCIDENTS + 3)
        ]
        denials.record(session, "status", "dismissed", [item.id for item in many], NOW)
        denials.record(session, "verdict", "not_suspicious", [many[0].id], NOW)
        session.commit()

        told = denials.told(session, NOW)

        assert told is not None
        assert told.startswith("The owner has denied these suggestions lately")
        ids = ", ".join(str(item.id) for item in many[: denials.MAX_TOLD])
        assert f"status dismissed for incident {ids};" in told
        assert f"verdict not suspicious for incident {many[0].id}." in told
        assert str(many[-1].id) not in told
