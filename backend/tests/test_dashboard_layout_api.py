"""An account's layout of the dashboard, and the stream that tells an open dashboard when
something changed."""

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import dashboard_layout
from app.api import dashboard_layout as api
from app.config import Settings
from app.events.event import Severity
from app.events.store import record as record_events
from app.models import DashboardLayout, User, utcnow
from tests.helpers import OTHER_ORIGIN, new_event
from tests.test_dashboard import incident

BASE = "/api/dashboard"
LAYOUT = f"{BASE}/layout"


def headers(token: str) -> dict[str, str]:
    return {"X-CSRF-Token": token}


def whole(**changes: Any) -> dict[str, Any]:
    """A request to save: every widget once, as it starts, with what the test changes."""
    places = [
        {"id": place.id, "size": place.size, "hidden": place.hidden}
        for place in dashboard_layout.default_places()
    ]
    return {"preset": None, "widgets": places, **changes}


def test_it_is_only_for_someone_signed_in(client: TestClient, account: User) -> None:
    assert client.get(LAYOUT).status_code == 401
    assert client.put(LAYOUT, json=whole()).status_code == 401
    assert client.delete(LAYOUT).status_code == 401
    assert client.get(f"{BASE}/stream").status_code == 401


class TestReading:
    def test_an_account_that_never_changed_it_has_the_first_preset(
        self, client: TestClient, csrf_token: str
    ) -> None:
        body = client.get(LAYOUT).json()

        assert body["preset"] == "overview"
        assert [item["id"] for item in body["widgets"]] == [
            widget.id for widget in dashboard_layout.WIDGETS
        ]
        assert not any(item["hidden"] for item in body["widgets"])

    def test_it_offers_the_presets_to_start_from(self, client: TestClient, csrf_token: str) -> None:
        body = client.get(LAYOUT).json()

        assert [preset["key"] for preset in body["presets"]] == [
            "overview",
            "threat_watch",
            "compact",
        ]
        assert body["presets"][1]["title"] == "Threat watch"
        assert len(body["presets"][1]["widgets"]) == len(dashboard_layout.WIDGETS)
        assert body["presets"][0]["widgets"] == body["widgets"]


class TestSaving:
    def test_a_layout_is_kept_and_read_back(self, client: TestClient, csrf_token: str) -> None:
        widgets = whole()["widgets"]
        widgets.reverse()
        widgets[0]["hidden"] = True
        widgets[1]["size"] = "full"

        saved = client.put(
            LAYOUT, json=whole(preset="compact", widgets=widgets), headers=headers(csrf_token)
        )

        assert saved.status_code == 200
        assert saved.json()["preset"] == "compact"
        again = client.get(LAYOUT).json()
        assert again["preset"] == "compact"
        assert again["widgets"] == widgets

    def test_saving_again_changes_the_one_there_is(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        client.put(LAYOUT, json=whole(), headers=headers(csrf_token))
        client.put(LAYOUT, json=whole(preset="threat_watch"), headers=headers(csrf_token))

        session.expire_all()
        rows = session.query(DashboardLayout).all()
        assert [row.preset for row in rows] == ["threat_watch"]

    def test_a_widget_the_request_leaves_out_is_added_shown(
        self, client: TestClient, csrf_token: str
    ) -> None:
        saved = client.put(
            LAYOUT,
            json={"preset": None, "widgets": [{"id": "latest", "size": "full", "hidden": True}]},
            headers=headers(csrf_token),
        ).json()

        assert saved["widgets"][0] == {"id": "latest", "size": "full", "hidden": True}
        assert len(saved["widgets"]) == len(dashboard_layout.WIDGETS)
        assert not any(item["hidden"] for item in saved["widgets"][1:])

    @pytest.mark.parametrize(
        "changes",
        [
            {"widgets": [{"id": "latest", "size": "huge", "hidden": False}]},
            {"widgets": [{"id": "nothing", "size": "half", "hidden": False}]},
            {
                "widgets": [
                    {"id": "latest", "size": "half", "hidden": False},
                    {"id": "latest", "size": "half", "hidden": False},
                ]
            },
            {"preset": "mine"},
            {"widgets": "traffic"},
            {"widgets": [{"id": "latest", "size": "half"}]},
        ],
    )
    def test_what_is_not_a_layout_is_refused(
        self, client: TestClient, csrf_token: str, changes: dict[str, Any]
    ) -> None:
        response = client.put(LAYOUT, json=whole(**changes), headers=headers(csrf_token))

        assert response.status_code == 422
        assert client.get(LAYOUT).json()["preset"] == "overview"

    def test_a_change_from_another_website_is_refused(
        self, client: TestClient, csrf_token: str
    ) -> None:
        response = client.put(
            LAYOUT, json=whole(), headers={**headers(csrf_token), "Origin": OTHER_ORIGIN}
        )

        assert response.status_code == 403

    def test_a_change_without_the_security_token_is_refused(
        self, client: TestClient, csrf_token: str
    ) -> None:
        assert client.put(LAYOUT, json=whole()).status_code == 403


class TestResetting:
    def test_the_first_preset_comes_back(self, client: TestClient, csrf_token: str) -> None:
        widgets = whole()["widgets"]
        widgets[0]["hidden"] = True
        client.put(LAYOUT, json=whole(widgets=widgets), headers=headers(csrf_token))

        response = client.delete(LAYOUT, headers=headers(csrf_token))

        assert response.status_code == 204
        body = client.get(LAYOUT).json()
        assert body["preset"] == "overview"
        assert not any(item["hidden"] for item in body["widgets"])

    def test_there_is_nothing_to_do_for_an_account_that_never_changed_it(
        self, client: TestClient, csrf_token: str
    ) -> None:
        assert client.delete(LAYOUT, headers=headers(csrf_token)).status_code == 204


class TestWhatChanged:
    def test_it_differs_when_an_event_or_an_incident_comes(
        self, session: Session, account: User, settings: Settings
    ) -> None:
        now = utcnow()
        before = api.signature(session)
        record_events(session, settings, [new_event(severity=Severity.HIGH, occurred_at=now)], now)
        session.commit()
        after_event = api.signature(session)
        session.add(incident("10.0.0.5", now))
        session.commit()
        after_incident = api.signature(session)

        assert len({before, after_event, after_incident}) == 3
        assert api.signature(session) == after_incident


class FakeRequest:
    """A request whose client goes away after it has been asked this many times."""

    def __init__(self, asks_before_leaving: int | None = None) -> None:
        self.left = asks_before_leaving
        self.asked = 0

    async def is_disconnected(self) -> bool:
        self.asked += 1
        return self.left is not None and self.asked > self.left


@pytest.fixture
def quickly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api, "CHECK_SECONDS", 0.001)
    monkeypatch.setattr(api, "KEEP_ALIVE_SECONDS", 0.0)


def looking(monkeypatch: pytest.MonkeyPatch, *signatures: str) -> None:
    """What each look at the database finds, in turn, and the last one for ever after."""
    found = iter(signatures)
    last = signatures[-1]

    def look(_sessions: object) -> str:
        return next(found, last)

    monkeypatch.setattr(api, "_look", look)


def run_events(request: FakeRequest) -> list[str]:
    async def collect() -> list[str]:
        out: list[str] = []
        events: AsyncGenerator[str] = api._events(request, object())  # type: ignore[arg-type]
        async for item in events:
            out.append(item)
        return out

    return asyncio.run(collect())


class TestTheStream:
    def test_it_says_when_it_is_ready_and_when_something_changed(
        self, monkeypatch: pytest.MonkeyPatch, quickly: None
    ) -> None:
        looking(monkeypatch, "a", "a", "b", "b", "c")
        monkeypatch.setattr(api, "KEEP_ALIVE_SECONDS", 1000.0)

        sent = run_events(FakeRequest(asks_before_leaving=4))

        assert sent == [
            "event: ready\ndata: a\n\n",
            "event: changed\ndata: b\n\n",
            "event: changed\ndata: c\n\n",
        ]

    def test_a_quiet_stream_says_it_is_still_there(
        self, monkeypatch: pytest.MonkeyPatch, quickly: None
    ) -> None:
        looking(monkeypatch, "same")

        sent = run_events(FakeRequest(asks_before_leaving=2))

        assert sent == ["event: ready\ndata: same\n\n", ": still here\n\n", ": still here\n\n"]

    def test_it_ends_when_the_page_has_gone(
        self, monkeypatch: pytest.MonkeyPatch, quickly: None
    ) -> None:
        looking(monkeypatch, "same")

        sent = run_events(FakeRequest(asks_before_leaving=0))

        assert sent == ["event: ready\ndata: same\n\n"]

    def test_it_ends_after_its_time_so_the_page_connects_again(
        self, monkeypatch: pytest.MonkeyPatch, quickly: None
    ) -> None:
        looking(monkeypatch, "same")
        monkeypatch.setattr(api, "STREAM_SECONDS", 0.01)
        monkeypatch.setattr(api, "KEEP_ALIVE_SECONDS", 1000.0)

        sent = run_events(FakeRequest())

        assert sent == ["event: ready\ndata: same\n\n"]

    def test_it_is_sent_as_events_that_nothing_keeps(
        self, client: TestClient, csrf_token: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(api, "STREAM_SECONDS", 0.0)

        with client.stream("GET", f"{BASE}/stream") as response:
            body = "".join(response.iter_text())

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-accel-buffering"] == "no"
        assert body.startswith("event: ready\ndata: ")
