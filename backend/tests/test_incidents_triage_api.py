"""Asking the AI about an incident from the web app, and what the incident then says of it."""

from ipaddress import ip_address
from typing import Any, get_args

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import catalog
from app.api.incidents import Classification
from app.audit import Action, Outcome
from app.config import Settings
from app.models import CLASSES, AiTriage, AuditEvent, User
from tests.stubs import Serve
from tests.test_ai_gateway import anthropic_says, turned_on
from tests.test_ai_service import KEY, saved
from tests.test_ai_triage import DEVICE, incident, kept, reads_it, ready, signals

BASE = "/api/incidents"


def headers(token: str) -> dict[str, str]:
    return {"X-CSRF-Token": token}


def read(client: TestClient, token: str, incident_id: int) -> Any:
    return client.post(f"{BASE}/{incident_id}/triage", headers=headers(token))


def audited(session: Session) -> list[AuditEvent]:
    session.expire_all()
    return list(
        session.scalars(
            select(AuditEvent)
            .where(AuditEvent.action == Action.INCIDENT_TRIAGED.value)
            .order_by(AuditEvent.id)
        )
    )


def test_it_is_only_for_someone_signed_in(client: TestClient, account: User) -> None:
    assert client.post(f"{BASE}/1/triage").status_code == 401


def test_what_the_api_says_of_the_classes_is_what_the_database_allows() -> None:
    assert get_args(Classification) == CLASSES


def test_an_incident_that_is_not_there_is_not_read(client: TestClient, csrf_token: str) -> None:
    assert read(client, csrf_token, 4040).status_code == 404


def test_an_incident_the_ai_has_not_read_has_no_reading(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    found = incident(session)
    session.commit()

    detail = client.get(f"{BASE}/{found.id}").json()
    [listed] = client.get(BASE).json()["items"]

    assert detail["reading"] is None
    assert detail["ai"] is None
    assert listed["ai"] is None


def test_with_ai_off_it_says_so_and_the_incident_is_as_it_was(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    found = incident(session)
    session.commit()

    response = read(client, csrf_token, found.id)

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["reason"].startswith("AI is turned off.")
    assert body["incident"]["id"] == found.id
    assert body["incident"]["reading"] is None
    [event] = audited(session)
    assert event.outcome == Outcome.FAILURE.value
    assert event.detail == {"incident": found.id}


def test_the_ai_reads_it_and_the_page_gets_the_reading_with_the_real_names(
    client: TestClient,
    csrf_token: str,
    app: FastAPI,
    serve: Serve,
    session: Session,
    settings: Settings,
) -> None:
    server = serve(reads_it())
    app.state.ai_origins["anthropic"] = server.url
    ready(session, settings)
    found = incident(session)
    signals(session, found)
    session.commit()

    response = read(client, csrf_token, found.id)

    body = response.json()
    assert body["ok"] is True
    assert body["reason"] is None
    reading = body["incident"]["reading"]
    assert reading["classification"] == "probe"
    assert reading["confidence"] == 91
    assert reading["headline"] == "An internet scanner looked at one device"
    assert reading["story"] == f"{DEVICE} was scanned."
    assert reading["checks"] == ["Look at the firewall rules for port 22", "Nothing else needed"]
    assert reading["verdict"] == "low_priority"
    assert reading["verdict_reason"] == "Routine background scanning."
    assert (reading["provider"], reading["model"]) == ("Anthropic", "claude-haiku-5-5")
    assert reading["signals_read"] == 3
    assert body["incident"]["ai"] == {"classification": "probe", "confidence": 91}
    assert KEY not in response.text
    [event] = audited(session)
    assert event.outcome == Outcome.SUCCESS.value
    assert event.detail == {
        "incident": found.id,
        "classification": "probe",
        "model": "claude-haiku-5-5",
    }


def test_the_reading_stays_with_the_incident_and_is_in_the_list(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    read_one = incident(session, subject="203.0.113.7", addresses=[ip_address("203.0.113.7")])
    unread = incident(session, subject="203.0.113.8", addresses=[ip_address("203.0.113.8")])
    kept(session, read_one, classification="attack", confidence=77, provider="gone", model="m")
    session.commit()

    items = {item["id"]: item for item in client.get(BASE).json()["items"]}
    detail = client.get(f"{BASE}/{read_one.id}").json()

    assert items[read_one.id]["ai"] == {"classification": "attack", "confidence": 77}
    assert items[unread.id]["ai"] is None
    assert detail["reading"]["provider"] == "gone"
    assert detail["reading"]["classification"] == "attack"


def test_a_provider_that_refuses_is_reported_and_nothing_is_kept(
    client: TestClient,
    csrf_token: str,
    app: FastAPI,
    serve: Serve,
    session: Session,
    settings: Settings,
) -> None:
    server = serve(anthropic_says("unused"))
    app.state.ai_origins["anthropic"] = server.url
    saved(session, settings, catalog.ANTHROPIC, api_key="sk-a-different-key-0123456789")
    turned_on(session, "anthropic")
    found = incident(session)
    session.commit()

    body = read(client, csrf_token, found.id).json()

    assert body["ok"] is False
    assert body["reason"].startswith("The AI provider didn't answer.")
    assert body["incident"]["reading"] is None
    assert session.scalars(select(AiTriage)).all() == []
    [event] = audited(session)
    assert event.outcome == Outcome.FAILURE.value


def test_an_answer_that_is_not_a_reading_is_reported(
    client: TestClient,
    csrf_token: str,
    app: FastAPI,
    serve: Serve,
    session: Session,
    settings: Settings,
) -> None:
    server = serve(anthropic_says("It looks like a scan to me."))
    app.state.ai_origins["anthropic"] = server.url
    ready(session, settings)
    found = incident(session)
    session.commit()

    body = read(client, csrf_token, found.id).json()

    assert body["ok"] is False
    assert "not in a form AresGate could read" in body["reason"]
    assert body["incident"]["reading"] is None
