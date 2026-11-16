"""Settings > AI > Clearing: what the owner lets the AI clear, saved, audited and previewed."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import Action
from app.config import Settings
from app.models import AuditEvent, User, utcnow
from tests.test_ai_clearing import read, scan

BASE = "/api/ai/clearing"
EVERYTHING: dict[str, Any] = {
    "mode": "suggest",
    "minimum": 80,
    "kinds": ["noise", "probe", "unclear"],
    "sources": [],
    "ceiling": "medium",
    "daily_cap": 25,
}


def headers(token: str) -> dict[str, str]:
    return {"X-CSRF-Token": token}


def change(client: TestClient, token: str, **body: Any) -> Any:
    return client.put(BASE, json={**EVERYTHING, **body}, headers=headers(token))


def audited(session: Session) -> list[AuditEvent]:
    session.expire_all()
    return list(
        session.scalars(
            select(AuditEvent)
            .where(AuditEvent.action == Action.AI_CLEARING_CHANGED.value)
            .order_by(AuditEvent.id)
        )
    )


def test_it_is_only_for_someone_signed_in(client: TestClient, account: User) -> None:
    for method, path in (("get", BASE), ("put", BASE), ("post", f"{BASE}/preview")):
        assert client.request(method, path).status_code == 401, (method, path)


class TestTheSettings:
    def test_until_the_owner_saves_they_are_the_defaults(
        self, client: TestClient, csrf_token: str
    ) -> None:
        body = client.get(BASE).json()

        assert {name: body[name] for name in EVERYTHING} == EVERYTHING
        assert body["aggressiveness"] == "balanced"
        assert body["updated_at"] is None
        assert body["cleared_today"] == 0
        assert body["held"] is None
        assert (body["min_minimum"], body["max_minimum"], body["max_cap"]) == (50, 99, 500)

    def test_it_offers_three_ways_to_be_careful_and_the_programs_it_can_be_limited_to(
        self, client: TestClient, csrf_token: str
    ) -> None:
        body = client.get(BASE).json()

        assert [(item["key"], item["minimum"]) for item in body["presets"]] == [
            ("careful", 90),
            ("balanced", 80),
            ("thorough", 65),
        ]
        sources = {item["key"]: item["name"] for item in body["available_sources"]}
        assert sources["ntopng"] == "ntopng"
        assert sources["wazuh"] == "Wazuh"
        assert sources["baseline"] == "Learned baselines"

    def test_it_is_kept_and_the_change_is_recorded(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        saved = change(
            client,
            csrf_token,
            mode="automatic",
            minimum=90,
            kinds=["noise"],
            sources=["wazuh", "ntopng", "wazuh"],
            ceiling="high",
            daily_cap=5,
        )

        assert saved.status_code == 200
        body = client.get(BASE).json()
        assert (body["mode"], body["aggressiveness"], body["minimum"]) == (
            "automatic",
            "careful",
            90,
        )
        assert (body["kinds"], body["sources"]) == (["noise"], ["ntopng", "wazuh"])
        assert (body["ceiling"], body["daily_cap"]) == ("high", 5)
        assert body["updated_at"] is not None
        [event] = audited(session)
        assert event.detail == {
            "mode": "automatic",
            "from_mode": "suggest",
            "minimum": 90,
            "from_minimum": 80,
            "ceiling": "high",
            "from_ceiling": "medium",
            "daily_cap": 5,
            "from_daily_cap": 25,
            "kinds": "noise",
            "from_kinds": "noise,probe,unclear",
            "sources": "ntopng,wazuh",
            "from_sources": "any",
        }

    def test_a_number_of_its_own_is_custom(self, client: TestClient, csrf_token: str) -> None:
        change(client, csrf_token, minimum=73)

        assert client.get(BASE).json()["aggressiveness"] == "custom"

    def test_saving_what_is_saved_records_nothing(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        change(client, csrf_token, daily_cap=3)
        change(client, csrf_token, daily_cap=3)

        assert len(audited(session)) == 1

    def test_it_says_when_it_has_stopped_clearing(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        change(client, csrf_token, mode="automatic", daily_cap=0)

        assert "most it is allowed" in client.get(BASE).json()["held"]

    def test_it_will_not_take_what_makes_no_sense(
        self, client: TestClient, csrf_token: str
    ) -> None:
        for bad in (
            {"mode": "always"},
            {"minimum": 49},
            {"minimum": 100},
            {"kinds": ["attack"]},
            {"kinds": ["noise", "noise", "probe", "unclear"]},
            {"sources": ["nothing-like-it"]},
            {"ceiling": "critical"},
            {"daily_cap": -1},
            {"daily_cap": 501},
            {"also": "this"},
        ):
            assert change(client, csrf_token, **bad).status_code == 422, bad

    def test_it_can_be_made_to_clear_nothing(self, client: TestClient, csrf_token: str) -> None:
        saved = change(client, csrf_token, mode="off", kinds=[])

        assert saved.status_code == 200
        assert saved.json()["kinds"] == []


class TestThePreview:
    def test_it_says_how_many_of_the_incidents_the_ai_read_it_would_have_cleared(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        found = scan(session, settings)
        session.add(read(found))
        session.commit()
        found.last_seen_at = utcnow()
        session.commit()
        ask = {**EVERYTHING, "mode": "automatic"}

        same = client.post(f"{BASE}/preview", json=ask, headers=headers(csrf_token)).json()
        stricter = client.post(
            f"{BASE}/preview", json={**ask, "minimum": 95}, headers=headers(csrf_token)
        ).json()

        assert same == {"days": 7, "read": 1, "would_clear": 1}
        assert stricter == {"days": 7, "read": 1, "would_clear": 0}

    def test_it_changes_nothing(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        client.post(
            f"{BASE}/preview",
            json={**EVERYTHING, "mode": "automatic"},
            headers=headers(csrf_token),
        )

        assert client.get(BASE).json()["mode"] == "suggest"
        assert audited(session) == []
