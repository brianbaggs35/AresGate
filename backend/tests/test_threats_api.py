"""Threats from the web app: the funnel, the kinds of incident, and what the owner and an AI make of
each kind."""

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import Action, Outcome
from app.config import Settings
from app.models import AuditEvent, Incident, IncidentFamily, User, utcnow
from app.review import settings as review_settings
from e2e import factories
from tests.stubs import Serve
from tests.test_ai_families import judges
from tests.test_ai_triage import ready
from tests.test_threats_overview import kind

BASE = "/api/threats"


def headers(token: str) -> dict[str, str]:
    return {"X-CSRF-Token": token}


def audited(session: Session, action: Action) -> list[AuditEvent]:
    session.expire_all()
    return list(
        session.scalars(
            select(AuditEvent).where(AuditEvent.action == action.value).order_by(AuditEvent.id)
        )
    )


def test_it_is_only_for_someone_signed_in(client: TestClient, account: User) -> None:
    answers = [
        client.get(f"{BASE}/overview"),
        client.get(f"{BASE}/families"),
        client.get(f"{BASE}/families/1"),
        client.put(f"{BASE}/families/1/call", json={"call": None}),
        client.post(f"{BASE}/families/1/judge"),
    ]

    assert [answer.status_code for answer in answers] == [401] * 5


class TestTheOverview:
    def test_a_quiet_install_has_nothing(self, client: TestClient, csrf_token: str) -> None:
        body = client.get(f"{BASE}/overview").json()

        assert body["window"]["key"] == "24h"
        assert len(body["window"]["buckets"]) == 24
        assert body["funnel"] == {
            "reports": 0,
            "duplicates": 0,
            "repeats": 0,
            "alerts": 0,
            "incidents": 0,
            "families": 0,
            "threats": 0,
            "suspects": 0,
            "background": 0,
            "muted": 0,
            "handled": 0,
        }
        assert body["coverage"] == {"families": 0, "judged": 0, "owned": 0, "waiting": 0}
        assert body["watching"] is False
        assert body["threat_from"] == 65
        assert body["families"] == []

    def test_it_tells_what_the_reports_came_to(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        factories.incidents(
            session,
            settings,
            utcnow(),
            [
                factories.IncidentSpec(
                    address="93.184.216.34", scan=True, signals=4, twin="opnsense"
                ),
                factories.IncidentSpec(address="8.8.8.8", exploit=True, compromise=True),
            ],
        )
        session.commit()

        body = client.get(f"{BASE}/overview", params={"window": "7d"}).json()

        assert body["window"]["key"] == "7d"
        assert body["funnel"]["reports"] == 8 + 3
        assert body["funnel"]["duplicates"] == 4
        assert body["funnel"]["incidents"] == 2
        assert body["funnel"]["threats"] >= 1
        assert body["coverage"]["waiting"] == body["coverage"]["families"] == 2
        assert [item["incidents"] for item in body["families"]] == [1, 1]

    def test_the_window_has_to_be_one_it_knows(self, client: TestClient, csrf_token: str) -> None:
        assert client.get(f"{BASE}/overview", params={"window": "1y"}).status_code == 422


class TestListingTheKinds:
    def made(self, session: Session) -> dict[str, IncidentFamily]:
        return {
            "threat": kind(session, 1, "ET EXPLOIT threat", confidence=90),
            "big": kind(session, 3, "ET SCAN big", confidence=50),
            "small": kind(session, 2, "ET SCAN small", confidence=10),
        }

    def test_they_are_listed_with_what_is_thought_of_each(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        made = self.made(session)
        small = made["small"]
        small.ai_class = "probe"
        small.ai_confidence = 92
        small.ai_reason = "Scanners."
        small.judged_at = utcnow()
        small.owner_call = "background"
        session.commit()

        body = client.get(f"{BASE}/families").json()

        assert body["total"] == 3
        assert [item["label"] for item in body["items"]] == [
            "ET EXPLOIT threat from <address>",
            "ET SCAN big from <address>",
            "ET SCAN small from <address>",
        ]
        last = body["items"][2]
        assert last["classification"] == "probe"
        assert (last["confidence"], last["reason"], last["owner_call"]) == (
            92,
            "Scanners.",
            "background",
        )
        assert last["reach"] == "internet"
        assert (last["incidents"], last["alerts"], last["actors"]) == (2, 6, 2)
        assert (last["threats"], last["suspects"], last["background"]) == (0, 0, 2)
        assert last["worst"] == "medium"
        assert last["source_name"] == "OPNsense"

    def test_they_can_be_narrowed_and_paged(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        self.made(session)

        def labels(**params: Any) -> list[str]:
            return [
                item["label"]
                for item in client.get(f"{BASE}/families", params=params).json()["items"]
            ]

        assert labels(lane="threat") == ["ET EXPLOIT threat from <address>"]
        assert labels(lane="suspect") == ["ET SCAN big from <address>"]
        assert labels(lane="background") == ["ET SCAN small from <address>"]
        assert len(labels(judged="waiting")) == 3
        assert labels(judged="ai") == []
        assert labels(judged="owner") == []
        assert labels(q="small") == ["ET SCAN small from <address>"]
        assert labels(limit=1, offset=2) == ["ET SCAN small from <address>"]

    @pytest.mark.parametrize(
        "params",
        [{"lane": "other"}, {"judged": "maybe"}, {"limit": 0}, {"limit": 101}, {"offset": -1}],
    )
    def test_a_question_it_cannot_answer_is_refused(
        self, client: TestClient, csrf_token: str, params: dict[str, Any]
    ) -> None:
        assert client.get(f"{BASE}/families", params=params).status_code == 422


class TestOneKind:
    def test_it_has_its_incidents_and_why_it_is_what_it_is(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        found = kind(session, 3, "ET SCAN big", confidence=50)
        found.ai_class = "probe"
        found.ai_confidence = 90
        found.ai_reason = "Scanners."
        found.provider = "anthropic"
        found.model = "claude-haiku-5-5"
        session.commit()

        body = client.get(f"{BASE}/families/{found.id}").json()

        assert body["id"] == found.id
        assert (body["provider"], body["model"]) == ("anthropic", "claude-haiku-5-5")
        assert body["why"] == ["The AI judged it probe, 90% sure: Scanners."]
        assert len(body["sample"]) == 3
        assert {item["family_id"] for item in body["sample"]} == {found.id}
        assert body["sample"][0]["lane"] == "suspect"

    def test_the_sample_is_the_most_recent_so_many(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        found = kind(session, 22, "ET SCAN many", confidence=50)

        body = client.get(f"{BASE}/families/{found.id}").json()

        assert body["incidents"] == 22
        assert len(body["sample"]) == 20

    @pytest.mark.parametrize(
        ("changes", "line"),
        [
            ({"owner_call": "background"}, "You said this kind is background"),
            ({"owner_call": "watch"}, "You asked to keep an eye on this kind"),
            ({}, "No AI has judged this kind yet."),
        ],
    )
    def test_it_says_what_the_owner_or_nobody_has_said(
        self,
        client: TestClient,
        csrf_token: str,
        session: Session,
        changes: dict[str, str],
        line: str,
    ) -> None:
        found = kind(session, 2, "ET SCAN words")
        for name, value in changes.items():
            setattr(found, name, value)
        session.commit()

        [first] = client.get(f"{BASE}/families/{found.id}").json()["why"]

        assert first.startswith(line)

    def test_a_judgement_without_a_reason_still_reads_as_a_sentence(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        found = kind(session, 2, "ET SCAN quiet")
        found.ai_class = "noise"
        found.ai_confidence = 70
        session.commit()

        assert client.get(f"{BASE}/families/{found.id}").json()["why"] == [
            "The AI judged it noise, 70% sure."
        ]

    def test_a_kind_with_nothing_going_on_is_still_there(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        found = kind(session, 2, "ET SCAN over", status="dismissed")

        body = client.get(f"{BASE}/families/{found.id}").json()

        assert (body["incidents"], body["alerts"], body["sample"]) == (0, 0, [])
        assert body["worst"] == "info"
        assert body["last_seen_at"] >= body["first_seen_at"]

    def test_one_that_is_not_there_is_not_found(self, client: TestClient, csrf_token: str) -> None:
        assert client.get(f"{BASE}/families/4040").status_code == 404


class TestTheOwnersWord:
    def call(self, client: TestClient, token: str, family: int, call: str | None) -> Any:
        return client.put(
            f"{BASE}/families/{family}/call", json={"call": call}, headers=headers(token)
        )

    def test_calling_a_kind_background_sets_all_of_it_aside(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        found = kind(session, 3, "ET SCAN big", confidence=80)

        response = self.call(client, csrf_token, found.id, "background")

        assert response.status_code == 200
        body = response.json()
        assert body["owner_call"] == "background"
        assert (body["threats"], body["background"]) == (0, 3)
        assert {item["lane"] for item in body["sample"]} == {"background"}
        assert {item["call"]["basis"] for item in body["sample"]} == {"owner"}
        [event] = audited(session, Action.THREATS_FAMILY_CALLED)
        assert event.outcome == Outcome.SUCCESS.value
        assert event.detail == {"family": found.id, "call": "background", "from_call": "none"}

    def test_watching_a_kind_keeps_it_from_being_set_aside(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        found = kind(session, 2, "ET SCAN big", confidence=80)
        found.ai_class = "probe"
        found.ai_confidence = 95
        session.commit()
        session.query(Incident).update(
            {"ai_class": "probe", "ai_confidence": 95, "ai_basis": "family"}
        )
        session.commit()

        body = self.call(client, csrf_token, found.id, "watch").json()

        assert body["owner_call"] == "watch"
        assert body["owner_call_at"] is not None
        assert {item["lane"] for item in body["sample"]} == {"threat"}

    def test_taking_the_word_back_leaves_it_to_the_ai(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        found = kind(session, 2, "ET SCAN big", confidence=80)
        self.call(client, csrf_token, found.id, "background")

        body = self.call(client, csrf_token, found.id, None).json()

        assert body["owner_call"] is None
        assert body["owner_call_at"] is None
        assert {item["call"] for item in body["sample"]} == {None}
        assert len(audited(session, Action.THREATS_FAMILY_CALLED)) == 2

    def test_saying_what_was_already_said_changes_and_records_nothing(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        found = kind(session, 2, "ET SCAN big")

        assert self.call(client, csrf_token, found.id, None).status_code == 200
        self.call(client, csrf_token, found.id, "watch")
        self.call(client, csrf_token, found.id, "watch")

        assert len(audited(session, Action.THREATS_FAMILY_CALLED)) == 1

    def test_it_has_to_be_a_kind_that_exists_and_a_word_it_knows(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        found = kind(session, 2, "ET SCAN big")

        assert self.call(client, csrf_token, 4040, "background").status_code == 404
        assert self.call(client, csrf_token, found.id, "ignore").status_code == 422
        assert (
            client.put(
                f"{BASE}/families/{found.id}/call",
                json={"call": "watch", "x": 1},
                headers=headers(csrf_token),
            ).status_code
            == 422
        )

    def test_it_needs_the_token_a_browser_sends(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        found = kind(session, 2, "ET SCAN big")

        response = client.put(f"{BASE}/families/{found.id}/call", json={"call": "watch"})

        assert response.status_code == 403


class TestAskingTheAi:
    def judge(self, client: TestClient, token: str, family: int) -> Any:
        return client.post(f"{BASE}/families/{family}/judge", headers=headers(token))

    def test_with_ai_off_it_says_so_and_the_kind_is_as_it_was(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        found = kind(session, 3, "ET SCAN big")

        body = self.judge(client, csrf_token, found.id).json()

        assert body["ok"] is False
        assert body["reason"].startswith("AI is turned off.")
        assert body["family"]["classification"] is None
        [event] = audited(session, Action.THREATS_FAMILY_JUDGED)
        assert event.outcome == Outcome.FAILURE.value
        assert event.detail == {"family": found.id}

    def test_the_ai_judges_it_and_every_incident_of_it_is_told(
        self,
        client: TestClient,
        csrf_token: str,
        app: FastAPI,
        serve: Serve,
        session: Session,
        settings: Settings,
    ) -> None:
        server = serve(judges(1))
        app.state.ai_origins["anthropic"] = server.url
        ready(session, settings)
        review_settings.save(session, review_settings.Policy("auto"))
        session.commit()
        found = kind(session, 3, "ET SCAN big", confidence=80)

        body = self.judge(client, csrf_token, found.id).json()

        assert body["ok"] is True
        assert body["reason"] is None
        family = body["family"]
        assert (family["classification"], family["confidence"]) == ("probe", 93)
        assert family["reason"] == "Internet scanners."
        assert (family["provider"], family["model"]) == ("anthropic", "claude-haiku-5-5")
        assert {item["call"]["basis"] for item in family["sample"]} == {"family"}
        assert {item["lane"] for item in family["sample"]} == {"background"}
        [event] = audited(session, Action.THREATS_FAMILY_JUDGED)
        assert event.outcome == Outcome.SUCCESS.value

    def test_a_kind_that_is_not_there_is_not_judged(
        self, client: TestClient, csrf_token: str
    ) -> None:
        assert self.judge(client, csrf_token, 4040).status_code == 404
