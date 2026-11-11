"""Trust: what the owner says is safe, kept as verdicts and shown with what each was applied to."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import Action
from app.config import Settings
from app.events.event import Severity
from app.models import Incident, User, VerdictRule
from tests.test_ai_triage import kept
from tests.test_incidents_engine import ATTACKER, DEVICE, NOW, OTHER_ATTACKER, alert, run, store
from tests.test_verdicts_api import SIGNATURE, attack, audited, give, headers

BASE = "/api/trust"
CLOUD = "52.1.2.0/24"


def trust(client: TestClient, token: str, **body: Any) -> Any:
    return client.post(BASE, json=body, headers=headers(token))


def rules(session: Session) -> list[VerdictRule]:
    session.expire_all()
    return list(session.scalars(select(VerdictRule).order_by(VerdictRule.id)))


def test_it_is_only_for_someone_signed_in(client: TestClient, account: User) -> None:
    answers = [
        client.get(BASE),
        client.get(f"{BASE}/suggestions"),
        client.get(f"{BASE}/1"),
        client.post(BASE, json={"address": ATTACKER}),
        client.put(f"{BASE}/1", json={"address": ATTACKER}),
        client.delete(f"{BASE}/1"),
    ]

    assert [each.status_code for each in answers] == [401] * 6


def test_a_quiet_install_trusts_nothing(client: TestClient, csrf_token: str) -> None:
    assert client.get(BASE).json() == {"items": [], "safe": 0, "low_priority": 0, "applied": 0}
    assert client.get(f"{BASE}/suggestions").json() == {"items": []}


class TestTrusting:
    def test_an_address_is_trusted_at_once_and_says_what_it_was_applied_to(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        attack(session, settings)

        response = trust(client, csrf_token, address=ATTACKER, note="My own scanner")

        assert response.status_code == 201
        body = response.json()
        assert body["verdict"] == "not_suspicious"
        assert body["about"] == f"Everything about {ATTACKER}"
        assert body["note"] == "My own scanner"
        assert (body["hits"], body["incidents"]) == (1, 1)
        session.expire_all()
        assert session.scalars(select(Incident)).one().confidence == 0

    def test_it_is_how_much_it_is_trusted_that_can_be_said(
        self, client: TestClient, csrf_token: str
    ) -> None:
        low = trust(client, csrf_token, address=ATTACKER, verdict="low_priority")

        assert low.json()["verdict"] == "low_priority"
        assert trust(client, csrf_token, address=ATTACKER, verdict="threat").status_code == 422

    def test_trusting_what_is_already_trusted_changes_it(
        self, client: TestClient, csrf_token: str
    ) -> None:
        first = trust(client, csrf_token, address=ATTACKER).json()

        again = trust(client, csrf_token, address=ATTACKER, verdict="low_priority")

        assert again.status_code == 200
        assert again.json()["id"] == first["id"]
        assert again.json()["verdict"] == "low_priority"

    def test_it_says_what_each_kind_of_decision_is_about(
        self, client: TestClient, csrf_token: str
    ) -> None:
        said = [
            trust(client, csrf_token, address=DEVICE, destination=CLOUD).json()["about"],
            trust(client, csrf_token, signature=SIGNATURE).json()["about"],
            trust(client, csrf_token, source="wazuh").json()["about"],
            trust(client, csrf_token, signature="x", source="wazuh").json()["about"],
            trust(client, csrf_token, address=ATTACKER, signature="y", source="wazuh").json()[
                "about"
            ],
        ]

        assert said == [
            f"What {DEVICE} sends to {CLOUD}",
            f"Every “{SIGNATURE}” alert",
            "Everything Wazuh reports",
            "Every “x” alert, as reported by Wazuh",
            f"Everything about {ATTACKER}, when it is “y”, as reported by Wazuh",
        ]

    def test_it_has_to_be_about_something(self, client: TestClient, csrf_token: str) -> None:
        assert trust(client, csrf_token).status_code == 422


class TestTheList:
    def test_it_counts_the_decisions_by_how_much_they_trust_and_what_they_were_applied_to(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        attack(session, settings)
        trust(client, csrf_token, address=ATTACKER)
        trust(client, csrf_token, address=OTHER_ATTACKER, verdict="low_priority")
        # A verdict that something is a threat is not a trust decision.
        give(client, csrf_token, verdict="threat", address=DEVICE)

        body = client.get(BASE).json()

        assert (body["safe"], body["low_priority"], body["applied"]) == (1, 1, 1)
        assert [each["address"] for each in body["items"]] == [OTHER_ATTACKER, ATTACKER]
        assert [each["incidents"] for each in body["items"]] == [0, 1]


class TestOneDecision:
    def test_it_lists_the_incidents_it_was_applied_to(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        attack(session, settings)
        made = trust(client, csrf_token, address=ATTACKER).json()

        body = client.get(f"{BASE}/{made['id']}").json()

        [incident] = body["applied_to"]
        assert incident["title"].endswith(ATTACKER + ")")
        assert (incident["signals"], incident["severity"], incident["status"]) == (
            1,
            "high",
            "open",
        )
        assert body["about"] == f"Everything about {ATTACKER}"

    def test_a_decision_that_is_not_there_or_is_not_a_trust_is_not_found(
        self, client: TestClient, csrf_token: str
    ) -> None:
        threat = give(client, csrf_token, verdict="threat", address=ATTACKER).json()

        assert client.get(f"{BASE}/{threat['id']}").status_code == 404
        assert client.get(f"{BASE}/99").status_code == 404
        assert (
            client.delete(f"{BASE}/{threat['id']}", headers=headers(csrf_token)).status_code == 404
        )


class TestChangingIt:
    def test_everything_about_it_can_be_changed_and_the_incidents_are_judged_again(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        store(
            session,
            settings,
            alert(NOW, n=1, severity=Severity.HIGH),
            alert(NOW, n=2, src_address=OTHER_ATTACKER, severity=Severity.HIGH),
        )
        run(session)
        made = trust(client, csrf_token, address=ATTACKER).json()

        response = client.put(
            f"{BASE}/{made['id']}",
            json={
                "address": OTHER_ATTACKER,
                "verdict": "low_priority",
                "signature": SIGNATURE,
                "note": "A different one",
            },
            headers=headers(csrf_token),
        )

        assert response.status_code == 200
        body = response.json()
        assert (body["address"], body["verdict"], body["signature"]) == (
            OTHER_ATTACKER,
            "low_priority",
            SIGNATURE,
        )
        assert body["note"] == "A different one"
        assert body["id"] == made["id"]
        session.expire_all()
        by_subject = {each.subject: each for each in session.scalars(select(Incident))}
        # What it no longer covers counts again, and what it now covers does not.
        assert by_subject[ATTACKER].confidence > 0
        assert by_subject[OTHER_ATTACKER].confidence == 0
        [event] = audited(session, Action.VERDICT_CHANGED)
        assert event.detail is not None
        assert event.detail["from"] == "not_suspicious"

    def test_saying_the_same_again_changes_nothing(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        made = trust(client, csrf_token, address=ATTACKER, note="x").json()

        response = client.put(
            f"{BASE}/{made['id']}",
            json={"address": ATTACKER, "note": "x"},
            headers=headers(csrf_token),
        )

        assert response.status_code == 200
        assert audited(session, Action.VERDICT_CHANGED) == []

    def test_it_cannot_become_what_another_decision_already_is(
        self, client: TestClient, csrf_token: str
    ) -> None:
        trust(client, csrf_token, address=ATTACKER)
        other = trust(client, csrf_token, address=OTHER_ATTACKER).json()

        response = client.put(
            f"{BASE}/{other['id']}", json={"address": ATTACKER}, headers=headers(csrf_token)
        )

        assert response.status_code == 409
        assert "already a decision" in response.json()["detail"]

    def test_a_note_can_be_taken_off(self, client: TestClient, csrf_token: str) -> None:
        made = trust(client, csrf_token, address=ATTACKER, note="x").json()

        response = client.put(
            f"{BASE}/{made['id']}", json={"address": ATTACKER}, headers=headers(csrf_token)
        )

        assert response.json()["note"] is None

    def test_one_that_is_not_there_is_not_found(self, client: TestClient, csrf_token: str) -> None:
        response = client.put(f"{BASE}/9", json={"address": ATTACKER}, headers=headers(csrf_token))

        assert response.status_code == 404


class TestTakingItBack:
    def test_the_incidents_are_judged_as_if_it_had_never_been_said(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        attack(session, settings)
        made = trust(client, csrf_token, address=ATTACKER).json()

        response = client.delete(f"{BASE}/{made['id']}", headers=headers(csrf_token))

        assert response.status_code == 204
        assert rules(session) == []
        assert session.scalars(select(Incident)).one().confidence > 0
        assert len(audited(session, Action.VERDICT_REMOVED)) == 1


class TestWhatTheAiWouldTrust:
    def read(
        self, session: Session, settings: Settings, *, address: str = ATTACKER, **changes: Any
    ) -> Incident:
        store(
            session,
            settings,
            alert(NOW, n=sum(int(part) for part in address.split(".")), src_address=address),
        )
        run(session)
        found = session.scalars(select(Incident).where(Incident.subject == address)).one()
        kept(session, found, **changes)
        session.commit()
        return found

    def test_an_incident_it_is_sure_is_nothing_is_suggested_with_why(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        found = self.read(
            session,
            settings,
            verdict="not_suspicious",
            verdict_reason="A vendor's own scanner.",
            confidence=90,
            headline="A scheduled scan",
        )

        [one] = client.get(f"{BASE}/suggestions").json()["items"]

        assert one["incident_id"] == found.id
        assert one["subject"] == ATTACKER
        assert (one["verdict"], one["confidence"]) == ("not_suspicious", 90)
        assert one["reason"] == "A vendor's own scanner."
        assert one["headline"] == "A scheduled scan"
        assert one["severity"] == "medium"

    def test_only_what_it_is_sure_of_and_nothing_covers_yet_is_suggested(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        self.read(session, settings, verdict="not_suspicious", confidence=50)
        self.read(session, settings, address=OTHER_ATTACKER, verdict="threat", confidence=95)
        assert client.get(f"{BASE}/suggestions").json() == {"items": []}

    def test_an_address_that_is_already_trusted_is_not_suggested(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        self.read(session, settings, verdict="low_priority", confidence=80)
        trust(client, csrf_token, address=ATTACKER)

        assert client.get(f"{BASE}/suggestions").json() == {"items": []}

    def test_an_incident_about_a_rule_or_one_that_is_over_is_not_suggested(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        found = self.read(session, settings, verdict="not_suspicious", confidence=80)
        found.subject = "ssh-guessing"
        other = self.read(
            session, settings, address=OTHER_ATTACKER, verdict="not_suspicious", confidence=80
        )
        other.status = "resolved"
        session.commit()

        assert client.get(f"{BASE}/suggestions").json() == {"items": []}

    def test_the_most_sure_come_first_and_there_are_few(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        for number in range(12):
            self.read(
                session,
                settings,
                address=f"93.{number + 10}.216.5",
                verdict="not_suspicious",
                confidence=60 + number,
            )

        items = client.get(f"{BASE}/suggestions").json()["items"]

        assert len(items) == 10
        assert [each["confidence"] for each in items] == list(range(71, 61, -1))
