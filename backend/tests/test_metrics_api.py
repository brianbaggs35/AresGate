from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import Action, Outcome
from app.config import Settings
from app.metrics.store import record
from app.models import AuditEvent, MetricRetention, User, utcnow
from tests.helpers import OTHER_ORIGIN, new_sample

BASE = "/api/metrics/storage"


def headers(token: str) -> dict[str, str]:
    return {"X-CSRF-Token": token}


def source(client: TestClient, key: str) -> dict[str, object]:
    [found] = [item for item in client.get(BASE).json()["sources"] if item["source"] == key]
    return found


def test_it_is_only_for_someone_signed_in(client: TestClient, account: User) -> None:
    assert client.get(BASE).status_code == 401
    assert client.put(f"{BASE}/opnsense", json={"days": 7}).status_code == 401


def test_a_change_needs_the_security_token_and_an_origin_from_the_app(
    client: TestClient, csrf_token: str
) -> None:
    without = client.put(f"{BASE}/opnsense", json={"days": 7})
    foreign = client.put(
        f"{BASE}/opnsense",
        json={"days": 7},
        headers={**headers(csrf_token), "Origin": OTHER_ORIGIN},
    )

    assert without.status_code == 403
    assert foreign.status_code == 403


def test_every_integration_is_listed_with_how_long_it_keeps_samples(
    client: TestClient, csrf_token: str, settings: Settings
) -> None:
    response = client.get(BASE)

    assert response.status_code == 200
    body = response.json()
    assert body["default_days"] == settings.metric_retention_days
    assert [item["source"] for item in body["sources"]] == [
        "opnsense",
        "ntopng",
        "wazuh",
        "crowdsec",
    ]
    assert body["sources"][0] == {
        "source": "opnsense",
        "name": "OPNsense",
        "days": None,
        "effective_days": settings.metric_retention_days,
        "samples": 0,
        "oldest_at": None,
    }


def test_it_says_how_many_samples_there_are_and_how_old_the_oldest_is(
    client: TestClient, csrf_token: str, session: Session, settings: Settings
) -> None:
    now = utcnow()
    oldest = now - timedelta(days=4)
    record(
        session,
        settings,
        [
            new_sample(sampled_at=oldest),
            new_sample(sampled_at=now),
            new_sample(sampled_at=now, name="system.load_5m"),
        ],
        now,
    )
    session.commit()

    found = source(client, "opnsense")

    assert found["samples"] == 3
    assert found["oldest_at"] == oldest.isoformat().replace("+00:00", "Z")
    assert source(client, "ntopng")["samples"] == 0


def test_how_long_samples_are_kept_can_be_set_for_an_integration(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    response = client.put(f"{BASE}/opnsense", json={"days": 90}, headers=headers(csrf_token))

    assert response.status_code == 200
    assert response.json() == {
        "source": "opnsense",
        "name": "OPNsense",
        "days": 90,
        "effective_days": 90,
        "samples": 0,
        "oldest_at": None,
    }
    assert source(client, "opnsense")["days"] == 90
    assert source(client, "ntopng")["days"] is None
    session.expire_all()
    assert session.get(MetricRetention, "opnsense") is not None


def test_it_goes_back_to_the_default(
    client: TestClient, csrf_token: str, settings: Settings
) -> None:
    client.put(f"{BASE}/opnsense", json={"days": 90}, headers=headers(csrf_token))

    response = client.put(f"{BASE}/opnsense", json={"days": None}, headers=headers(csrf_token))

    assert response.status_code == 200
    assert response.json()["days"] is None
    assert response.json()["effective_days"] == settings.metric_retention_days


def test_it_is_kept_apart_from_how_long_events_are_kept(
    client: TestClient, csrf_token: str
) -> None:
    client.put(f"{BASE}/opnsense", json={"days": 90}, headers=headers(csrf_token))

    events = client.get("/api/events/storage").json()["sources"][0]

    assert events["source"] == "opnsense"
    assert events["days"] is None


def test_the_change_is_in_the_audit_log(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    client.put(f"{BASE}/opnsense", json={"days": 90}, headers=headers(csrf_token))
    client.put(f"{BASE}/opnsense", json={"days": None}, headers=headers(csrf_token))

    session.expire_all()
    events = session.scalars(
        select(AuditEvent).where(AuditEvent.action == Action.METRIC_RETENTION_CHANGED)
    ).all()
    assert [(event.outcome, event.detail) for event in events] == [
        (Outcome.SUCCESS, {"source": "opnsense", "days": 90}),
        (Outcome.SUCCESS, {"source": "opnsense", "days": "default"}),
    ]
    assert all(event.username == "brian" for event in events)


@pytest.mark.parametrize("days", [0, -5, 3651, "a week", 1.5, True])
def test_a_period_out_of_range_is_refused(
    client: TestClient, csrf_token: str, days: object
) -> None:
    response = client.put(f"{BASE}/opnsense", json={"days": days}, headers=headers(csrf_token))

    assert response.status_code == 422
    assert source(client, "opnsense")["days"] is None


@pytest.mark.parametrize("body", [{}, {"days": 7, "source": "x"}])
def test_the_body_is_exactly_the_period(
    client: TestClient, csrf_token: str, body: dict[str, object]
) -> None:
    response = client.put(f"{BASE}/opnsense", json=body, headers=headers(csrf_token))

    assert response.status_code == 422


@pytest.mark.parametrize("key", ["nothing", "opnsense-x"])
def test_an_integration_that_does_not_exist_is_not_found(
    client: TestClient, csrf_token: str, key: str
) -> None:
    response = client.put(f"{BASE}/{key}", json={"days": 7}, headers=headers(csrf_token))

    assert response.status_code == 404
    assert response.json() == {"detail": "There's no such integration."}


def test_a_name_that_is_not_a_key_is_refused(client: TestClient, csrf_token: str) -> None:
    response = client.put(f"{BASE}/Not%20A%20Key", json={"days": 7}, headers=headers(csrf_token))

    assert response.status_code == 422
