"""The checks every route shares: where a change comes from, and who is signed in."""

from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.api.deps import client_address
from app.config import Settings, get_settings
from app.models import User, UserSession, utcnow
from app.security import sessions
from tests.helpers import ACCOUNT_USERNAME, ORIGIN, OTHER_ORIGIN

LOGIN = {"username": ACCOUNT_USERNAME, "password": "wrong"}


def test_a_change_from_aresgates_own_pages_is_let_through(client: TestClient) -> None:
    assert client.post("/api/auth/login", json=LOGIN).status_code == 401


def test_a_change_without_an_origin_is_refused(app: FastAPI) -> None:
    with TestClient(app, base_url=ORIGIN) as bare:
        response = bare.post("/api/auth/login", json=LOGIN)

    assert response.status_code == 403
    assert "didn't come from AresGate" in response.json()["detail"]


@pytest.mark.parametrize(
    "origin",
    [
        OTHER_ORIGIN,
        "null",
        "http://aresgate.test",
        "https://aresgate.test:8443",
        "https://aresgate.test.evil.example",
        "http://localhost:5173",
    ],
)
def test_a_change_from_anywhere_else_is_refused_in_production(
    app: FastAPI, settings: Settings, origin: str
) -> None:
    production = settings.model_copy(update={"environment": "production"})
    app.dependency_overrides[get_settings] = lambda: production
    with TestClient(app, base_url=ORIGIN) as other:
        response = other.post("/api/auth/login", json=LOGIN, headers={"Origin": origin})

    assert response.status_code == 403


@pytest.mark.parametrize(
    "origin",
    [
        OTHER_ORIGIN,
        "null",
        "",
        "http://localhost.evil.example",
        "http://localhost@evil.example",
        "http://localhost:abc",
        "http://localhost:5173/path",
        "http://[::1",
        "https://localhost:5173",
        "ftp://localhost",
    ],
)
def test_a_change_from_another_website_is_refused(client: TestClient, origin: str) -> None:
    assert client.post("/api/auth/login", json=LOGIN, headers={"Origin": origin}).status_code == 403


@pytest.mark.parametrize(
    "origin", ["http://localhost:5173", "http://127.0.0.1:14173", "http://localhost"]
)
def test_the_dev_server_may_make_changes_outside_production(
    client: TestClient, origin: str
) -> None:
    response = client.post("/api/auth/login", json=LOGIN, headers={"Origin": origin})

    assert response.status_code == 401


def test_the_port_is_part_of_the_origin(app: FastAPI, settings: Settings) -> None:
    on_8443 = settings.model_copy(update={"https_port": 8443})
    app.dependency_overrides[get_settings] = lambda: on_8443
    with TestClient(app, base_url="https://aresgate.test:8443") as other:
        allowed = other.post(
            "/api/auth/login", json=LOGIN, headers={"Origin": "https://aresgate.test:8443"}
        )
        refused = other.post("/api/auth/login", json=LOGIN, headers={"Origin": ORIGIN})

    assert allowed.status_code == 401
    assert refused.status_code == 403


def test_reading_needs_no_origin(app: FastAPI) -> None:
    with TestClient(app, base_url=ORIGIN) as bare:
        assert bare.get("/api/health").status_code == 200
        assert bare.get("/api/setup/status").status_code == 200


def test_the_address_is_the_one_the_server_saw() -> None:
    known = Request({"type": "http", "headers": [], "client": ("203.0.113.9", 4321)})
    unknown = Request({"type": "http", "headers": [], "client": None})

    assert client_address(known) == "203.0.113.9"
    assert client_address(unknown) == "unknown"


def test_nobody_is_signed_in_without_a_cookie(client: TestClient) -> None:
    response = client.get("/api/auth/session")

    assert response.status_code == 401
    assert response.json() == {"detail": "You're not signed in."}


def test_a_made_up_cookie_signs_nobody_in(client: TestClient, account: User) -> None:
    client.cookies.set(sessions.COOKIE_NAME, "made-up", domain="aresgate.test")

    assert client.get("/api/auth/session").status_code == 401


def test_a_signed_in_browser_is_recognised(client: TestClient, csrf_token: str) -> None:
    response = client.get("/api/auth/session")

    assert response.status_code == 200
    body = response.json()
    assert body["username"] == ACCOUNT_USERNAME
    assert body["csrf_token"] == csrf_token


def test_a_session_that_sat_idle_is_over(
    client: TestClient, csrf_token: str, session: Session, settings: Settings
) -> None:
    row = session.scalars(select(UserSession)).one()
    row.last_seen_at = utcnow() - timedelta(minutes=settings.session_idle_minutes, seconds=1)
    session.commit()

    assert client.get("/api/auth/session").status_code == 401
    assert session.scalars(select(UserSession)).first() is None


def test_a_session_that_lasted_all_day_is_over(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    row = session.scalars(select(UserSession)).one()
    row.expires_at = utcnow() - timedelta(seconds=1)
    session.commit()

    assert client.get("/api/auth/session").status_code == 401


def test_a_change_needs_the_security_token(client: TestClient, csrf_token: str) -> None:
    missing = client.post("/api/auth/logout")
    wrong = client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf_token[::-1]})
    foreign = client.post("/api/auth/logout", headers=[(b"X-CSRF-Token", b"caf\xe9")])

    assert [missing.status_code, wrong.status_code, foreign.status_code] == [403, 403, 403]
    assert client.get("/api/auth/session").status_code == 200


def test_the_security_token_is_not_needed_to_read(client: TestClient, csrf_token: str) -> None:
    assert client.get("/api/auth/session").status_code == 200


def test_the_security_token_of_one_sign_in_is_no_use_in_another(
    app: FastAPI, client: TestClient, csrf_token: str
) -> None:
    with TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN}) as second:
        other = second.post(
            "/api/auth/login",
            json={"username": ACCOUNT_USERNAME, "password": "a sentence nobody would guess"},
        ).json()["csrf_token"]

    assert other != csrf_token
    assert client.post("/api/auth/logout", headers={"X-CSRF-Token": other}).status_code == 403


def test_the_ended_session_is_removed_from_the_database(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf_token})

    assert session.scalars(select(UserSession)).first() is None
