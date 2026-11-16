"""The review queue's API: what the AI cleared and what it suggests clearing, and confirming or
taking back, one at a time or many."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import clearing, review_queue
from app.ai.clearing_settings import Policy
from app.audit import Action
from app.config import Settings
from app.models import (
    AiClearVeto,
    AiTriage,
    AuditEvent,
    Incident,
    IncidentSignal,
    User,
    VerdictRule,
)
from app.threats.settings import Tuning
from tests.test_ai_clearing import ON, read, scan
from tests.test_ai_review_queue import another, suggested
from tests.test_incidents_engine import NOW

BASE = "/api/ai/cleared"


def headers(token: str) -> dict[str, str]:
    return {"X-CSRF-Token": token}


def post(client: TestClient, token: str, path: str, *items: tuple[str, int], **more: Any) -> Any:
    body = {"items": [{"kind": kind, "id": key} for kind, key in items], **more}
    return client.post(f"{BASE}/{path}", json=body, headers=headers(token))


def audited(session: Session, action: Action) -> list[AuditEvent]:
    session.expire_all()
    return list(
        session.scalars(
            select(AuditEvent).where(AuditEvent.action == action.value).order_by(AuditEvent.id)
        )
    )


def detail(event: AuditEvent) -> dict[str, str | int | bool]:
    assert event.detail is not None
    return event.detail


def cleared(session: Session, settings: Settings) -> VerdictRule:
    """A verdict the AI gave itself."""
    found = scan(session, settings)
    reading = read(found)
    session.add(reading)
    session.flush()
    rule = clearing.clear(session, found, reading, Tuning(), NOW, ON)
    session.commit()
    assert rule is not None
    return rule


def test_it_is_only_for_someone_signed_in(client: TestClient, account: User) -> None:
    for method, path in (
        ("get", BASE),
        ("get", f"{BASE}/summary"),
        ("post", f"{BASE}/confirm"),
        ("post", f"{BASE}/take-back"),
    ):
        assert client.request(method, path).status_code == 401, (method, path)


class TestTheQueue:
    def test_nothing_is_waiting_or_cleared_on_a_new_install(
        self, client: TestClient, csrf_token: str
    ) -> None:
        body = client.get(BASE).json()

        assert body["counts"] == {"waiting": 0, "cleared": 0}
        assert (body["state"], body["items"], body["mode"], body["held"]) == (
            "waiting",
            [],
            "suggest",
            None,
        )

    def test_a_suggestion_says_why_how_sure_and_what_the_ai_read(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        found = suggested(session, settings, observations=["Port 22 only"], checks=["Is it known"])
        session.commit()

        body = client.get(BASE).json()

        assert body["counts"] == {"waiting": 1, "cleared": 0}
        (item,) = body["items"]
        assert (item["kind"], item["id"], item["verdict"]) == (
            "waiting",
            found.id,
            "not_suspicious",
        )
        assert item["reason"] == "It is the scanner the owner runs."
        assert (item["confidence"], item["classification"]) == (91, "noise")
        assert (item["provider"], item["model"]) == ("anthropic", "claude-haiku-5-5")
        assert (item["story"], item["checks"], item["observations"]) == (
            "It tried a port.",
            ["Is it known"],
            ["Port 22 only"],
        )
        assert item["incident"]["id"] == found.id
        assert item["incident"]["severity"] == "medium"

    def test_a_clearing_says_what_the_ai_said_when_it_gave_it(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        rule = cleared(session, settings)

        body = client.get(BASE, params={"state": "cleared"}).json()

        assert body["counts"] == {"waiting": 0, "cleared": 1}
        (item,) = body["items"]
        assert (item["kind"], item["id"], item["confidence"]) == ("cleared", rule.id, 91)
        assert item["reason"] == "It is the scanner the owner runs."
        assert item["story"] == "It tried a port."

    def test_a_clearing_whose_incident_is_gone_is_still_there(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        session.add(
            VerdictRule(
                verdict="low_priority",
                source="wazuh",
                signature="x",
                given_by="ai",
                ai_confidence=88,
            )
        )
        session.commit()

        (item,) = client.get(BASE, params={"state": "cleared"}).json()["items"]

        assert (item["incident"], item["story"], item["checks"]) == (None, None, [])

    def test_it_pages(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        suggested(session, settings)
        another_one = another(session, settings)
        session.add(read(another_one))
        session.commit()

        first = client.get(BASE, params={"limit": 1}).json()
        second = client.get(BASE, params={"limit": 1, "offset": 1}).json()

        assert (first["total"], len(first["items"]), len(second["items"])) == (2, 1, 1)
        assert first["items"][0]["id"] != second["items"][0]["id"]

    def test_it_says_why_the_ai_is_not_clearing_by_itself(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        client.put(
            "/api/ai/clearing",
            json={
                "mode": "automatic",
                "minimum": 80,
                "kinds": ["noise"],
                "sources": [],
                "ceiling": "medium",
                "daily_cap": 0,
            },
            headers=headers(csrf_token),
        )

        body = client.get(BASE).json()

        assert body["mode"] == "automatic"
        assert "most it is allowed" in body["held"]

    def test_the_summary_is_what_the_banner_says(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        suggested(session, settings)
        session.commit()

        assert client.get(f"{BASE}/summary").json() == {"waiting": 1, "cleared": 0}


class TestConfirming:
    def test_what_the_ai_cleared_becomes_the_owners(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        rule = cleared(session, settings)
        incident_id = rule.ai_incident_id

        done = post(client, csrf_token, "confirm", ("cleared", rule.id)).json()

        assert (done["done"], done["skipped"], done["counts"]["cleared"]) == (1, 0, 0)
        session.expire_all()
        assert session.get_one(VerdictRule, rule.id).given_by == "owner"
        [event] = audited(session, Action.AI_CLEAR_CONFIRMED)
        assert (event.username, detail(event)["incident_id"]) == ("brian", incident_id)

    def test_a_suggestion_is_given_as_the_owners_verdict_and_applied(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        found = suggested(session, settings)
        session.commit()

        done = post(client, csrf_token, "confirm", ("waiting", found.id)).json()

        assert (done["done"], done["counts"]["waiting"]) == (1, 0)
        session.expire_all()
        rule = session.scalars(select(VerdictRule)).one()
        assert (rule.given_by, rule.verdict) == ("owner", "not_suspicious")
        assert session.get_one(Incident, found.id).verdict == "not_suspicious"
        [event] = audited(session, Action.AI_SUGGESTION_CONFIRMED)
        assert detail(event)["incident_id"] == found.id

    def test_a_suggestion_can_be_confirmed_as_low_priority(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        found = suggested(session, settings)
        session.commit()

        post(client, csrf_token, "confirm", ("waiting", found.id), verdict="low_priority")

        assert session.scalars(select(VerdictRule)).one().verdict == "low_priority"

    def test_many_at_once_and_what_is_no_longer_there_is_skipped(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        rule = cleared(session, settings)
        waiting = another(session, settings)
        session.add(read(waiting))
        session.commit()

        done = post(
            client,
            csrf_token,
            "confirm",
            ("cleared", rule.id),
            ("waiting", waiting.id),
            ("cleared", 999_999),
            ("waiting", 999_999),
        ).json()

        assert (done["done"], done["skipped"]) == (2, 2)
        assert done["counts"] == {"waiting": 0, "cleared": 0}

    def test_an_incident_the_owner_has_a_verdict_on_is_skipped(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        found = suggested(session, settings)
        found.verdict = "threat"
        session.commit()

        assert post(client, csrf_token, "confirm", ("waiting", found.id)).json()["skipped"] == 1

    def test_a_suggestion_the_owner_already_has_a_verdict_for_is_skipped(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        found = suggested(session, settings)
        match = clearing.match_of(session, found)
        assert match is not None
        session.add(
            VerdictRule(
                verdict="threat",
                address=match.address,
                source=match.source,
                signature=match.signature,
            )
        )
        session.commit()

        done = post(client, csrf_token, "confirm", ("waiting", found.id)).json()

        assert (done["done"], done["skipped"]) == (0, 1)
        assert audited(session, Action.AI_SUGGESTION_CONFIRMED) == []

    def test_a_clearing_that_is_the_owners_already_is_skipped(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        rule = VerdictRule(verdict="threat", source="wazuh", signature="x")
        session.add(rule)
        session.commit()

        assert post(client, csrf_token, "confirm", ("cleared", rule.id)).json()["done"] == 0

    def test_it_needs_something_to_do_and_not_too_much(
        self, client: TestClient, csrf_token: str
    ) -> None:
        assert post(client, csrf_token, "confirm").status_code == 422
        too_many = [("waiting", key) for key in range(1, 102)]
        assert post(client, csrf_token, "confirm", *too_many).status_code == 422
        assert post(client, csrf_token, "confirm", ("nothing", 1)).status_code == 422
        assert post(client, csrf_token, "confirm", ("waiting", 0)).status_code == 422
        assert (
            post(client, csrf_token, "confirm", ("waiting", 1), verdict="threat").status_code == 422
        )


class TestTakingBack:
    def test_what_the_ai_cleared_is_taken_back_and_the_ai_is_told_not_to_again(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        rule = cleared(session, settings)

        done = post(client, csrf_token, "take-back", ("cleared", rule.id)).json()

        assert (done["done"], done["counts"]["cleared"]) == (1, 0)
        session.expire_all()
        assert session.scalars(select(VerdictRule)).all() == []
        assert len(session.scalars(select(AiClearVeto)).all()) == 1
        [event] = audited(session, Action.VERDICT_TAKEN_BACK_FROM_AI)
        assert detail(event)["incident_id"] == rule.ai_incident_id
        assert event.username == "brian"

    def test_a_suggestion_is_turned_down_and_not_made_again(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        found = suggested(session, settings)
        session.commit()

        done = post(client, csrf_token, "take-back", ("waiting", found.id)).json()

        assert (done["done"], done["counts"]["waiting"]) == (1, 0)
        assert len(session.scalars(select(AiClearVeto)).all()) == 1
        [event] = audited(session, Action.AI_SUGGESTION_DISMISSED)
        assert detail(event)["incident_id"] == found.id
        assert client.get(BASE).json()["items"] == []

    def test_many_at_once_and_what_is_not_the_ais_is_skipped(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        rule = cleared(session, settings)
        mine = VerdictRule(verdict="threat", source="wazuh", signature="x")
        session.add(mine)
        session.commit()

        done = post(
            client,
            csrf_token,
            "take-back",
            ("cleared", rule.id),
            ("cleared", mine.id),
            ("waiting", 999_999),
        ).json()

        assert (done["done"], done["skipped"]) == (1, 2)
        assert session.get(VerdictRule, mine.id) is not None

    def test_a_suggestion_with_no_signature_cannot_be_turned_down(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        found = suggested(session, settings)
        for signal in session.scalars(select(IncidentSignal)):
            signal.signature = None
        session.commit()

        assert post(client, csrf_token, "take-back", ("waiting", found.id)).json()["skipped"] == 1


class TestWhereItShows:
    def test_the_dashboard_says_what_the_ai_cleared(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        rule = cleared(session, settings)

        body = client.get("/api/dashboard").json()

        assert rule.id
        assert body["ai_review"] == {"waiting": 0, "cleared": 1}

    def test_the_incident_says_what_happened_to_it(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        rule = cleared(session, settings)
        # The AI giving it is recorded as the AI giving it, with no account behind it.
        incident_id = rule.ai_incident_id
        post(client, csrf_token, "take-back", ("cleared", rule.id))

        trail = client.get(f"/api/incidents/{incident_id}").json()["clearing_trail"]

        assert [(step["action"], step["by"]) for step in trail] == [
            ("cleared", "the AI"),
            ("taken_back", "brian"),
        ]
        assert (trail[0]["verdict"], trail[0]["confidence"]) == ("not_suspicious", 91)

    def test_the_trail_is_empty_where_the_ai_did_nothing(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        found = scan(session, settings)

        assert client.get(f"/api/incidents/{found.id}").json()["clearing_trail"] == []


def test_the_suggestions_of_an_install_that_is_off_are_none(
    client: TestClient, csrf_token: str, session: Session, settings: Settings
) -> None:
    suggested(session, settings)
    session.commit()
    client.put(
        "/api/ai/clearing",
        json={
            "mode": "off",
            "minimum": 80,
            "kinds": ["noise", "probe", "unclear"],
            "sources": [],
            "ceiling": "medium",
            "daily_cap": 25,
        },
        headers=headers(csrf_token),
    )

    assert client.get(BASE).json()["counts"]["waiting"] == 0
    assert review_queue.waiting(session, Policy(mode="off"), Tuning()) == []
    assert session.scalars(select(AiTriage)).one().verdict == "not_suspicious"
