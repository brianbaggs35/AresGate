"""The Review page's API: the decisions to look at, what the owner says of them, and how much of it
they want to look at first."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import Action
from app.models import AuditEvent, ReviewFeedback, ReviewSettings, User
from tests.test_review import family, incident, reading

BASE = "/api/review"


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
        client.get(BASE),
        client.get(f"{BASE}/summary"),
        client.get(f"{BASE}/settings"),
        client.put(f"{BASE}/settings", json={"mode": "auto", "auto_from": 85, "learn": True}),
        client.post(f"{BASE}/family/1", json={"answer": "agree"}),
        client.post(f"{BASE}/agree", json={"items": [{"subject": "family", "id": 1}]}),
    ]

    assert [answer.status_code for answer in answers] == [401] * 6


class TestTheDecisions:
    def test_with_nothing_decided_there_is_nothing_to_look_at(
        self, client: TestClient, csrf_token: str
    ) -> None:
        found = client.get(BASE).json()

        assert found["items"] == []
        assert found["total"] == 0
        assert found["counts"] == {"waiting": 0, "decided": 0, "answered": 0}
        assert found["standing"]["rate"] is None
        assert found["mode"] == "all"

    def test_a_decision_says_what_it_is_and_what_it_does(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        judged = family(session, review="pending")
        for n in range(2):
            incident(session, n + 1, judged)
        session.commit()

        found = client.get(BASE).json()

        assert found["counts"]["waiting"] == 1
        decision = found["items"][0]
        assert decision["subject"] == "family"
        assert decision["id"] == judged.id
        assert (decision["kind"], decision["confidence"], decision["review"]) == (
            "noise",
            90,
            "pending",
        )
        assert decision["title"] == "Scanning k"
        assert decision["why"] == "Scanners."
        assert decision["incidents"] == 2
        assert decision["active"] == 2
        assert decision["severity"] == "medium"
        assert decision["counting"] is False
        assert decision["effect"] == "Sets aside 2 incidents going on, and any more of this kind."

    def test_what_raises_the_alarm_counts_at_once(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        found = incident(session)
        reading(session, found, "attack", 90, review="pending")
        session.commit()

        decision = client.get(BASE).json()["items"][0]

        assert decision["subject"] == "incident"
        assert decision["counting"] is True
        assert decision["effect"] == "Calls this incident a real attack."
        assert decision["suggestion"] is None

    def test_the_other_states_are_asked_for_by_name(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        found = incident(session)
        reading(session, found, "noise", 90, review="auto")
        family(session, review="agreed")
        session.commit()

        decided = client.get(BASE, params={"state": "decided"}).json()
        answered = client.get(BASE, params={"state": "answered"}).json()

        assert [item["subject"] for item in decided["items"]] == ["incident"]
        assert decided["items"][0]["effect"] == "Sets this incident aside."
        assert [item["subject"] for item in answered["items"]] == ["family"]
        assert decided["counts"] == {"waiting": 0, "decided": 1, "answered": 1}

    def test_a_family_with_one_incident_says_so(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        judged = family(session, review="pending", ai_class="attack")
        incident(session, 1, judged)
        session.commit()

        decision = client.get(BASE).json()["items"][0]

        assert decision["effect"] == "Raises 1 incident going on, and any more of this kind."

    def test_it_is_paged_and_the_page_is_limited(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        for key in "abc":
            family(session, key=key, review="pending")
        session.commit()

        page = client.get(BASE, params={"limit": 2, "offset": 2}).json()

        assert (page["total"], len(page["items"])) == (3, 1)
        assert client.get(BASE, params={"limit": 101}).status_code == 422
        assert client.get(BASE, params={"state": "later"}).status_code == 422

    def test_how_many_wait_is_told_alone_for_the_menu(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        family(session, review="pending")
        session.commit()

        assert client.get(f"{BASE}/summary").json() == {"waiting": 1}


class TestAnswering:
    def test_agreeing_makes_it_count_and_is_audited_without_the_reason(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        judged = family(session, review="pending")
        found = incident(session, 1, judged)
        session.commit()

        answer = client.post(
            f"{BASE}/family/{judged.id}",
            json={"answer": "agree", "reason": "  Fine,   it is a scanner. "},
            headers=headers(csrf_token),
        )

        assert answer.status_code == 200
        assert (answer.json()["review"], answer.json()["counting"]) == ("agreed", True)
        assert answer.json()["reason"] == "Fine, it is a scanner."
        session.expire_all()
        assert found.ai_class == "noise"
        entry = audited(session, Action.REVIEW_ANSWERED)[0]
        assert entry.detail == {
            "subject": "family",
            "id": judged.id,
            "answer": "agree",
            "reason_given": True,
        }
        assert "scanner" not in str(entry.detail)

    def test_disagreeing_with_an_incident_reading(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        found = incident(session)
        reading(session, found, "noise", 90, review="auto")
        session.commit()

        answer = client.post(
            f"{BASE}/incident/{found.id}",
            json={"answer": "disagree"},
            headers=headers(csrf_token),
        )

        assert answer.json()["review"] == "disagreed"
        assert answer.json()["counting"] is False
        assert session.scalars(select(ReviewFeedback.answer)).one() == "disagree"

    def test_keeping_a_kind_in_front_of_the_owner(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        judged = family(session)
        session.commit()

        client.post(
            f"{BASE}/family/{judged.id}",
            json={"answer": "disagree", "keep_kind": True},
            headers=headers(csrf_token),
        )

        session.expire_all()
        assert judged.owner_call == "watch"

    def test_the_answer_can_be_taken_back(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        judged = family(session, review="pending")
        session.commit()
        client.post(
            f"{BASE}/family/{judged.id}", json={"answer": "agree"}, headers=headers(csrf_token)
        )

        answer = client.post(
            f"{BASE}/family/{judged.id}", json={"answer": "undo"}, headers=headers(csrf_token)
        )

        assert answer.json()["review"] == "pending"

    def test_what_is_not_there_is_not_found(self, client: TestClient, csrf_token: str) -> None:
        answer = client.post(
            f"{BASE}/family/999", json={"answer": "agree"}, headers=headers(csrf_token)
        )

        assert answer.status_code == 404

    def test_a_bad_answer_is_refused(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        judged = family(session)
        session.commit()
        url = f"{BASE}/family/{judged.id}"

        assert (
            client.post(url, json={"answer": "maybe"}, headers=headers(csrf_token)).status_code
            == 422
        )
        assert (
            client.post(
                url, json={"answer": "agree", "x": 1}, headers=headers(csrf_token)
            ).status_code
            == 422
        )
        long = {"answer": "disagree", "reason": "x" * 301}
        assert client.post(url, json=long, headers=headers(csrf_token)).status_code == 422
        assert (
            client.post(
                f"{BASE}/thing/1", json={"answer": "agree"}, headers=headers(csrf_token)
            ).status_code
            == 422
        )

    def test_a_reason_of_only_spaces_is_none(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        judged = family(session)
        session.commit()

        answer = client.post(
            f"{BASE}/family/{judged.id}",
            json={"answer": "disagree", "reason": "   "},
            headers=headers(csrf_token),
        )

        assert answer.json()["reason"] is None

    def test_agreeing_with_what_is_shown(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        one = family(session, key="a", review="pending")
        two = family(session, key="b", review="pending")
        session.commit()

        answer = client.post(
            f"{BASE}/agree",
            json={
                "items": [
                    {"subject": "family", "id": one.id},
                    {"subject": "family", "id": two.id},
                    {"subject": "family", "id": 999},
                ]
            },
            headers=headers(csrf_token),
        )

        assert answer.json() == {"agreed": 2}
        assert audited(session, Action.REVIEW_AGREED_ALL)[0].detail == {"count": 2}

    def test_agreeing_with_nothing_that_waits_is_not_audited(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        done = family(session, review="agreed")
        session.commit()

        answer = client.post(
            f"{BASE}/agree",
            json={"items": [{"subject": "family", "id": done.id}]},
            headers=headers(csrf_token),
        )

        assert answer.json() == {"agreed": 0}
        assert audited(session, Action.REVIEW_AGREED_ALL) == []

    def test_agreeing_is_for_a_few_at_a_time(self, client: TestClient, csrf_token: str) -> None:
        items: Any = [{"subject": "family", "id": n} for n in range(1, 102)]

        too_many = client.post(f"{BASE}/agree", json={"items": items}, headers=headers(csrf_token))
        none = client.post(f"{BASE}/agree", json={"items": []}, headers=headers(csrf_token))

        assert (too_many.status_code, none.status_code) == (422, 422)


class TestTheSettings:
    def test_they_are_the_defaults_until_changed(self, client: TestClient, csrf_token: str) -> None:
        found = client.get(f"{BASE}/settings").json()

        assert found == {
            "mode": "all",
            "auto_from": 85,
            "learn": True,
            "default_mode": "all",
            "default_auto_from": 85,
            "min_auto_from": 50,
            "updated_at": None,
        }

    def test_the_ai_can_be_let_to_decide_on_its_own(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        answer = client.put(
            f"{BASE}/settings",
            json={"mode": "auto", "auto_from": 90, "learn": False},
            headers=headers(csrf_token),
        )

        assert answer.status_code == 200
        assert (answer.json()["mode"], answer.json()["learn"]) == ("auto", False)
        assert answer.json()["updated_at"] is not None
        session.expire_all()
        assert session.get(ReviewSettings, 1) is not None
        entry = audited(session, Action.REVIEW_SETTINGS_CHANGED)[0]
        assert entry.detail == {
            "mode": "auto",
            "from_mode": "all",
            "auto_from": 90,
            "learn": False,
        }

    def test_saving_what_is_saved_is_no_change(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        client.put(
            f"{BASE}/settings",
            json={"mode": "all", "auto_from": 85, "learn": True},
            headers=headers(csrf_token),
        )

        assert audited(session, Action.REVIEW_SETTINGS_CHANGED) == []

    def test_a_bad_setting_is_refused(self, client: TestClient, csrf_token: str) -> None:
        bad = [
            {"mode": "never", "auto_from": 85, "learn": True},
            {"mode": "auto", "auto_from": 49, "learn": True},
            {"mode": "auto", "auto_from": 101, "learn": True},
            {"mode": "auto", "auto_from": 85},
        ]

        statuses = [
            client.put(f"{BASE}/settings", json=body, headers=headers(csrf_token)).status_code
            for body in bad
        ]

        assert statuses == [422, 422, 422, 422]
