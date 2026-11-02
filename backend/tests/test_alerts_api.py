from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.alerts import destinations
from app.audit import Action, Outcome
from app.config import Settings
from app.integrations import netguard
from app.models import AlertDestination, ApiCall, AuditEvent, StoredCredential, User, utcnow
from app.security import credential_store
from app.security.credential_store import Kind
from e2e.stand_ins import discord as discord_stand_in
from tests.helpers import OTHER_ORIGIN
from tests.stubs import Answer, Serve, StubServer

BASE = "/api/alerts/destinations"
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
    assert client.post(BASE, json={"name": "x", "url": ADDRESS}).status_code == 403


class TestAddingOne:
    def test_an_install_with_none_has_an_empty_list(
        self, client: TestClient, csrf_token: str
    ) -> None:
        assert client.get(BASE).json() == {
            "items": [],
            "max_destinations": 10,
            "hosts": ["discord.com", "discordapp.com"],
        }

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
        assert client.delete(f"{BASE}/99", headers=headers(csrf_token)).status_code == 404


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
        assert client.post(f"{BASE}/99/test", headers=headers(csrf_token)).status_code == 404
