import logging
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware import HEADER

ID = re.compile(r"[0-9a-f]{32}")
SENT = "0123456789abcdef0123456789abcdef"


def request_logs(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == "aresgate.request"]


def test_every_response_carries_the_id_of_its_request(client: TestClient) -> None:
    first = client.get("/api/health").headers[HEADER]
    second = client.get("/api/health").headers[HEADER]

    assert ID.fullmatch(first)
    assert first != second


def test_a_sensible_id_from_nginx_is_kept(client: TestClient) -> None:
    response = client.get("/api/health", headers={HEADER: SENT})

    assert response.headers[HEADER] == SENT


@pytest.mark.parametrize(
    "sent", ["short", "has spaces in it!", "x" * 65, "line\x7fbreak-id-123", ""]
)
def test_anything_else_is_replaced(client: TestClient, sent: str) -> None:
    response = client.get("/api/health", headers={HEADER: sent})

    assert ID.fullmatch(response.headers[HEADER])


def test_the_response_to_a_refused_request_has_it_too(client: TestClient) -> None:
    response = client.post("/api/auth/login", json={}, headers={"Origin": "https://evil.example"})

    assert response.status_code == 403
    assert ID.fullmatch(response.headers[HEADER])


def test_each_request_is_logged_once_with_its_id(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG, logger="aresgate.request"):
        response = client.get("/api/system?limit=5&since=2026-10-22T00:00:00Z")

    [record] = request_logs(caplog)
    assert record.getMessage() == "GET /api/system 401"
    assert record.levelno == logging.INFO
    assert (record.method, record.path, record.status) == ("GET", "/api/system", 401)  # type: ignore[attr-defined]
    assert record.client == "testclient"  # type: ignore[attr-defined]
    assert record.duration_ms >= 0  # type: ignore[attr-defined]
    assert response.headers[HEADER]
    # The query string can carry what shouldn't be logged.
    assert "limit" not in caplog.text
    assert "since" not in caplog.text


def test_the_health_check_is_only_worth_a_line_when_it_fails(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG, logger="aresgate.request"):
        client.get("/api/health")

    [record] = request_logs(caplog)
    assert record.levelno == logging.DEBUG


def test_a_very_long_path_is_cut_short(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG, logger="aresgate.request"):
        client.get("/api/" + "x" * 1000)

    [record] = request_logs(caplog)
    assert len(record.path) == 200  # type: ignore[attr-defined]


def add_broken_route(app: FastAPI) -> None:
    def broken() -> None:
        raise RuntimeError("something broke, password=hunter2")

    app.add_api_route("/api/broken", broken)


def test_an_error_gets_a_plain_answer_that_still_has_the_id(
    app: FastAPI, caplog: pytest.LogCaptureFixture
) -> None:
    add_broken_route(app)
    with (
        caplog.at_level(logging.DEBUG, logger="aresgate.request"),
        TestClient(app, raise_server_exceptions=False) as client,
    ):
        response = client.get("/api/broken", headers={HEADER: SENT})

    assert response.status_code == 500
    assert response.json() == {"detail": "AresGate ran into a problem. Try again in a moment."}
    assert response.headers[HEADER] == SENT
    [record] = request_logs(caplog)
    assert (record.levelno, record.status) == (logging.ERROR, 500)  # type: ignore[attr-defined]
