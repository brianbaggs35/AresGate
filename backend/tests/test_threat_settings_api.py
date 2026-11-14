"""Threat detection settings from the web app."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import Action, Outcome
from app.models import AuditEvent, ThreatSettings, User
from app.threats import calls
from tests.test_threats_overview import kind
from tests.test_threats_settings import ai

BASE = "/api/threat-settings"
EVERYTHING: dict[str, Any] = {
    "threat_from": 65,
    "ai_may_clear": True,
    "clear_from": 80,
    "ai_confirms": True,
    "exposure": "unknown",
    "exposed_ports": [],
    "notes": "",
    "important_drop": 10,
    "low_raise": 0,
    "ai_gives_verdicts": False,
}


def headers(token: str) -> dict[str, str]:
    return {"X-CSRF-Token": token}


def change(client: TestClient, token: str, **body: Any) -> Any:
    return client.put(BASE, json={**EVERYTHING, **body}, headers=headers(token))


def preview(client: TestClient, token: str, **body: Any) -> Any:
    return client.post(f"{BASE}/preview", json={**EVERYTHING, **body}, headers=headers(token))


def audited(session: Session) -> list[AuditEvent]:
    session.expire_all()
    return list(
        session.scalars(
            select(AuditEvent)
            .where(AuditEvent.action == Action.THREATS_SETTINGS_CHANGED.value)
            .order_by(AuditEvent.id)
        )
    )


def test_it_is_only_for_someone_signed_in(client: TestClient, account: User) -> None:
    answers = [
        client.get(BASE),
        client.put(BASE, json=EVERYTHING),
        client.post(f"{BASE}/preview", json=EVERYTHING),
    ]

    assert [answer.status_code for answer in answers] == [401, 401, 401]


class TestReadingThem:
    def test_an_install_that_never_saved_them_has_the_defaults(
        self, client: TestClient, csrf_token: str
    ) -> None:
        assert client.get(BASE).json() == {
            **EVERYTHING,
            "default_threat_from": 65,
            "default_clear_from": 80,
            "default_important_drop": 10,
            "default_low_raise": 0,
            "max_shift": 30,
            "min_clear_from": 50,
            "max_notes": 500,
            "max_ports": 20,
            "watching": False,
            "updated_at": None,
        }

    def test_it_says_when_an_ai_is_watching(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        ai(session)

        assert client.get(BASE).json()["watching"] is True


class TestChangingThem:
    def test_what_is_saved_is_what_is_read(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        asked = {
            "threat_from": 80,
            "ai_may_clear": False,
            "clear_from": 90,
            "ai_confirms": False,
            "exposure": "some",
            "exposed_ports": [443, 22, 443],
            "notes": "  A web   server in\nthe garage. ",
        }

        saved = change(client, csrf_token, **asked)

        assert saved.status_code == 200
        body = saved.json()
        assert {name: body[name] for name in asked} == {
            **asked,
            "exposed_ports": [22, 443],
            "notes": "A web server in the garage.",
        }
        assert body["updated_at"] is not None
        assert client.get(BASE).json() == body

    def test_a_change_is_recorded_without_the_owners_own_words(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        change(
            client,
            csrf_token,
            threat_from=80,
            clear_from=90,
            ai_may_clear=False,
            ai_confirms=False,
            exposure="some",
            exposed_ports=[22],
            notes="secret garage",
        )

        [event] = audited(session)
        assert event.outcome == Outcome.SUCCESS.value
        assert event.detail == {
            "threat_from": 80,
            "from_threat_from": 65,
            "clear_from": 90,
            "from_clear_from": 80,
            "ai_may_clear": False,
            "from_ai_may_clear": True,
            "ai_confirms": False,
            "from_ai_confirms": True,
            "exposure": "some",
            "from_exposure": "unknown",
            "exposed_ports": "22",
            "from_exposed_ports": "",
            "notes_changed": True,
        }
        assert "garage" not in str(event.detail)

    def test_how_far_importance_moves_the_bar_is_kept_and_recorded(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        saved = change(client, csrf_token, important_drop=20, low_raise=5)

        assert saved.status_code == 200
        assert (saved.json()["important_drop"], saved.json()["low_raise"]) == (20, 5)
        [event] = audited(session)
        assert event.detail == {
            "important_drop": 20,
            "from_important_drop": 10,
            "low_raise": 5,
            "from_low_raise": 0,
        }

    def test_letting_the_ai_clear_false_positives_is_off_until_the_owner_says_so(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        assert client.get(BASE).json()["ai_gives_verdicts"] is False

        saved = change(client, csrf_token, ai_gives_verdicts=True)

        assert saved.json()["ai_gives_verdicts"] is True
        assert client.get(BASE).json()["ai_gives_verdicts"] is True
        [event] = audited(session)
        assert event.detail == {"ai_gives_verdicts": True, "from_ai_gives_verdicts": False}

    def test_saving_what_is_saved_changes_and_records_nothing(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        change(client, csrf_token)
        change(client, csrf_token, threat_from=70)
        change(client, csrf_token, threat_from=70)

        assert len(audited(session)) == 1
        assert session.get(ThreatSettings, 1) is not None

    @pytest.mark.parametrize(
        "body",
        [
            {"threat_from": 0},
            {"threat_from": 101},
            {"clear_from": 49},
            {"clear_from": 101},
            {"exposure": "everything"},
            {"exposed_ports": [0]},
            {"exposed_ports": [65536]},
            {"exposed_ports": list(range(1, 22))},
            {"notes": "x" * 501},
            {"important_drop": -1},
            {"important_drop": 31},
            {"low_raise": 31},
            {"unknown": 1},
        ],
    )
    def test_what_makes_no_sense_is_refused(
        self, client: TestClient, csrf_token: str, body: dict[str, Any]
    ) -> None:
        assert change(client, csrf_token, **body).status_code == 422

    def test_it_needs_the_token_a_browser_sends(self, client: TestClient, csrf_token: str) -> None:
        assert client.put(BASE, json=EVERYTHING).status_code == 403


class TestPreviewingThem:
    def made(self, session: Session) -> None:
        kind(session, 1, "ET SCAN a", confidence=90)
        kind(session, 1, "ET SCAN b", confidence=50)
        kind(session, 1, "ET SCAN c", confidence=10)
        judged = kind(session, 1, "ET SCAN d", confidence=90)
        judged.ai_class = "probe"
        judged.ai_confidence = 85
        session.flush()
        calls.sync(session, family_id=judged.id)
        session.commit()
        kind(session, 1, "ET SCAN e", confidence=90, verdict="low_priority")

    def test_it_says_where_the_incidents_stand_now_and_where_they_would(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        self.made(session)

        body = preview(client, csrf_token, threat_from=95, ai_may_clear=False).json()

        assert body["now"] == {
            "threats": 1,
            "suspects": 1,
            "background": 2,
            "cleared": 1,
            "muted": 1,
        }
        assert body["after"] == {
            "threats": 0,
            "suspects": 3,
            "background": 1,
            "cleared": 0,
            "muted": 1,
        }

    def test_it_says_what_importance_would_move(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        kind(session, 1, "ET SCAN guest", confidence=40, importance=-1)
        kind(session, 1, "ET SCAN nas", confidence=30, importance=2)

        body = preview(client, csrf_token, important_drop=10, low_raise=10).json()

        assert (body["now"]["suspects"], body["now"]["background"]) == (2, 0)
        assert (body["after"]["suspects"], body["after"]["background"]) == (1, 1)
        wide = preview(client, csrf_token, important_drop=0, low_raise=30).json()["after"]
        assert (wide["suspects"], wide["background"]) == (0, 2)

    def test_it_changes_nothing(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        self.made(session)

        preview(client, csrf_token, threat_from=95)

        assert session.get(ThreatSettings, 1) is None
        assert audited(session) == []

    def test_the_ai_agreeing_is_counted_only_while_an_ai_is_watching(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        self.made(session)

        quiet = preview(client, csrf_token, ai_confirms=True).json()["after"]
        ai(session)
        watched = preview(client, csrf_token, ai_confirms=True).json()
        unconfirmed = preview(client, csrf_token, ai_confirms=False).json()["after"]

        assert quiet["threats"] == 1
        assert watched["now"]["threats"] == 0
        assert watched["after"]["threats"] == 0
        assert unconfirmed["threats"] == 1

    def test_it_needs_the_token_a_browser_sends(self, client: TestClient, csrf_token: str) -> None:
        assert client.post(f"{BASE}/preview", json=EVERYTHING).status_code == 403
