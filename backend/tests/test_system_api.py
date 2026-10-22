import re
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import TextClause, text

from app import __version__
from app.api import system
from app.config import Settings, get_settings
from app.models import User, utcnow


def test_it_is_only_for_someone_signed_in(client: TestClient, account: User) -> None:
    response = client.get("/api/system")

    assert response.status_code == 401
    assert response.json() == {"detail": "You're not signed in."}


def test_it_says_what_is_running_and_for_how_long(client: TestClient, csrf_token: str) -> None:
    response = client.get("/api/system")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"version", "started_at", "uptime_seconds", "database"}
    assert body["version"] == __version__
    assert 0 <= body["uptime_seconds"] < 60
    started = datetime.fromisoformat(body["started_at"])
    assert timedelta(0) <= utcnow() - started < timedelta(minutes=1)
    assert body["database"]["status"] == "ok"
    assert re.fullmatch(r"\d+(\.\d+)*", body["database"]["version"])


def test_it_says_when_the_database_cannot_be_asked(
    client: TestClient, csrf_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def not_a_query(_: str) -> TextClause:
        return text("SELECT * FROM a_table_that_is_not_there")

    monkeypatch.setattr(system, "text", not_a_query)

    response = client.get("/api/system")

    assert response.status_code == 200
    assert response.json()["database"] == {"status": "unavailable", "version": None}


def test_the_public_health_check_still_says_nothing_about_the_install(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok", "database": "ok"}


def test_a_release_reports_the_version_it_was_built_as(
    app: FastAPI, client: TestClient, csrf_token: str, settings: Settings
) -> None:
    app.dependency_overrides[get_settings] = lambda: settings.model_copy(
        update={"release": "9.9.9"}
    )

    assert client.get("/api/system").json()["version"] == "9.9.9"
