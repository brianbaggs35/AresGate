import json
from datetime import timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.alerts import destinations
from app.audit import Action, Outcome
from app.config import Settings
from app.integrations import netguard
from app.models import (
    AlertDestination,
    ApiCall,
    AuditEvent,
    Incident,
    StoredCredential,
    User,
    utcnow,
)
from app.security import credential_store
from app.security.credential_store import Kind
from e2e.stand_ins import discord as discord_stand_in
from tests.helpers import OTHER_ORIGIN
from tests.stubs import Answer, Serve, StubServer

BASE = "/api/alerts/destinations"
SAMPLE = "/api/alerts/sample"
ID = "1234567890123456789"
TOKEN = "Zk3-_abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-_x"
ADDRESS = f"https://discord.com/api/webhooks/{ID}/{TOKEN}"
OTHER_ID = "9876543210987654321"
OTHER_TOKEN = "Qq9-_zyxwvutsrqponmlkjihgfedcba9876543210ZYXWVUTSRQPONMLKJIHGFEDCBA-_y"
OTHER_ADDRESS = f"https://discord.com/api/webhooks/{OTHER_ID}/{OTHER_TOKEN}"


def headers(token: str) -> dict[str, str]:
    return {"X-CSRF-Token": token}


def add(client: TestClient, token: str, **body: Any) -> Any:
    return client.post(
        BASE, json={"name": "Security", "url": ADDRESS, **body}, headers=headers(token)
    )


def audited(session: Session, action: Action) -> list[AuditEvent]:
    session.expire_all()
    return list(
        session.scalars(
            select(AuditEvent).where(AuditEvent.action == action.value).order_by(AuditEvent.id)
        )
    )


def discord(serve: Serve, app: FastAPI, known: str = f"{ID}/{TOKEN}") -> StubServer:
    """Discord, on this machine, and alerts sent there."""
    server = serve(discord_stand_in(known))
    app.state.alert_origin = server.url
    return server


def test_it_is_only_for_someone_signed_in(client: TestClient, account: User) -> None:
    for method, path in (
        ("get", BASE),
        ("post", BASE),
        ("patch", f"{BASE}/1"),
        ("delete", f"{BASE}/1"),
        ("post", f"{BASE}/1/test"),
        ("post", f"{BASE}/1/sample"),
        ("get", SAMPLE),
        ("put", f"{BASE}/1/rules"),
        ("post", f"{BASE}/1/preview"),
    ):
        assert client.request(method, path).status_code == 401, (method, path)


def test_a_change_from_another_website_is_refused(client: TestClient, csrf_token: str) -> None:
    response = client.post(
        BASE,
        json={"name": "x", "url": ADDRESS},
        headers={**headers(csrf_token), "Origin": OTHER_ORIGIN},
    )

    assert response.status_code == 403


def test_a_change_without_the_security_token_is_refused(
    client: TestClient, csrf_token: str
) -> None:
    response = client.post(BASE, json={"name": "x", "url": ADDRESS})
    assert response.status_code == 403


class TestAddingOne:
    def test_an_install_with_none_has_an_empty_list(
        self, client: TestClient, csrf_token: str
    ) -> None:
        body = client.get(BASE).json()

        assert body["items"] == []
        assert body["max_destinations"] == 10
        assert body["hosts"] == ["discord.com", "discordapp.com"]
        assert set(body["choices"]) == {"sources", "activities"}

    def test_it_is_kept_and_shown_without_its_address(
        self, client: TestClient, csrf_token: str
    ) -> None:
        response = add(client, csrf_token)

        assert response.status_code == 201
        body = response.json()
        assert body | {"id": 0, "created_at": "", "updated_at": ""} == {
            "id": 0,
            "kind": "discord",
            "name": "Security",
            "enabled": True,
            "host": "discord.com",
            "hint": "…6789",
            "status": "untested",
            "last_attempt_at": None,
            "last_success_at": None,
            "last_error": None,
            "rules": NEW_RULES,
            "created_at": "",
            "updated_at": "",
        }
        assert client.get(BASE).json()["items"] == [body]
        everything = response.text + client.get(BASE).text
        assert TOKEN not in everything
        assert ADDRESS not in everything

    def test_the_address_is_sealed_and_can_be_opened_to_send(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        body = add(client, csrf_token).json()

        sealed = session.scalars(select(StoredCredential)).one()
        assert (sealed.kind, sealed.name, sealed.field) == (
            "destination",
            f"destination-{body['id']}",
            "webhook_url",
        )
        assert TOKEN not in sealed.value_sealed
        assert (
            credential_store.reveal(
                session, settings, Kind.DESTINATION, f"destination-{body['id']}", "webhook_url"
            )
            == ADDRESS
        )

    def test_the_address_is_kept_in_the_form_it_was_checked_in(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        body = add(client, csrf_token, url=f"  {ADDRESS}/  ").json()

        assert (
            credential_store.reveal(
                session, settings, Kind.DESTINATION, f"destination-{body['id']}", "webhook_url"
            )
            == ADDRESS
        )

    def test_a_record_is_made_without_the_address(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        add(client, csrf_token)

        [event] = audited(session, Action.ALERT_DESTINATION_ADDED)
        assert event.outcome == Outcome.SUCCESS.value
        assert event.detail == {"destination": "Security", "kind": "discord"}
        assert TOKEN not in repr(event.detail)
        assert TOKEN not in str(event.__dict__)

    def test_the_name_is_trimmed(self, client: TestClient, csrf_token: str) -> None:
        assert add(client, csrf_token, name="  Security  ").json()["name"] == "Security"

    def test_an_address_that_is_not_discords_is_refused_in_words_for_that_field(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        response = add(client, csrf_token, url="https://example.com/api/webhooks/1/2")

        assert response.status_code == 422
        [problem] = response.json()["detail"]
        assert problem["loc"] == ["body", "url"]
        assert "isn't a Discord address" in problem["msg"]
        assert session.scalars(select(AlertDestination)).all() == []
        assert session.scalars(select(StoredCredential)).all() == []

    def test_a_refusal_does_not_repeat_the_address(
        self, client: TestClient, csrf_token: str
    ) -> None:
        response = add(client, csrf_token, url=f"http://discord.com/api/webhooks/{ID}/{TOKEN}")

        assert response.status_code == 422
        assert TOKEN not in response.text

    def test_a_name_is_taken_whatever_its_letter_case(
        self, client: TestClient, csrf_token: str
    ) -> None:
        add(client, csrf_token)

        response = add(client, csrf_token, name="SECURITY", url=OTHER_ADDRESS)

        assert response.status_code == 422
        [problem] = response.json()["detail"]
        assert problem["loc"] == ["body", "name"]
        assert problem["msg"] == "There's already a destination called SECURITY."

    def test_a_name_and_an_address_are_needed(self, client: TestClient, csrf_token: str) -> None:
        assert add(client, csrf_token, name="   ").status_code == 422
        assert add(client, csrf_token, url="").status_code == 422
        assert add(client, csrf_token, url="x" * 401).status_code == 422
        assert add(client, csrf_token, name="n" * 61).status_code == 422
        assert add(client, csrf_token, extra=1).status_code == 422

    def test_only_so_many_can_be_kept(self, client: TestClient, csrf_token: str) -> None:
        for number in range(destinations.MAX_DESTINATIONS):
            assert add(client, csrf_token, name=f"Channel {number}").status_code == 201

        response = add(client, csrf_token, name="One more")

        assert response.status_code == 409
        assert response.json()["detail"] == (
            "You can keep 10 destinations. Remove one to add another."
        )


class TestChangingOne:
    def test_it_can_be_renamed_and_turned_off(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        body = add(client, csrf_token).json()

        response = client.patch(
            f"{BASE}/{body['id']}",
            json={"name": "Phone", "enabled": False},
            headers=headers(csrf_token),
        )

        assert response.status_code == 200
        assert (response.json()["name"], response.json()["enabled"]) == ("Phone", False)
        [event] = audited(session, Action.ALERT_DESTINATION_CHANGED)
        assert event.detail == {"destination": "Phone", "changed": "name, turned off"}

    def test_turning_it_back_on_is_recorded(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        body = add(client, csrf_token).json()
        change = {"enabled": False}
        client.patch(f"{BASE}/{body['id']}", json=change, headers=headers(csrf_token))

        client.patch(f"{BASE}/{body['id']}", json={"enabled": True}, headers=headers(csrf_token))

        details = [event.detail for event in audited(session, Action.ALERT_DESTINATION_CHANGED)]
        assert [detail["changed"] for detail in details if detail] == ["turned off", "turned on"]

    def test_saying_what_is_already_so_changes_nothing(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        body = add(client, csrf_token).json()

        response = client.patch(
            f"{BASE}/{body['id']}",
            json={"name": "Security", "enabled": True},
            headers=headers(csrf_token),
        )

        assert response.status_code == 200
        assert audited(session, Action.ALERT_DESTINATION_CHANGED) == []

    def test_a_new_address_replaces_the_old_and_forgets_how_it_went(
        self,
        client: TestClient,
        csrf_token: str,
        session: Session,
        settings: Settings,
        serve: Serve,
        app: FastAPI,
    ) -> None:
        discord(serve, app)
        body = add(client, csrf_token).json()
        client.post(f"{BASE}/{body['id']}/test", headers=headers(csrf_token))

        response = client.patch(
            f"{BASE}/{body['id']}", json={"url": OTHER_ADDRESS}, headers=headers(csrf_token)
        )

        changed = response.json()
        assert (changed["hint"], changed["status"], changed["last_success_at"]) == (
            "…4321",
            "untested",
            None,
        )
        assert (
            credential_store.reveal(
                session, settings, Kind.DESTINATION, f"destination-{body['id']}", "webhook_url"
            )
            == OTHER_ADDRESS
        )
        assert TOKEN not in response.text
        assert OTHER_TOKEN not in response.text
        [event] = audited(session, Action.ALERT_DESTINATION_CHANGED)
        assert event.detail == {"destination": "Security", "changed": "address"}

    def test_a_new_address_that_is_refused_changes_nothing(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        body = add(client, csrf_token).json()

        response = client.patch(
            f"{BASE}/{body['id']}",
            json={"name": "Renamed", "url": "https://example.com/x"},
            headers=headers(csrf_token),
        )

        assert response.status_code == 422
        assert response.json()["detail"][0]["loc"] == ["body", "url"]
        session.expire_all()
        assert session.scalars(select(AlertDestination)).one().hint == "…6789"
        assert audited(session, Action.ALERT_DESTINATION_CHANGED) == []

    def test_a_name_another_has_is_refused(self, client: TestClient, csrf_token: str) -> None:
        add(client, csrf_token)
        other = add(client, csrf_token, name="Phone", url=OTHER_ADDRESS).json()

        response = client.patch(
            f"{BASE}/{other['id']}", json={"name": "security"}, headers=headers(csrf_token)
        )

        assert response.status_code == 422
        assert response.json()["detail"][0]["loc"] == ["body", "name"]

    def test_there_is_no_changing_what_is_not_there(
        self, client: TestClient, csrf_token: str
    ) -> None:
        response = client.patch(f"{BASE}/99", json={"enabled": False}, headers=headers(csrf_token))

        assert response.status_code == 404
        assert response.json()["detail"] == "There's no such destination."

    def test_a_destination_whose_address_was_deleted_says_so(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        body = add(client, csrf_token).json()
        client.delete(
            f"/api/credentials/destination/destination-{body['id']}/webhook_url",
            headers=headers(csrf_token),
        )

        [listed] = client.get(BASE).json()["items"]

        assert listed["status"] == "not_connected"


class TestRemovingOne:
    def test_it_goes_with_its_address(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        body = add(client, csrf_token).json()

        response = client.delete(f"{BASE}/{body['id']}", headers=headers(csrf_token))

        assert response.status_code == 204
        assert client.get(BASE).json()["items"] == []
        assert session.scalar(select(func.count()).select_from(StoredCredential)) == 0
        [event] = audited(session, Action.ALERT_DESTINATION_REMOVED)
        assert event.detail == {"destination": "Security"}

    def test_another_keeps_its_address(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        first = add(client, csrf_token).json()
        add(client, csrf_token, name="Phone", url=OTHER_ADDRESS)

        client.delete(f"{BASE}/{first['id']}", headers=headers(csrf_token))

        [kept] = session.scalars(select(StoredCredential))
        assert kept.name != f"destination-{first['id']}"

    def test_there_is_no_removing_what_is_not_there(
        self, client: TestClient, csrf_token: str
    ) -> None:
        response = client.delete(f"{BASE}/99", headers=headers(csrf_token))

        assert response.status_code == 404


class TestTheTestMessage:
    def test_it_is_sent_and_the_destination_is_working(
        self, client: TestClient, csrf_token: str, serve: Serve, app: FastAPI, session: Session
    ) -> None:
        server = discord(serve, app)
        body = add(client, csrf_token).json()

        response = client.post(f"{BASE}/{body['id']}/test", headers=headers(csrf_token))

        assert response.status_code == 200
        answer = response.json()
        assert answer["ok"] is True
        assert answer["message"] == "The test message was sent. Look for it in the channel."
        assert answer["destination"]["status"] == "connected"
        assert answer["destination"]["last_attempt_at"] is not None
        assert answer["destination"]["last_success_at"] is not None
        assert answer["destination"]["last_error"] is None
        [seen] = server.seen
        assert seen.path == f"/api/webhooks/{ID}/{TOKEN}"
        [event] = audited(session, Action.ALERT_DESTINATION_TESTED)
        assert (event.outcome, event.detail) == ("success", {"destination": "Security"})

    def test_the_request_is_logged_without_the_address(
        self, client: TestClient, csrf_token: str, serve: Serve, app: FastAPI, session: Session
    ) -> None:
        discord(serve, app)
        body = add(client, csrf_token).json()

        client.post(f"{BASE}/{body['id']}/test", headers=headers(csrf_token))

        call = session.scalars(select(ApiCall)).one()
        assert (call.integration, call.connection, call.method, call.status_code) == (
            "discord",
            f"destination-{body['id']}",
            "POST",
            204,
        )
        assert call.path == "/api/webhooks/…"
        assert TOKEN not in repr(call.__dict__)

    def test_a_webhook_discord_does_not_know_is_a_problem_in_words(
        self, client: TestClient, csrf_token: str, serve: Serve, app: FastAPI, session: Session
    ) -> None:
        discord(serve, app, known=f"{OTHER_ID}/{OTHER_TOKEN}")
        body = add(client, csrf_token).json()

        response = client.post(f"{BASE}/{body['id']}/test", headers=headers(csrf_token))

        assert response.status_code == 200
        answer = response.json()
        assert answer["ok"] is False
        assert answer["message"].startswith("Discord doesn't accept this webhook (HTTP 404).")
        assert answer["destination"]["status"] == "problem"
        assert answer["destination"]["last_error"] == answer["message"]
        assert answer["destination"]["last_success_at"] is None
        assert TOKEN not in response.text
        [event] = audited(session, Action.ALERT_DESTINATION_TESTED)
        assert event.outcome == "failure"

    def test_a_working_one_that_then_fails_keeps_when_it_last_worked(
        self, client: TestClient, csrf_token: str, serve: Serve, app: FastAPI
    ) -> None:
        discord(serve, app)
        body = add(client, csrf_token).json()
        worked = client.post(f"{BASE}/{body['id']}/test", headers=headers(csrf_token)).json()
        discord(serve, app, known="1/other")

        failed = client.post(f"{BASE}/{body['id']}/test", headers=headers(csrf_token)).json()

        assert failed["ok"] is False
        assert failed["destination"]["last_success_at"] == worked["destination"]["last_success_at"]
        assert failed["destination"]["status"] == "problem"

    def test_nobody_answering_is_a_problem_in_words(
        self, client: TestClient, csrf_token: str, serve: Serve, app: FastAPI
    ) -> None:
        server = serve(lambda seen: Answer(drop=True))
        app.state.alert_origin = server.url
        body = add(client, csrf_token).json()

        answer = client.post(f"{BASE}/{body['id']}/test", headers=headers(csrf_token)).json()

        assert answer["ok"] is False
        assert answer["message"]
        assert TOKEN not in answer["message"]

    def test_the_network_guard_keeps_it_off_the_home_network(
        self, client: TestClient, csrf_token: str, serve: Serve, app: FastAPI
    ) -> None:
        server = discord(serve, app)
        app.state.alert_policy = netguard.PUBLIC_INTERNET
        body = add(client, csrf_token).json()

        answer = client.post(f"{BASE}/{body['id']}/test", headers=headers(csrf_token)).json()

        assert answer["ok"] is False
        assert "won't connect" in answer["message"]
        assert server.seen == []

    def test_it_is_sent_even_when_the_destination_is_turned_off(
        self, client: TestClient, csrf_token: str, serve: Serve, app: FastAPI
    ) -> None:
        server = discord(serve, app)
        body = add(client, csrf_token).json()
        client.patch(f"{BASE}/{body['id']}", json={"enabled": False}, headers=headers(csrf_token))

        answer = client.post(f"{BASE}/{body['id']}/test", headers=headers(csrf_token)).json()

        assert answer["ok"] is True
        assert answer["destination"]["enabled"] is False
        assert len(server.seen) == 1

    def test_a_missing_address_is_a_problem_in_words(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        body = add(client, csrf_token).json()
        client.delete(
            f"/api/credentials/destination/destination-{body['id']}/webhook_url",
            headers=headers(csrf_token),
        )

        answer = client.post(f"{BASE}/{body['id']}/test", headers=headers(csrf_token)).json()

        assert answer["ok"] is False
        assert answer["message"] == (
            "The webhook address is missing or can't be opened. Enter it again."
        )
        assert answer["destination"]["status"] == "not_connected"

    def test_an_address_that_is_no_longer_discords_is_not_sent_to(
        self,
        client: TestClient,
        csrf_token: str,
        session: Session,
        settings: Settings,
        serve: Serve,
        app: FastAPI,
    ) -> None:
        server = discord(serve, app)
        body = add(client, csrf_token).json()
        # The credentials route takes any text, so the address is checked again to send.
        credential_store.store(
            session,
            settings,
            Kind.DESTINATION,
            f"destination-{body['id']}",
            "webhook_url",
            "https://evil.example/api/webhooks/1/2",
            utcnow(),
        )
        session.commit()

        answer = client.post(f"{BASE}/{body['id']}/test", headers=headers(csrf_token)).json()

        assert answer["ok"] is False
        assert answer["message"] == (
            "The saved webhook address isn't a Discord address any more. Enter it again."
        )
        assert server.seen == []

    def test_an_address_that_cannot_be_opened_is_a_problem_in_words(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        body = add(client, csrf_token).json()
        sealed = session.scalars(select(StoredCredential)).one()
        sealed.value_sealed = "not sealed by us"
        session.commit()

        answer = client.post(f"{BASE}/{body['id']}/test", headers=headers(csrf_token)).json()

        assert answer["ok"] is False
        assert "can't be opened" in answer["message"]

    def test_there_is_no_testing_what_is_not_there(
        self, client: TestClient, csrf_token: str
    ) -> None:
        response = client.post(f"{BASE}/99/test", headers=headers(csrf_token))

        assert response.status_code == 404


# What a new destination is told about, and the page's whole set of rules with changes.
NEW_RULES: dict[str, Any] = {
    "mode": "threats",
    "min_severity": 2,
    "min_confidence": 65,
    "sources": [],
    "activities": [],
    "quiet_hours": False,
    "quiet_from": 1320,
    "quiet_until": 420,
    "quiet_critical": True,
    "time_zone": "UTC",
    "max_per_hour": 6,
    "detail": "standard",
    "again_when_worse": True,
}


def rules(**changes: Any) -> dict[str, Any]:
    return {**NEW_RULES, **changes}


def incident(session: Session, **changes: Any) -> Incident:
    now = utcnow()
    fields: dict[str, Any] = {
        "subject": "203.0.113.5",
        "title": "Scan from 203.0.113.5",
        "severity": 3,
        "confidence": 70,
        "status": "open",
        "first_seen_at": now - timedelta(hours=2),
        "last_seen_at": now - timedelta(hours=1),
        "signal_count": 3,
        "sources": ["opnsense", "wazuh"],
        "addresses": [],
        "ports": [],
        "activities": ["scan"],
        "top_source": "wazuh",
        "top_summary": "An alert",
        "banned": False,
        "verdict": None,
        "waves": 1,
        **changes,
    }
    found = Incident(**fields)
    session.add(found)
    session.commit()
    return found


class TestTheSampleAlert:
    def test_a_sample_is_sent_in_the_form_the_destinations_rules_give_it(
        self, client: TestClient, csrf_token: str, serve: Serve, app: FastAPI, session: Session
    ) -> None:
        server = discord(serve, app)
        body = add(client, csrf_token).json()

        response = client.post(f"{BASE}/{body['id']}/sample", headers=headers(csrf_token))

        assert response.status_code == 200
        answer = response.json()
        assert answer["ok"] is True
        assert answer["message"] == "The sample alert was sent. Look for it in the channel."
        assert answer["destination"]["status"] == "connected"
        [seen] = server.seen
        [embed] = json.loads(seen.body)["embeds"]
        assert embed["title"].startswith("Attack in progress: ")
        assert embed["footer"] == {"text": "AresGate · sample alert"}
        [event] = audited(session, Action.ALERT_DESTINATION_TESTED)
        assert event.outcome == "success"

    def test_a_destination_with_floors_gets_the_plain_message(
        self, client: TestClient, csrf_token: str, serve: Serve, app: FastAPI
    ) -> None:
        server = discord(serve, app)
        body = add(client, csrf_token).json()
        client.put(
            f"{BASE}/{body['id']}/rules",
            json=rules(mode="custom", detail="brief"),
            headers=headers(csrf_token),
        )

        client.post(f"{BASE}/{body['id']}/sample", headers=headers(csrf_token))

        [embed] = json.loads(server.seen[0].body)["embeds"]
        assert embed["title"] == "High-severity scanning"
        assert "fields" not in embed

    def test_a_webhook_that_is_not_taken_is_a_problem_in_words(
        self, client: TestClient, csrf_token: str, serve: Serve, app: FastAPI
    ) -> None:
        discord(serve, app, known=f"{OTHER_ID}/{OTHER_TOKEN}")
        body = add(client, csrf_token).json()

        answer = client.post(f"{BASE}/{body['id']}/sample", headers=headers(csrf_token)).json()

        assert answer["ok"] is False
        assert answer["message"].startswith("Discord doesn't accept this webhook (HTTP 404).")

    def test_there_is_no_sample_for_a_destination_that_is_not_there(
        self, client: TestClient, csrf_token: str
    ) -> None:
        response = client.post(f"{BASE}/99/sample", headers=headers(csrf_token))

        assert response.status_code == 404

    def test_the_page_can_ask_what_a_message_looks_like(
        self, client: TestClient, csrf_token: str
    ) -> None:
        threats = client.get(SAMPLE).json()["payload"]
        brief = client.get(SAMPLE, params={"mode": "custom", "detail": "brief"}).json()
        worse = client.get(SAMPLE, params={"reason": "worse"}).json()

        assert threats["allowed_mentions"] == {"parse": []}
        assert threats["embeds"][0]["title"].startswith("Attack in progress: ")
        assert threats["embeds"][0]["url"].endswith("/incidents")
        assert brief["payload"]["embeds"][0]["title"] == "High-severity scanning"
        assert worse["payload"]["embeds"][0]["title"].startswith("Escalated: ")

    def test_a_mode_or_a_level_it_does_not_know_is_refused(
        self, client: TestClient, csrf_token: str
    ) -> None:
        for query in ({"mode": "all"}, {"detail": "loud"}, {"reason": "limit"}):
            assert client.get(SAMPLE, params=query).status_code == 422, query


class TestTheRules:
    def test_a_new_destination_is_told_only_of_what_is_serious_and_sure(
        self, client: TestClient, csrf_token: str
    ) -> None:
        body = add(client, csrf_token).json()

        assert body["rules"] == NEW_RULES
        assert client.get(BASE).json()["items"][0]["rules"] == NEW_RULES

    def test_the_page_is_told_what_the_rules_can_name(
        self, client: TestClient, csrf_token: str
    ) -> None:
        choices = client.get(BASE).json()["choices"]

        assert {"key": "wazuh", "name": "Wazuh"} in choices["sources"]
        assert {"key": "opnsense", "name": "OPNsense"} in choices["sources"]
        assert choices["activities"] == [
            {"key": "scan", "name": "scanning"},
            {"key": "brute_force", "name": "brute force"},
        ]

    def test_they_are_replaced_whole_and_kept(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        destination = add(client, csrf_token).json()
        wanted = rules(
            min_severity=3,
            min_confidence=35,
            sources=["wazuh", "crowdsec"],
            activities=["brute_force", "scan"],
            quiet_hours=True,
            quiet_from=23 * 60,
            quiet_until=6 * 60,
            quiet_critical=False,
            time_zone="Europe/Berlin",
            max_per_hour=2,
            detail="brief",
            again_when_worse=False,
        )

        response = client.put(
            f"{BASE}/{destination['id']}/rules", json=wanted, headers=headers(csrf_token)
        )

        assert response.status_code == 200
        # Sources and kinds are kept in order, once each.
        assert response.json()["rules"] == {
            **wanted,
            "sources": ["crowdsec", "wazuh"],
            "activities": ["brute_force", "scan"],
        }
        assert client.get(BASE).json()["items"][0]["rules"] == response.json()["rules"]
        row = session.get(AlertDestination, destination["id"])
        assert row is not None
        assert (row.min_severity, row.detail, row.quiet_hours) == (3, "brief", True)

    def test_a_source_listed_twice_is_kept_once(self, client: TestClient, csrf_token: str) -> None:
        destination = add(client, csrf_token).json()

        response = client.put(
            f"{BASE}/{destination['id']}/rules",
            json=rules(sources=["wazuh", "wazuh"]),
            headers=headers(csrf_token),
        )

        assert response.json()["rules"]["sources"] == ["wazuh"]

    def test_the_change_is_recorded_without_saying_what_was_chosen(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        destination = add(client, csrf_token).json()

        client.put(f"{BASE}/{destination['id']}/rules", json=rules(), headers=headers(csrf_token))

        [event] = audited(session, Action.ALERT_RULES_CHANGED)
        assert event.outcome == Outcome.SUCCESS.value
        assert event.detail == {"destination": "Security"}

    @pytest.mark.parametrize(
        ("changes", "field"),
        [
            ({"sources": ["nothing-of-the-kind"]}, "sources"),
            ({"time_zone": "Nowhere/Land"}, "time_zone"),
            ({"quiet_hours": True, "quiet_from": 600, "quiet_until": 600}, "quiet_until"),
        ],
    )
    def test_rules_that_make_no_sense_are_refused_on_the_field(
        self, client: TestClient, csrf_token: str, changes: dict[str, Any], field: str
    ) -> None:
        destination = add(client, csrf_token).json()

        response = client.put(
            f"{BASE}/{destination['id']}/rules", json=rules(**changes), headers=headers(csrf_token)
        )

        assert response.status_code == 422
        assert response.json()["detail"][0]["loc"] == ["body", field]
        assert client.get(BASE).json()["items"][0]["rules"] == NEW_RULES

    def test_equal_quiet_times_are_fine_while_quiet_hours_are_off(
        self, client: TestClient, csrf_token: str
    ) -> None:
        destination = add(client, csrf_token).json()

        response = client.put(
            f"{BASE}/{destination['id']}/rules",
            json=rules(quiet_from=600, quiet_until=600),
            headers=headers(csrf_token),
        )

        assert response.status_code == 200

    @pytest.mark.parametrize(
        "changes",
        [
            {"min_severity": 0},
            {"min_severity": 5},
            {"min_confidence": 101},
            {"max_per_hour": 0},
            {"max_per_hour": 61},
            {"quiet_from": 1440},
            {"quiet_until": -1},
            {"detail": "everything"},
            {"activities": ["scan", "scan", "scan"]},
            {"activities": ["dancing"]},
            {"time_zone": ""},
        ],
    )
    def test_numbers_and_words_outside_what_is_allowed_are_refused(
        self, client: TestClient, csrf_token: str, changes: dict[str, Any]
    ) -> None:
        destination = add(client, csrf_token).json()

        response = client.put(
            f"{BASE}/{destination['id']}/rules", json=rules(**changes), headers=headers(csrf_token)
        )

        assert response.status_code == 422

    def test_something_left_out_or_added_is_refused(
        self, client: TestClient, csrf_token: str
    ) -> None:
        destination = add(client, csrf_token).json()
        missing: dict[str, Any] = {k: v for k, v in NEW_RULES.items() if k != "detail"}
        bodies: list[dict[str, Any]] = [missing, {**NEW_RULES, "address": "x"}]

        for body in bodies:
            response = client.put(
                f"{BASE}/{destination['id']}/rules", json=body, headers=headers(csrf_token)
            )
            assert response.status_code == 422

    def test_there_is_no_rules_for_a_destination_that_is_not_there(
        self, client: TestClient, csrf_token: str
    ) -> None:
        response = client.put(f"{BASE}/99/rules", json=rules(), headers=headers(csrf_token))

        assert response.status_code == 404


class TestTheMode:
    def test_a_new_destination_is_told_only_of_threats(
        self, client: TestClient, csrf_token: str
    ) -> None:
        body = add(client, csrf_token).json()

        assert body["rules"]["mode"] == "threats"

    def test_the_owner_can_choose_the_floors_instead_and_back(
        self, client: TestClient, csrf_token: str
    ) -> None:
        body = add(client, csrf_token).json()

        custom = client.put(
            f"{BASE}/{body['id']}/rules",
            json=rules(mode="custom", min_severity=3),
            headers=headers(csrf_token),
        ).json()
        back = client.put(
            f"{BASE}/{body['id']}/rules", json=rules(), headers=headers(csrf_token)
        ).json()

        assert (custom["rules"]["mode"], custom["rules"]["min_severity"]) == ("custom", 3)
        assert back["rules"]["mode"] == "threats"
        assert client.get(BASE).json()["items"][0]["rules"]["mode"] == "threats"

    def test_a_mode_there_is_not_is_refused(self, client: TestClient, csrf_token: str) -> None:
        body = add(client, csrf_token).json()

        response = client.put(
            f"{BASE}/{body['id']}/rules",
            json=rules(mode="everything"),
            headers=headers(csrf_token),
        )

        assert response.status_code == 422

    def test_the_rules_must_say_which(self, client: TestClient, csrf_token: str) -> None:
        body = add(client, csrf_token).json()
        without = {key: value for key, value in NEW_RULES.items() if key != "mode"}

        response = client.put(
            f"{BASE}/{body['id']}/rules", json=without, headers=headers(csrf_token)
        )

        assert response.status_code == 422

    def test_the_preview_of_threats_counts_what_is_on_the_threats_page(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        destination = add(client, csrf_token).json()
        incident(session, title="Chain", confidence=40, stages=["recon", "access"])
        incident(session, title="Suspect", confidence=50)
        incident(session, title="Quiet", verdict="not_suspicious")

        response = client.post(
            f"{BASE}/{destination['id']}/preview", json=rules(), headers=headers(csrf_token)
        )

        body = response.json()
        assert (body["considered"], body["would_send"]) == (3, 1)
        assert body["left_out"] == [
            {"reason": "muted", "text": "You called it not suspicious or low priority", "count": 1},
            {
                "reason": "threat",
                "text": "Not a threat: a suspect or background on the Threats page",
                "count": 1,
            },
        ]
        assert [example["title"] for example in body["examples"]] == ["Chain"]


class TestThePreview:
    def preview(self, client: TestClient, csrf_token: str, destination: int, **changes: Any) -> Any:
        # These are of the floors, so the rules are the custom ones unless a test says otherwise.
        return client.post(
            f"{BASE}/{destination}/preview",
            json=rules(**{"mode": "custom", **changes}),
            headers=headers(csrf_token),
        )

    def test_it_says_what_the_rules_would_have_sent_in_the_last_day(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        destination = add(client, csrf_token).json()
        sure = incident(session, title="Sure", severity=4, confidence=90)
        incident(session, title="Unsure", confidence=40)
        incident(session, title="Quiet", verdict="not_suspicious")
        incident(session, title="Old", last_seen_at=utcnow() - timedelta(hours=30))

        response = self.preview(client, csrf_token, destination["id"])

        assert response.status_code == 200
        body = response.json()
        assert (body["hours"], body["considered"], body["would_send"], body["held"]) == (
            24,
            3,
            1,
            0,
        )
        assert body["left_out"] == [
            {"reason": "muted", "text": "You called it not suspicious or low priority", "count": 1},
            {"reason": "confidence", "text": "AresGate is less than 65% sure", "count": 1},
        ]
        [example] = body["examples"]
        assert (example["id"], example["title"], example["severity"], example["confidence"]) == (
            sure.id,
            "Sure",
            "critical",
            90,
        )
        assert body["truncated"] is False

    def test_it_follows_the_rules_it_was_sent_and_not_the_ones_kept(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        destination = add(client, csrf_token).json()
        incident(session, confidence=40)

        kept = self.preview(client, csrf_token, destination["id"])
        looser = self.preview(client, csrf_token, destination["id"], min_confidence=30)

        assert (kept.json()["would_send"], looser.json()["would_send"]) == (0, 1)
        assert client.get(BASE).json()["items"][0]["rules"] == NEW_RULES

    def test_it_changes_and_sends_nothing(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        destination = add(client, csrf_token).json()
        incident(session)

        self.preview(client, csrf_token, destination["id"])

        assert audited(session, Action.ALERT_RULES_CHANGED) == []
        assert session.scalar(select(func.count()).select_from(ApiCall)) == 0

    def test_it_refuses_rules_that_make_no_sense(self, client: TestClient, csrf_token: str) -> None:
        destination = add(client, csrf_token).json()

        response = self.preview(client, csrf_token, destination["id"], time_zone="Nowhere/Land")

        assert response.status_code == 422

    def test_it_needs_a_destination_that_is_there(
        self, client: TestClient, csrf_token: str
    ) -> None:
        assert self.preview(client, csrf_token, 99).status_code == 404
