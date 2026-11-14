from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import Settings
from app.events.event import Severity
from app.incidents import respond
from app.models import User
from tests.test_incidents_engine import ATTACKER, NOW, OTHER_ATTACKER, alert, run, store
from tests.test_incidents_response import MINUTE, connect, decision, turned_away

BASE = "/api/incident-response"


def ask(client: TestClient, days: int = 7) -> dict[str, Any]:
    response = client.get(BASE, params={"days": days})
    assert response.status_code == 200
    return dict(response.json())


def test_it_is_only_for_someone_signed_in(client: TestClient, account: User) -> None:
    assert client.get(BASE).status_code == 401


def test_the_days_have_limits(client: TestClient, csrf_token: str) -> None:
    assert client.get(BASE, params={"days": 0}).status_code == 422
    assert client.get(BASE, params={"days": max(respond.DAYS) + 1}).status_code == 422
    assert client.get(BASE, params={"days": "week"}).status_code == 422


def test_with_nothing_going_on_every_group_is_there_and_empty(
    client: TestClient, csrf_token: str
) -> None:
    body = client.get(BASE).json()

    assert body["days"] == 7
    assert (body["minimum"], body["total"], body["shown"]) == ("medium", 0, 0)
    assert (body["crowdsec_connected"], body["opnsense_connected"]) == (False, False)
    assert [(group["key"], group["label"], group["items"]) for group in body["groups"]] == [
        (key, label, []) for key, (label, _) in respond.GROUPS.items()
    ]
    assert all(group["description"] for group in body["groups"])


def test_each_incident_is_in_the_group_that_says_what_was_done(
    client: TestClient,
    csrf_token: str,
    session: Session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = NOW + timedelta(hours=1)
    monkeypatch.setattr(respond, "utcnow", lambda: clock)
    connect(session, "crowdsec")
    store(
        session,
        settings,
        alert(NOW, severity=Severity.HIGH),
        alert(NOW, n=2, src_address=OTHER_ATTACKER),
        decision(NOW + 2 * MINUTE, duration="4h"),
        turned_away(NOW + MINUTE, 7, address=OTHER_ATTACKER),
    )
    run(session)

    body = ask(client)

    groups = {group["key"]: group for group in body["groups"]}
    assert (body["total"], body["shown"]) == (2, 2)
    assert body["crowdsec_connected"] is True
    assert body["opnsense_connected"] is False
    (banned,) = groups["banned"]["items"]
    assert banned["subject"] == ATTACKER
    assert (banned["state"], banned["label"], banned["severity"]) == ("banned", "Banned", "high")
    assert (banned["banned_now"], banned["attackers"], banned["status"]) == (1, 1, "open")
    assert banned["ban_ends_at"].startswith("2026-10-26T10:02:00")
    assert banned["why"] is None
    (blocked,) = groups["blocked"]["items"]
    assert blocked["subject"] == OTHER_ATTACKER
    assert (blocked["blocked"], blocked["dropped"]) == (1, 0)
    assert groups["needs_response"]["items"] == []
