"""Alerts by email: the mail server's settings and password, email destinations through the API,
and the notifier sending to one."""

import asyncio
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.alerts import destinations, mail, notify
from app.alerts.discord import Sent
from app.audit import Action, Outcome
from app.config import Settings
from app.integrations import netguard
from app.models import AlertDelivery, AlertDestination, AuditEvent, SmtpSettings, StoredCredential
from app.models.base import utcnow
from app.security import credential_store
from app.security.credential_store import Kind
from tests.test_alerts_api import ADDRESS, BASE, add, audited, headers
from tests.test_alerts_notify import HOUR, incident, nothing

SMTP = "/api/alerts/smtp"
PASSWORD = "correct horse battery staple"


def server_body(**changes: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "host": "smtp.example.com",
        "port": 587,
        "security": "starttls",
        "username": "alerts@example.com",
        "sender": "alerts@example.com",
        "password": PASSWORD,
    }
    body.update(changes)
    return body


def set_up(client: TestClient, token: str, **changes: Any) -> Any:
    return client.put(SMTP, json=server_body(**changes), headers=headers(token))


def add_email(client: TestClient, token: str, **changes: Any) -> Any:
    body = {"kind": "email", "name": "Inbox", "recipient": "me@example.org", **changes}
    return client.post(BASE, json=body, headers=headers(token))


class Sending:
    """Stands in for ``mail.send``: remembers what was sent and where, and answers as told."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, answer: Sent | None = None) -> None:
        self.answer = answer or Sent(ok=True, status=250)
        self.sent: list[tuple[mail.Mailbox, dict[str, object]]] = []
        monkeypatch.setattr(mail, "send", self)

    async def __call__(self, box: mail.Mailbox, payload: dict[str, object]) -> Sent:
        self.sent.append((box, payload))
        return self.answer


class TestTheMailServer:
    def test_there_is_none_until_it_is_set_up(self, client: TestClient, csrf_token: str) -> None:
        shown = client.get(BASE).json()["smtp"]

        assert shown == {
            "configured": False,
            "host": "",
            "port": 587,
            "security": "starttls",
            "username": None,
            "sender": "",
            "password_kept": False,
            "default_ports": {"starttls": 587, "ssl": 465, "none": 25},
        }

    def test_it_is_for_someone_signed_in_and_not_for_another_website(
        self, client: TestClient, account: Any
    ) -> None:
        assert client.get("/api/alerts/destinations").status_code == 401
        for method in ("put", "delete"):
            assert client.request(method, SMTP).status_code == 401
        assert client.put(SMTP, json=server_body()).status_code in (401, 403)

    def test_it_is_kept_and_the_password_is_sealed_and_never_shown(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        response = set_up(client, csrf_token, host=" SMTP.Example.com ")

        assert response.status_code == 200
        assert response.json() == {
            "configured": True,
            "host": "smtp.example.com",
            "port": 587,
            "security": "starttls",
            "username": "alerts@example.com",
            "sender": "alerts@example.com",
            "password_kept": True,
            "default_ports": {"starttls": 587, "ssl": 465, "none": 25},
        }
        assert client.get(BASE).json()["smtp"] == response.json()
        everything = response.text + client.get(BASE).text
        assert PASSWORD not in everything
        session.expire_all()
        sealed = session.scalars(
            select(StoredCredential).where(StoredCredential.kind == Kind.SMTP.value)
        ).one()
        assert PASSWORD not in str(sealed.__dict__)
        assert credential_store.reveal(session, settings, Kind.SMTP, "server", "password") == (
            PASSWORD
        )
        assert session.get(SmtpSettings, 1) is not None
        [event] = audited(session, Action.ALERT_SMTP_CHANGED)
        assert event.outcome == Outcome.SUCCESS.value
        assert event.detail == {"host": "smtp.example.com", "security": "starttls"}
        assert PASSWORD not in str(event.detail)

    def test_saving_again_without_a_password_keeps_the_one_kept(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        set_up(client, csrf_token)

        response = set_up(client, csrf_token, host="mail.example.org", password=None)

        assert response.status_code == 200
        assert response.json()["host"] == "mail.example.org"
        assert response.json()["password_kept"] is True
        session.expire_all()
        assert credential_store.reveal(session, settings, Kind.SMTP, "server", "password") == (
            PASSWORD
        )

    def test_a_new_password_replaces_the_old(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        set_up(client, csrf_token)

        set_up(client, csrf_token, password="another one")

        session.expire_all()
        assert credential_store.reveal(session, settings, Kind.SMTP, "server", "password") == (
            "another one"
        )

    def test_a_server_that_needs_none_has_the_password_forgotten(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        set_up(client, csrf_token)

        response = set_up(
            client,
            csrf_token,
            username=None,
            password=None,
            clear_password=True,
            security="none",
            port=25,
        )

        assert response.status_code == 200
        assert response.json()["password_kept"] is False
        assert response.json()["username"] is None
        session.expire_all()
        assert session.scalars(select(StoredCredential)).all() == []

    def test_a_user_name_with_no_password_kept_needs_one(
        self, client: TestClient, csrf_token: str
    ) -> None:
        response = set_up(client, csrf_token, password=None)

        assert response.status_code == 200
        assert response.json()["password_kept"] is False
        assert response.json()["username"] == "alerts@example.com"

    @pytest.mark.parametrize(
        ("changes", "field"),
        [
            ({"host": "not a host"}, "host"),
            ({"port": 0}, "port"),
            ({"port": 70000}, "port"),
            ({"security": "tls"}, "security"),
            ({"security": "none"}, "security"),
            ({"sender": "nobody"}, "sender"),
            ({"password": "a\nb"}, "password"),
            ({"username": None}, "username"),
        ],
    )
    def test_what_cannot_be_used_is_refused_on_its_field_without_repeating_the_password(
        self, client: TestClient, csrf_token: str, changes: dict[str, Any], field: str
    ) -> None:
        response = set_up(client, csrf_token, **changes)

        assert response.status_code == 422
        assert response.json()["detail"][0]["loc"] == ["body", field]
        assert PASSWORD not in response.text

    def test_an_unknown_field_is_refused(self, client: TestClient, csrf_token: str) -> None:
        assert set_up(client, csrf_token, extra=1).status_code == 422

    def test_a_refused_change_changes_nothing(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        set_up(client, csrf_token)

        set_up(client, csrf_token, host="not a host")

        assert client.get(BASE).json()["smtp"]["host"] == "smtp.example.com"

    def test_removing_it_forgets_the_server_and_the_password(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        set_up(client, csrf_token)

        response = client.delete(SMTP, headers=headers(csrf_token))

        assert response.status_code == 204
        assert client.get(BASE).json()["smtp"]["configured"] is False
        session.expire_all()
        assert session.scalars(select(StoredCredential)).all() == []
        assert len(audited(session, Action.ALERT_SMTP_REMOVED)) == 1

    def test_removing_what_is_not_there_is_not_an_error(
        self, client: TestClient, csrf_token: str
    ) -> None:
        response = client.delete(SMTP, headers=headers(csrf_token))

        assert response.status_code == 204

    def test_saving_lets_every_email_destination_try_again(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        set_up(client, csrf_token)
        made = add_email(client, csrf_token).json()
        row = session.get(AlertDestination, made["id"])
        assert row is not None
        row.refused = True
        row.last_error = "The mail server didn't accept the user name and password."
        row.last_attempt_at = utcnow()
        session.commit()

        set_up(client, csrf_token, password="the right one")

        session.expire_all()
        assert (row.refused, row.last_error, row.last_attempt_at) == (False, None, None)


class TestEmailDestinations:
    def test_it_is_kept_and_shown_with_its_address_and_the_server_it_goes_through(
        self, client: TestClient, csrf_token: str
    ) -> None:
        set_up(client, csrf_token)

        response = add_email(client, csrf_token, recipient=" me@example.org ")

        assert response.status_code == 201
        body = response.json()
        assert (body["kind"], body["recipient"], body["host"]) == (
            "email",
            "me@example.org",
            "smtp.example.com",
        )
        assert (body["status"], body["hint"], body["enabled"]) == ("untested", "", True)
        assert body["rules"]["mode"] == "threats"
        assert client.get(BASE).json()["items"] == [body]

    def test_without_a_mail_server_it_is_not_connected(
        self, client: TestClient, csrf_token: str
    ) -> None:
        body = add_email(client, csrf_token).json()

        assert (body["status"], body["host"]) == ("not_connected", "")

    def test_setting_the_server_up_connects_it(self, client: TestClient, csrf_token: str) -> None:
        add_email(client, csrf_token)

        set_up(client, csrf_token)

        assert client.get(BASE).json()["items"][0]["status"] == "untested"

    def test_removing_the_server_leaves_it_waiting_for_one(
        self, client: TestClient, csrf_token: str
    ) -> None:
        set_up(client, csrf_token)
        add_email(client, csrf_token)

        client.delete(SMTP, headers=headers(csrf_token))

        assert client.get(BASE).json()["items"][0]["status"] == "not_connected"

    @pytest.mark.parametrize(
        "recipient", ["nobody", "a@b", "x y@example.org", "a@example.org,b@example.org"]
    )
    def test_an_address_that_is_not_one_is_refused_on_the_field(
        self, client: TestClient, csrf_token: str, recipient: str
    ) -> None:
        response = add_email(client, csrf_token, recipient=recipient)

        assert response.status_code == 422
        assert response.json()["detail"][0]["loc"] == ["body", "recipient"]

    def test_an_address_is_needed_and_a_webhook_is_for_discord_only(
        self, client: TestClient, csrf_token: str
    ) -> None:
        missing = client.post(
            BASE, json={"kind": "email", "name": "Inbox"}, headers=headers(csrf_token)
        )
        webhook_missing = client.post(
            BASE, json={"kind": "discord", "name": "Inbox"}, headers=headers(csrf_token)
        )

        assert missing.status_code == 422
        assert webhook_missing.status_code == 422
        assert add(client, csrf_token, kind="discord").status_code == 201

    def test_a_name_is_taken_whatever_the_kind(self, client: TestClient, csrf_token: str) -> None:
        add(client, csrf_token, name="Security")

        response = add_email(client, csrf_token, name="security")

        assert response.status_code == 422
        assert response.json()["detail"][0]["loc"] == ["body", "name"]

    def test_the_audit_log_says_the_kind(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        add_email(client, csrf_token)

        [event] = audited(session, Action.ALERT_DESTINATION_ADDED)
        assert event.detail == {"destination": "Inbox", "kind": "email"}

    def test_it_is_sent_to_another_address_and_forgets_how_it_went(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        set_up(client, csrf_token)
        made = add_email(client, csrf_token).json()
        row = session.get(AlertDestination, made["id"])
        assert row is not None
        row.refused, row.last_error, row.last_attempt_at = True, "no", utcnow()
        session.commit()

        response = client.patch(
            f"{BASE}/{made['id']}",
            json={"recipient": "you@example.org"},
            headers=headers(csrf_token),
        )

        assert response.status_code == 200
        assert response.json()["recipient"] == "you@example.org"
        assert response.json()["last_error"] is None
        session.expire_all()
        assert (row.refused, row.last_attempt_at) == (False, None)
        [event] = audited(session, Action.ALERT_DESTINATION_CHANGED)
        assert event.detail == {"destination": "Inbox", "changed": "address"}

    def test_a_new_address_that_is_refused_changes_nothing(
        self, client: TestClient, csrf_token: str
    ) -> None:
        set_up(client, csrf_token)
        made = add_email(client, csrf_token).json()

        response = client.patch(
            f"{BASE}/{made['id']}", json={"recipient": "nonsense"}, headers=headers(csrf_token)
        )

        assert response.status_code == 422
        assert response.json()["detail"][0]["loc"] == ["body", "recipient"]
        assert client.get(BASE).json()["items"][0]["recipient"] == "me@example.org"

    def test_an_address_means_nothing_for_the_other_kind(
        self, client: TestClient, csrf_token: str
    ) -> None:
        discord = add(client, csrf_token).json()
        set_up(client, csrf_token)
        email = add_email(client, csrf_token).json()

        client.patch(
            f"{BASE}/{discord['id']}",
            json={"recipient": "me@example.org"},
            headers=headers(csrf_token),
        )
        client.patch(f"{BASE}/{email['id']}", json={"url": ADDRESS}, headers=headers(csrf_token))

        items = client.get(BASE).json()["items"]
        assert [item["recipient"] for item in items] == [None, "me@example.org"]
        assert [item["hint"] for item in items] == ["…6789", ""]

    def test_removing_one_leaves_the_mail_server(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        set_up(client, csrf_token)
        made = add_email(client, csrf_token).json()

        response = client.delete(f"{BASE}/{made['id']}", headers=headers(csrf_token))

        assert response.status_code == 204

        assert client.get(BASE).json()["smtp"]["password_kept"] is True


class TestTheTestMessage:
    def test_it_goes_through_the_server_to_the_address_and_the_destination_is_working(
        self, client: TestClient, csrf_token: str, monkeypatch: pytest.MonkeyPatch, session: Session
    ) -> None:
        set_up(client, csrf_token)
        made = add_email(client, csrf_token).json()
        sending = Sending(monkeypatch)

        response = client.post(f"{BASE}/{made['id']}/test", headers=headers(csrf_token))

        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        assert (
            body["message"]
            == "The test message was sent. Look for it in the inbox of me@example.org."
        )
        assert body["destination"]["status"] == "connected"
        [(box, payload)] = sending.sent
        assert box.recipient == "me@example.org"
        assert (box.server.host, box.server.password) == ("smtp.example.com", PASSWORD)
        assert "AresGate can email you" in str(payload)
        assert PASSWORD not in response.text
        [event] = audited(session, Action.ALERT_DESTINATION_TESTED)
        assert event.outcome == Outcome.SUCCESS.value

    def test_a_sample_alert_goes_in_the_form_the_rules_give_it(
        self, client: TestClient, csrf_token: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        set_up(client, csrf_token)
        made = add_email(client, csrf_token).json()
        sending = Sending(monkeypatch)

        response = client.post(f"{BASE}/{made['id']}/sample", headers=headers(csrf_token))

        assert response.json()["message"] == (
            "The sample alert was sent. Look for it in the inbox of me@example.org."
        )
        assert len(sending.sent) == 1

    def test_what_went_wrong_is_said_in_the_mail_servers_words(
        self, client: TestClient, csrf_token: str, monkeypatch: pytest.MonkeyPatch, session: Session
    ) -> None:
        set_up(client, csrf_token)
        made = add_email(client, csrf_token).json()
        Sending(
            monkeypatch,
            Sent(ok=False, status=535, problem="The mail server didn't accept it.", gone=True),
        )

        response = client.post(f"{BASE}/{made['id']}/test", headers=headers(csrf_token))

        body = response.json()
        assert (body["ok"], body["message"]) == (False, "The mail server didn't accept it.")
        assert body["destination"]["status"] == "problem"
        assert body["destination"]["last_error"] == "The mail server didn't accept it."
        [event] = audited(session, Action.ALERT_DESTINATION_TESTED)
        assert event.outcome == Outcome.FAILURE.value

    def test_a_failure_that_says_nothing_is_still_a_failure_in_words(
        self, client: TestClient, csrf_token: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        set_up(client, csrf_token)
        made = add_email(client, csrf_token).json()
        Sending(monkeypatch, Sent(ok=False, status=None))

        body = client.post(f"{BASE}/{made['id']}/test", headers=headers(csrf_token)).json()

        assert body["message"] == "The message didn't get through."

    def test_without_a_mail_server_it_says_to_set_one_up(
        self, client: TestClient, csrf_token: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        made = add_email(client, csrf_token).json()
        sending = Sending(monkeypatch)

        body = client.post(f"{BASE}/{made['id']}/test", headers=headers(csrf_token)).json()

        assert body["ok"] is False
        assert body["message"].startswith("The mail server isn't set up.")
        assert sending.sent == []

    def test_a_password_that_cannot_be_opened_is_a_problem_in_words(
        self,
        client: TestClient,
        csrf_token: str,
        monkeypatch: pytest.MonkeyPatch,
        session: Session,
    ) -> None:
        set_up(client, csrf_token)
        made = add_email(client, csrf_token).json()
        sending = Sending(monkeypatch)
        stored = session.scalars(
            select(StoredCredential).where(StoredCredential.kind == Kind.SMTP.value)
        ).one()
        stored.value_sealed = "not a sealed secret"
        session.commit()

        body = client.post(f"{BASE}/{made['id']}/test", headers=headers(csrf_token)).json()

        assert body["ok"] is False
        assert "password can't be opened" in body["message"]
        assert sending.sent == []


class TestTheNotifier:
    def mailbox(self, session: Session, settings: Settings) -> AlertDestination:
        destinations.save_smtp(
            session,
            settings,
            host="smtp.example.com",
            port=587,
            security="starttls",
            username="alerts@example.com",
            sender="alerts@example.com",
            password=PASSWORD,
            clear_password=False,
            now=utcnow(),
        )
        row = destinations.create_email(session, "Inbox", "me@example.org", utcnow() - 2 * HOUR)
        row.listening_since = utcnow() - HOUR
        row.mode = "custom"
        session.commit()
        return row

    def tell(
        self, settings: Settings, engine: Engine, policy: netguard.AddressPolicy | None = None
    ) -> notify.Report:
        new_session: Callable[[], Session] = sessionmaker(bind=engine, expire_on_commit=False)
        return asyncio.run(
            notify.notify_once(
                settings, new_session, nothing, policy or netguard.PUBLIC_INTERNET, pace=0
            )
        )

    def test_an_incident_is_emailed_once_and_the_log_says_so(
        self,
        session: Session,
        settings: Settings,
        engine: Engine,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        row = self.mailbox(session, settings)
        incident(session, last_seen_at=utcnow(), first_seen_at=utcnow())
        sending = Sending(monkeypatch)

        first = self.tell(settings, engine)
        second = self.tell(settings, engine)

        assert (first, second) == (notify.Report(sent=1), notify.Report())
        [(box, payload)] = sending.sent
        assert box.recipient == "me@example.org"
        assert box.server.password == PASSWORD
        assert "embeds" in payload
        session.expire_all()
        [sent] = session.scalars(select(AlertDelivery)).all()
        assert (sent.state, sent.attempts, sent.message_id) == ("sent", 1, None)
        session.refresh(row)
        assert row.last_success_at is not None
        assert PASSWORD not in str(sent.note)

    def test_nothing_is_sent_while_there_is_no_mail_server(
        self,
        session: Session,
        settings: Settings,
        engine: Engine,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        self.mailbox(session, settings)
        destinations.forget_smtp(session)
        session.commit()
        incident(session, last_seen_at=utcnow(), first_seen_at=utcnow())
        sending = Sending(monkeypatch)

        assert self.tell(settings, engine) == notify.Report()

        assert sending.sent == []
        assert session.scalars(select(AlertDelivery)).all() == []

    def test_a_server_that_refuses_the_sign_in_stops_every_waiting_message_and_names_the_fix(
        self,
        session: Session,
        settings: Settings,
        engine: Engine,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        row = self.mailbox(session, settings)
        for number in (1, 2):
            incident(session, subject=f"93.184.216.{number}", last_seen_at=utcnow())
        Sending(
            monkeypatch,
            Sent(ok=False, status=535, problem="The mail server didn't accept it.", gone=True),
        )

        report = self.tell(settings, engine)

        assert report == notify.Report(failed=1)
        session.expire_all()
        assert row.refused is True
        assert {(each.state, each.note) for each in session.scalars(select(AlertDelivery))} == {
            ("failed", "The mail server didn't accept it."),
            ("failed", notify.REFUSED_NOTES["email"]),
        }
        # Refused, so nothing more is tried until the settings or the address are fixed.
        assert self.tell(settings, engine) == notify.Report()

    def test_a_server_that_cannot_be_reached_is_tried_again_later(
        self,
        session: Session,
        settings: Settings,
        engine: Engine,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        self.mailbox(session, settings)
        incident(session, last_seen_at=utcnow(), first_seen_at=utcnow())
        Sending(
            monkeypatch,
            Sent(ok=False, status=None, problem="Couldn't reach the mail server.", retry=True),
        )

        assert self.tell(settings, engine) == notify.Report(retrying=1)

        session.expire_all()
        [waiting] = session.scalars(select(AlertDelivery)).all()
        assert waiting.state == "retrying"
        assert waiting.due_at > utcnow() + timedelta(seconds=20)

    def test_an_email_is_not_changed_after_it_is_sent_so_a_stood_down_incident_is_not_followed_up(
        self,
        session: Session,
        settings: Settings,
        engine: Engine,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        row = self.mailbox(session, settings)
        row.mode = "threats"
        found = incident(
            session,
            last_seen_at=utcnow(),
            first_seen_at=utcnow(),
            confidence=90,
            stages=["recon", "access"],
        )
        sending = Sending(monkeypatch)
        self.tell(settings, engine)
        found.verdict = "not_suspicious"
        found.status = "dismissed"
        session.commit()

        self.tell(settings, engine)

        assert len(sending.sent) == 1
        session.expire_all()
        assert [each.kind for each in session.scalars(select(AlertDelivery))] == ["incident"]


def test_the_audit_log_never_holds_the_password(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    set_up(client, csrf_token)
    add_email(client, csrf_token)

    everything = " ".join(str(each.detail) for each in session.scalars(select(AuditEvent)))

    assert PASSWORD not in everything
