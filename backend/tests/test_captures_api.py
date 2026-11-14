"""The capture of a host's packets: who may ask, what is asked of ntopng and what is said back."""

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.api import captures as api
from app.audit import Action
from app.config import Settings
from app.models import AuditEvent, User
from e2e.stand_ins import Answer, Seen, ntopng, sample_ntopng_capture
from tests.ntopng import TOKEN, connect
from tests.stubs import Serve

URL = "/api/captures"
HOST = "192.168.1.20"


def ask(client: TestClient, token: str, **body: Any) -> Any:
    return client.post(URL, json={"host": HOST} | body, headers={"X-CSRF-Token": token})


def audited(session: Session) -> list[AuditEvent]:
    session.expire_all()
    return list(
        session.scalars(select(AuditEvent).where(AuditEvent.action == Action.CAPTURE_TAKEN))
    )


def test_it_is_only_for_someone_signed_in(client: TestClient, account: User) -> None:
    assert client.post(URL, json={"host": HOST}).status_code == 401


def test_it_returns_what_the_packets_say_and_keeps_a_record_of_asking(
    client: TestClient,
    csrf_token: str,
    session: Session,
    settings: Settings,
    serve: Serve,
) -> None:
    connect(session, settings, serve(ntopng(TOKEN, capture=sample_ntopng_capture(HOST))).url)

    response = ask(client, csrf_token, seconds=3)

    assert response.status_code == 200
    body = response.json()
    assert (body["host"], body["seconds"], body["total"], body["cut"]) == (HOST, 3, 6, False)
    assert body["max_packets"] == 300
    assert body["protocols"] == [
        {"protocol": "TCP", "packets": 5},
        {"protocol": "UDP", "packets": 1},
    ]
    first = body["packets"][0]
    assert (first["source"], first["destination"], first["flags"]) == (HOST, "93.184.216.34", "SYN")
    assert body["packets"][3]["preview"].startswith("GET / HTTP/1.1")
    (event,) = audited(session)
    assert event.outcome == audit.Outcome.SUCCESS
    assert event.detail == {"host": HOST, "seconds": 3, "packets": 6}


def test_an_address_is_written_in_its_usual_form(
    client: TestClient, csrf_token: str, session: Session, settings: Settings, serve: Serve
) -> None:
    connect(session, settings, serve(ntopng(TOKEN, capture=sample_ntopng_capture(HOST))).url)

    assert ask(client, csrf_token, host=" FE80:0::1 ").json()["host"] == "fe80::1"


def test_it_refuses_what_is_not_an_address(client: TestClient, csrf_token: str) -> None:
    assert ask(client, csrf_token, host="example.com").status_code == 422
    assert ask(client, csrf_token, seconds=0).status_code == 422
    assert ask(client, csrf_token, seconds=31).status_code == 422
    assert ask(client, csrf_token, extra=1).status_code == 422


def test_it_needs_ntopng_to_be_connected(client: TestClient, csrf_token: str) -> None:
    response = ask(client, csrf_token)

    assert response.status_code == 409
    assert response.json()["detail"] == "Connect ntopng first."


def test_it_says_when_the_connection_is_not_complete(
    client: TestClient,
    csrf_token: str,
    session: Session,
    settings: Settings,
    serve: Serve,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connect(session, settings, serve(ntopng(TOKEN)).url)

    def incomplete(*_: object) -> None:
        raise api.service.Incomplete("The token is missing.")

    monkeypatch.setattr(api.service, "load_target", incomplete)

    response = ask(client, csrf_token)

    assert response.status_code == 409
    assert response.json()["detail"] == "The token is missing."


def test_it_says_why_ntopng_gave_no_capture_and_records_that_too(
    client: TestClient, csrf_token: str, session: Session, settings: Settings, serve: Serve
) -> None:
    def handle(request: Seen) -> Answer:
        if request.path.endswith("live_traffic.lua"):
            return Answer(
                body=json.dumps({"error": "Not allowed"}),
                headers={"Content-Type": "application/json"},
            )
        return ntopng(TOKEN)(request)

    connect(session, settings, serve(handle).url)

    response = ask(client, csrf_token)

    assert response.status_code == 502
    assert "Not allowed" in response.json()["detail"]
    (event,) = audited(session)
    assert event.outcome == audit.Outcome.FAILURE
    assert event.detail == {"host": HOST, "seconds": 10}


def test_only_one_capture_runs_at_a_time(
    client: TestClient, csrf_token: str, session: Session, settings: Settings, serve: Serve
) -> None:
    connect(session, settings, serve(ntopng(TOKEN, capture=sample_ntopng_capture(HOST))).url)

    assert api.RUNNING.acquire(blocking=False)
    try:
        response = ask(client, csrf_token)
    finally:
        api.RUNNING.release()

    assert response.status_code == 409
    assert "already running" in response.json()["detail"]
    assert ask(client, csrf_token).status_code == 200
