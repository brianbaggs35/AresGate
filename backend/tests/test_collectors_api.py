from datetime import timedelta
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import CollectorHealth, User, WorkerBeat, utcnow

BASE = "/api/collectors"


def health_row(session: Session, integration: str, key: str, **changes: object) -> CollectorHealth:
    row = CollectorHealth(
        collector="connection-check",
        integration=integration,
        connection=key,
        interval_seconds=300,
        consecutive_failures=0,
        updated_at=utcnow(),
    )
    for name, value in changes.items():
        setattr(row, name, value)
    session.add(row)
    session.commit()
    return row


def get(client: TestClient, **query: str) -> dict[str, Any]:
    response = client.get(BASE, params=query)
    assert response.status_code == 200
    return response.json()


def test_it_is_only_for_someone_signed_in(client: TestClient, account: User) -> None:
    response = client.get(BASE)

    assert response.status_code == 401
    assert response.json() == {"detail": "You're not signed in."}


def test_there_is_nothing_to_report_before_the_worker_has_reported_in(
    client: TestClient, csrf_token: str
) -> None:
    assert get(client) == {
        "worker": {"state": "unknown", "started_at": None, "seen_at": None},
        "collectors": [],
    }


def test_it_reports_the_worker_and_each_collector(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    now = utcnow()
    session.add(WorkerBeat(name="collectors", started_at=now - timedelta(hours=2), beat_at=now))
    health_row(
        session,
        "wazuh",
        "manager",
        last_started_at=now - timedelta(seconds=2),
        last_finished_at=now,
        last_success_at=now,
        last_duration_ms=1800,
        last_items=4,
        next_run_at=now + timedelta(minutes=5),
    )
    health_row(
        session,
        "crowdsec",
        "lapi",
        consecutive_failures=2,
        last_error="CrowdSec refused the key.",
        last_finished_at=now,
        next_run_at=now + timedelta(minutes=1),
    )

    body = get(client)

    assert body["worker"]["state"] == "running"
    assert body["worker"]["seen_at"] is not None
    assert body["worker"]["started_at"] is not None
    crowdsec, wazuh = body["collectors"]
    assert (crowdsec["integration"], crowdsec["connection"]) == ("crowdsec", "lapi")
    assert crowdsec["source"] == "CrowdSec"
    assert crowdsec["collector"] == "connection-check"
    assert crowdsec["title"] == "Connection check"
    assert "Tests the connection" in crowdsec["summary"]
    assert crowdsec["state"] == "problem"
    assert crowdsec["last_error"] == "CrowdSec refused the key."
    assert crowdsec["consecutive_failures"] == 2
    assert wazuh["source"] == "Wazuh · Manager API"
    assert wazuh["state"] == "ok"
    assert (wazuh["last_duration_ms"], wazuh["last_items"], wazuh["interval_seconds"]) == (
        1800,
        4,
        300,
    )
    assert wazuh["last_error"] is None
    assert wazuh["next_run_at"] is not None


def test_it_can_be_narrowed_to_one_integration(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    health_row(session, "wazuh", "manager")
    health_row(session, "crowdsec", "lapi")

    only = get(client, integration="crowdsec")["collectors"]
    none = get(client, integration="opnsense")["collectors"]

    assert [(item["integration"], item["state"]) for item in only] == [("crowdsec", "waiting")]
    assert none == []


def test_a_name_that_cannot_be_an_integration_is_refused(
    client: TestClient, csrf_token: str
) -> None:
    response = client.get(BASE, params={"integration": "Not An Integration!"})

    assert response.status_code == 422


def test_what_the_product_no_longer_has_is_left_out(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    health_row(session, "crowdsec", "lapi", collector="no-longer-written")
    health_row(session, "dropped-from-the-product", "api")
    health_row(session, "crowdsec", "no-such-connection")
    health_row(session, "ntopng", "api")

    found = get(client)["collectors"]

    assert [(item["integration"], item["connection"]) for item in found] == [("ntopng", "api")]


def test_with_collecting_turned_off_nothing_is_reported_but_that_fact(
    app: FastAPI, client: TestClient, csrf_token: str, settings: Settings, session: Session
) -> None:
    app.dependency_overrides[get_settings] = lambda: settings.model_copy(
        update={"collectors_enabled": False}
    )
    health_row(session, "ntopng", "api")

    body = get(client)

    assert body["worker"]["state"] == "off"
    assert body["collectors"] == []
