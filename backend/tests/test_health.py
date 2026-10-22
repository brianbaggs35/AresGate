from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.db import get_session


def test_health_reports_ok_with_a_database(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_says_nothing_else(client: TestClient) -> None:
    assert set(client.get("/api/health").json()) == {"status", "database"}


def test_health_is_degraded_when_the_database_is_down(app: FastAPI) -> None:
    class BrokenSession(Session):
        def execute(self, *args: object, **kwargs: object) -> None:  # type: ignore[override]
            raise OperationalError("SELECT 1", {}, Exception("down"))

    app.dependency_overrides[get_session] = lambda: BrokenSession()
    response = TestClient(app).get("/api/health")
    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "unavailable"}
