from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import Action, Outcome
from app.config import Settings
from app.events.event import Severity
from app.models import AuditEvent, Incident, User, VerdictRule
from tests.helpers import OTHER_ORIGIN
from tests.test_incidents_engine import ATTACKER, DEVICE, NOW, alert, run, store

BASE = "/api/verdicts"
SIGNATURE = "ET SCAN Potential SSH Scan"


def headers(token: str) -> dict[str, str]:
    return {"X-CSRF-Token": token}


def give(client: TestClient, token: str, **body: Any) -> Any:
    return client.post(BASE, json={"verdict": "not_suspicious", **body}, headers=headers(token))


def audited(session: Session, action: Action) -> list[AuditEvent]:
    session.expire_all()
    return list(
        session.scalars(
            select(AuditEvent).where(AuditEvent.action == action).order_by(AuditEvent.id)
        )
    )


def attack(session: Session, settings: Settings) -> Incident:
    """An attack from one address, which AresGate is 40 points sure of."""
    store(session, settings, alert(NOW, n=1, severity=Severity.HIGH))
    run(session)
    return session.scalars(select(Incident)).one()


def test_it_is_only_for_someone_signed_in(client: TestClient, account: User) -> None:
    answers = [
        client.get(BASE),
        client.post(BASE, json={"verdict": "threat", "address": ATTACKER}),
        client.patch(f"{BASE}/1", json={"note": "x"}),
        client.delete(f"{BASE}/1"),
    ]

    assert [answer.status_code for answer in answers] == [401, 401, 401, 401]


class TestGivingAVerdict:
    def test_an_install_with_none_has_an_empty_list(
        self, client: TestClient, csrf_token: str
    ) -> None:
        assert client.get(BASE).json() == {"items": []}

    def test_it_is_kept_and_a_record_is_made(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        response = give(client, csrf_token, address=ATTACKER, note="  my scanner  ")

        assert response.status_code == 201
        body = response.json()
        assert body | {"id": 0, "created_at": "", "updated_at": ""} == {
            "id": 0,
            "verdict": "not_suspicious",
            "address": ATTACKER,
            "source": None,
            "source_name": None,
            "signature": None,
            "note": "my scanner",
            "created_at": "",
            "updated_at": "",
            "hits": 0,
            "last_hit_at": None,
        }
        assert client.get(BASE).json()["items"] == [body]
        (event,) = audited(session, Action.VERDICT_GIVEN)
        assert event.outcome == Outcome.SUCCESS
        assert event.username == "brian"
        assert event.detail == {
            "verdict_id": body["id"],
            "verdict": "not_suspicious",
            "address": ATTACKER,
        }

    def test_it_can_be_about_a_program_and_a_signature_too(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        response = give(
            client, csrf_token, verdict="low_priority", source="wazuh", signature=f" {SIGNATURE} "
        )

        body = response.json()
        assert (body["source"], body["source_name"], body["signature"]) == (
            "wazuh",
            "Wazuh",
            SIGNATURE,
        )
        assert audited(session, Action.VERDICT_GIVEN)[0].detail == {
            "verdict_id": body["id"],
            "verdict": "low_priority",
            "source": "wazuh",
            "signature": SIGNATURE,
        }

    def test_an_address_can_be_a_version_6_one(self, client: TestClient, csrf_token: str) -> None:
        assert give(client, csrf_token, address="2606:2800:220:1::1").json()["address"] == (
            "2606:2800:220:1::1"
        )

    def test_it_is_applied_at_once_to_the_incidents_that_are_going(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        incident = attack(session, settings)
        assert (incident.confidence, incident.verdict) == (40, None)

        body = give(client, csrf_token, address=ATTACKER).json()

        session.expire_all()
        assert (incident.confidence, incident.verdict) == (0, "not_suspicious")
        assert body["hits"] == 1

    def test_and_says_how_many_signals_it_has_been_applied_to(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        attack(session, settings)
        give(client, csrf_token, address=DEVICE)
        given = give(client, csrf_token, address=ATTACKER).json()

        (quiet, used) = sorted(client.get(BASE).json()["items"], key=lambda item: item["hits"])

        assert quiet["address"] == DEVICE
        assert quiet["hits"] == 0
        assert (used["id"], used["hits"]) == (given["id"], 1)
        assert used["last_hit_at"] is not None

    def test_saying_it_again_of_the_same_thing_changes_it(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        attack(session, settings)
        first = give(client, csrf_token, address=ATTACKER, signature=SIGNATURE).json()

        again = give(client, csrf_token, verdict="threat", address=ATTACKER, signature=SIGNATURE)

        assert again.status_code == 200
        assert again.json()["id"] == first["id"]
        assert again.json()["verdict"] == "threat"
        assert len(client.get(BASE).json()["items"]) == 1
        session.expire_all()
        assert session.scalars(select(Incident)).one().verdict == "threat"
        (changed,) = audited(session, Action.VERDICT_CHANGED)
        assert changed.detail is not None
        assert (changed.detail["verdict"], changed.detail["from"]) == ("threat", "not_suspicious")

    def test_a_note_can_be_added_by_saying_it_again(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        give(client, csrf_token, address=ATTACKER)

        again = give(client, csrf_token, address=ATTACKER, note="a scanner I run")

        assert again.status_code == 200
        assert again.json()["note"] == "a scanner I run"
        assert len(audited(session, Action.VERDICT_CHANGED)) == 1

    def test_saying_the_same_again_changes_nothing(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        give(client, csrf_token, address=ATTACKER, note="a scanner I run")

        again = give(client, csrf_token, address=ATTACKER, note="a scanner I run")
        without = give(client, csrf_token, address=ATTACKER)

        assert again.status_code == without.status_code == 200
        assert without.json()["note"] == "a scanner I run"
        assert audited(session, Action.VERDICT_CHANGED) == []

    @pytest.mark.parametrize(
        "body",
        [
            {},
            {"verdict": "threat"},
            {"verdict": "threat", "note": "but of what?"},
            {"verdict": "maybe", "address": ATTACKER},
            {"address": ATTACKER},
            {"verdict": "threat", "address": "not an address"},
            {"verdict": "threat", "source": "zeek"},
            {"verdict": "threat", "signature": "   "},
            {"verdict": "threat", "signature": "x" * 257},
            {"verdict": "threat", "address": ATTACKER, "note": "x" * 501},
            {"verdict": "threat", "address": ATTACKER, "colour": "red"},
        ],
        ids=[
            "nothing",
            "of nothing",
            "of nothing but a note",
            "a verdict that is none",
            "no verdict",
            "no address",
            "no such program",
            "a blank signature",
            "a long signature",
            "a long note",
            "something else",
        ],
    )
    def test_nonsense_is_refused(
        self, client: TestClient, csrf_token: str, session: Session, body: dict[str, Any]
    ) -> None:
        response = client.post(BASE, json=body, headers=headers(csrf_token))

        assert response.status_code == 422
        assert session.scalars(select(VerdictRule)).all() == []

    def test_it_is_only_given_from_one_of_its_own_pages(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        response = client.post(
            BASE,
            json={"verdict": "threat", "address": ATTACKER},
            headers={**headers(csrf_token), "Origin": OTHER_ORIGIN},
        )

        assert response.status_code == 403
        assert session.scalars(select(VerdictRule)).all() == []


class TestChangingAVerdict:
    def given(self, client: TestClient, token: str) -> int:
        return int(give(client, token, address=ATTACKER, note="a scanner I run").json()["id"])

    def test_what_is_said_can_be_changed_and_it_is_applied(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        incident = attack(session, settings)
        rule_id = self.given(client, csrf_token)

        response = client.patch(
            f"{BASE}/{rule_id}", json={"verdict": "threat"}, headers=headers(csrf_token)
        )

        assert response.status_code == 200
        assert response.json()["verdict"] == "threat"
        assert response.json()["note"] == "a scanner I run"
        session.expire_all()
        assert (incident.confidence, incident.verdict) == (100, "threat")
        (changed,) = audited(session, Action.VERDICT_CHANGED)
        assert changed.detail is not None
        assert (changed.detail["verdict"], changed.detail["from"]) == ("threat", "not_suspicious")

    def test_the_note_can_be_changed_and_taken_off(
        self, client: TestClient, csrf_token: str
    ) -> None:
        rule_id = self.given(client, csrf_token)

        changed = client.patch(
            f"{BASE}/{rule_id}", json={"note": " now it's the vacuum "}, headers=headers(csrf_token)
        )
        taken_off = client.patch(
            f"{BASE}/{rule_id}", json={"note": None}, headers=headers(csrf_token)
        )

        assert changed.json()["note"] == "now it's the vacuum"
        assert taken_off.json()["note"] is None
        assert taken_off.json()["verdict"] == "not_suspicious"

    def test_saying_what_it_already_is_changes_nothing(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        rule_id = self.given(client, csrf_token)

        for body in ({}, {"verdict": "not_suspicious"}, {"note": "a scanner I run"}):
            response = client.patch(f"{BASE}/{rule_id}", json=body, headers=headers(csrf_token))
            assert response.status_code == 200

        assert audited(session, Action.VERDICT_CHANGED) == []

    @pytest.mark.parametrize(
        "body",
        [
            {"verdict": "maybe"},
            {"verdict": None, "address": "8.8.8.8"},
            {"note": "x" * 501},
        ],
        ids=["a verdict that is none", "what it is about", "a long note"],
    )
    def test_nonsense_is_refused(
        self, client: TestClient, csrf_token: str, body: dict[str, Any]
    ) -> None:
        rule_id = self.given(client, csrf_token)

        response = client.patch(f"{BASE}/{rule_id}", json=body, headers=headers(csrf_token))

        assert response.status_code == 422

    @pytest.mark.parametrize("rule_id", ["999999", "0", "99999999999999999999"])
    def test_there_is_no_such_verdict(
        self, client: TestClient, csrf_token: str, rule_id: str
    ) -> None:
        response = client.patch(
            f"{BASE}/{rule_id}", json={"verdict": "threat"}, headers=headers(csrf_token)
        )

        assert response.status_code == (404 if rule_id == "999999" else 422)


class TestTakingAVerdictBack:
    def test_the_incidents_are_judged_as_if_it_had_never_been_said(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        incident = attack(session, settings)
        rule_id = give(client, csrf_token, address=ATTACKER).json()["id"]
        session.expire_all()
        assert incident.verdict == "not_suspicious"

        response = client.delete(f"{BASE}/{rule_id}", headers=headers(csrf_token))

        assert response.status_code == 204
        assert client.get(BASE).json() == {"items": []}
        session.expire_all()
        assert (incident.confidence, incident.verdict, incident.verdict_counts) == (40, None, {})
        (removed,) = audited(session, Action.VERDICT_REMOVED)
        assert removed.detail == {
            "verdict_id": rule_id,
            "verdict": "not_suspicious",
            "address": ATTACKER,
        }

    def test_a_resolved_incident_keeps_what_was_said_at_the_time(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        incident = attack(session, settings)
        rule_id = give(client, csrf_token, address=ATTACKER).json()["id"]
        incident.status = "resolved"
        session.commit()

        client.delete(f"{BASE}/{rule_id}", headers=headers(csrf_token))

        session.expire_all()
        assert incident.verdict == "not_suspicious"

    def test_there_is_no_such_verdict(self, client: TestClient, csrf_token: str) -> None:
        response = client.delete(f"{BASE}/999999", headers=headers(csrf_token))

        assert response.status_code == 404
