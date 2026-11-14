from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import clearing
from app.audit import Action, Outcome
from app.config import Settings
from app.events.event import Severity
from app.incidents import engine
from app.models import AiClearVeto, AiTriage, AuditEvent, Incident, User, VerdictRule
from app.threats.settings import Tuning
from tests.helpers import OTHER_ORIGIN
from tests.test_incidents_engine import (
    ATTACKER,
    DEVICE,
    NOW,
    OTHER_ATTACKER,
    alert,
    run,
    store,
)

BASE = "/api/verdicts"
SIGNATURE = "ET SCAN Potential SSH Scan"
CLOUD = "52.1.2.0/24"
CLOUD_HOST = "52.1.2.9"


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
            "destination": None,
            "source": None,
            "source_name": None,
            "signature": None,
            "note": "my scanner",
            "given_by": "owner",
            "ai": None,
            "created_at": "",
            "updated_at": "",
            "hits": 0,
            "last_hit_at": None,
            "replaced": None,
        }
        listed = {key: value for key, value in body.items() if key != "replaced"}
        assert client.get(BASE).json()["items"] == [listed]
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

    def test_a_destination_says_where_a_device_sends_its_traffic(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        response = give(client, csrf_token, address=DEVICE, destination=CLOUD)

        assert response.status_code == 201
        body = response.json()
        assert (body["address"], body["destination"]) == (DEVICE, CLOUD)
        assert audited(session, Action.VERDICT_GIVEN)[0].detail == {
            "verdict_id": body["id"],
            "verdict": "not_suspicious",
            "address": DEVICE,
            "destination": CLOUD,
        }

    def test_a_single_address_destination_is_kept_as_that_address(
        self, client: TestClient, csrf_token: str
    ) -> None:
        body = give(client, csrf_token, address=DEVICE, destination=f" {CLOUD_HOST} ").json()

        assert body["destination"] == CLOUD_HOST

    def test_a_destination_said_as_null_is_no_destination(
        self, client: TestClient, csrf_token: str
    ) -> None:
        body = give(client, csrf_token, address=DEVICE, destination=None).json()

        assert body["destination"] is None

    def test_a_destination_is_a_verdict_apart_from_the_device_alone(
        self, client: TestClient, csrf_token: str
    ) -> None:
        give(client, csrf_token, address=DEVICE)

        given = give(client, csrf_token, verdict="threat", address=DEVICE, destination=CLOUD)

        assert given.status_code == 201
        assert len(client.get(BASE).json()["items"]) == 2

    def test_saying_it_again_of_the_same_device_and_network_changes_it(
        self, client: TestClient, csrf_token: str
    ) -> None:
        give(client, csrf_token, address=DEVICE, destination=CLOUD)

        again = give(client, csrf_token, verdict="threat", address=DEVICE, destination=CLOUD)

        assert again.status_code == 200
        assert (again.json()["verdict"], again.json()["replaced"]) == (
            "threat",
            "not_suspicious",
        )
        assert len(client.get(BASE).json()["items"]) == 1

    def test_it_quiets_what_the_device_sends_there_and_nothing_else_of_it(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        store(
            session,
            settings,
            alert(NOW, n=1, src_address=DEVICE, dst_address=CLOUD_HOST, severity=Severity.HIGH),
            alert(NOW, n=2, src_address=DEVICE, dst_address=ATTACKER, severity=Severity.HIGH),
        )
        run(session)

        give(client, csrf_token, address=DEVICE, destination=CLOUD)

        session.expire_all()
        by_subject = {incident.subject: incident for incident in session.scalars(select(Incident))}
        assert by_subject[CLOUD_HOST].verdict == "not_suspicious"
        assert by_subject[ATTACKER].verdict is None

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
        assert again.json()["replaced"] == "not_suspicious"
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
        assert again.json()["replaced"] == "not_suspicious"
        assert len(audited(session, Action.VERDICT_CHANGED)) == 1

    def test_saying_the_same_again_changes_nothing(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        give(client, csrf_token, address=ATTACKER, note="a scanner I run")

        again = give(client, csrf_token, address=ATTACKER, note="a scanner I run")
        without = give(client, csrf_token, address=ATTACKER)

        assert again.status_code == without.status_code == 200
        assert without.json()["note"] == "a scanner I run"
        assert without.json()["replaced"] == "not_suspicious"
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
            {"verdict": "threat", "destination": CLOUD},
            {"verdict": "threat", "address": DEVICE, "destination": "52.1.2.9/24"},
            {"verdict": "threat", "address": DEVICE, "destination": "not a network"},
            {"verdict": "threat", "source": "wazuh", "destination": CLOUD},
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
            "a destination with no device",
            "a network with host bits set",
            "a destination that is not one",
            "a destination with a program but no device",
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


class TestOnlyWhatItCouldChangeIsJudged:
    """A verdict is judged again only in the incidents it can make a difference to: on a network
    with thousands of open incidents, giving one must not wait for every signal to be judged."""

    @pytest.fixture
    def rebuilt(self, monkeypatch: pytest.MonkeyPatch) -> list[str]:
        """The subjects of the incidents that are judged again, in the order they were."""
        subjects: list[str] = []
        original = engine.__dict__["_rebuild"]

        def spy(db: Session, incident: Incident, *rest: Any, **how: Any) -> None:
            subjects.append(incident.subject)
            original(db, incident, *rest, **how)

        monkeypatch.setattr(engine, "_rebuild", spy)
        return subjects

    @pytest.fixture
    def two(self, session: Session, settings: Settings) -> None:
        store(
            session,
            settings,
            alert(NOW, n=1, severity=Severity.HIGH),
            alert(NOW, n=2, severity=Severity.HIGH, src_address=OTHER_ATTACKER),
        )
        run(session)

    def test_giving_one_leaves_the_other_incidents_alone(
        self, client: TestClient, csrf_token: str, two: None, rebuilt: list[str]
    ) -> None:
        give(client, csrf_token, address=ATTACKER)

        assert rebuilt == [ATTACKER]

    def test_so_does_changing_one(
        self, client: TestClient, csrf_token: str, two: None, rebuilt: list[str]
    ) -> None:
        rule_id = give(client, csrf_token, address=ATTACKER).json()["id"]
        rebuilt.clear()

        client.patch(f"{BASE}/{rule_id}", json={"verdict": "threat"}, headers=headers(csrf_token))

        assert rebuilt == [ATTACKER]

    def test_and_so_does_taking_one_back(
        self, client: TestClient, csrf_token: str, two: None, rebuilt: list[str]
    ) -> None:
        rule_id = give(client, csrf_token, address=ATTACKER).json()["id"]
        rebuilt.clear()

        client.delete(f"{BASE}/{rule_id}", headers=headers(csrf_token))

        assert rebuilt == [ATTACKER]

    def test_a_verdict_nothing_matches_judges_nothing_again(
        self, client: TestClient, csrf_token: str, two: None, rebuilt: list[str]
    ) -> None:
        give(client, csrf_token, address="8.8.4.4")

        assert rebuilt == []

    def test_a_verdict_on_a_program_reaches_every_incident_that_program_reported(
        self, client: TestClient, csrf_token: str, two: None, rebuilt: list[str]
    ) -> None:
        give(client, csrf_token, source="wazuh")

        assert sorted(rebuilt) == sorted([ATTACKER, OTHER_ATTACKER])


class TestWhatAVerdictReaches:
    def test_the_incidents_with_a_signal_it_is_about(
        self, session: Session, settings: Settings
    ) -> None:
        store(
            session,
            settings,
            alert(NOW, n=1),
            alert(NOW, n=2, src_address=OTHER_ATTACKER, signature="ET WEB Probe"),
        )
        run(session)
        by_subject = {item.subject: item.id for item in session.scalars(select(Incident))}
        both = {by_subject[ATTACKER], by_subject[OTHER_ATTACKER]}

        def reached(**about: Any) -> set[int]:
            rule = VerdictRule(verdict="threat", **about)
            session.add(rule)
            session.flush()
            return engine.reach(session, rule)

        assert reached(address=ATTACKER) == {by_subject[ATTACKER]}
        assert reached(signature="ET WEB Probe") == {by_subject[OTHER_ATTACKER]}
        assert reached(address=ATTACKER, signature="ET WEB Probe") == set()
        assert reached(source="opnsense") == set()
        assert reached(source="wazuh") == both
        # A signal that names an address as where it went is about that address too.
        assert reached(address=DEVICE) == both

    def test_an_incident_that_is_over_is_history_and_is_not_reached(
        self, session: Session, settings: Settings
    ) -> None:
        store(session, settings, alert(NOW, n=1))
        run(session)
        incident = session.scalars(select(Incident)).one()
        incident.status = "resolved"
        session.flush()
        rule = VerdictRule(verdict="threat", address=ATTACKER)
        session.add(rule)
        session.flush()

        assert engine.reach(session, rule) == set()


class TestWhatTheAiGave:
    def given_by_ai(self, session: Session, settings: Settings) -> VerdictRule:
        """The verdict the AI gave of a scan: it was 91 sure, and said why."""
        store(session, settings, alert(NOW, n=1, severity=Severity.HIGH))
        run(session)
        found = session.scalars(select(Incident)).one()
        reading = AiTriage(
            incident_id=found.id,
            read_at=NOW,
            signals_read=1,
            classification="noise",
            confidence=91,
            headline="A scanner",
            story="It tried a port.",
            verdict="not_suspicious",
            verdict_reason="The owner's own scanner.",
            provider="anthropic",
            model="claude-haiku-5-5",
        )
        rule = clearing.clear(session, found, reading, Tuning(ai_gives_verdicts=True), NOW)
        session.commit()
        assert rule is not None
        return rule

    def test_it_says_who_gave_it_and_what_the_ai_said(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        rule = self.given_by_ai(session, settings)

        (listed,) = client.get(BASE).json()["items"]

        assert listed["given_by"] == "ai"
        assert listed["note"] == "The owner's own scanner."
        assert listed["ai"] == {
            "confidence": 91,
            "provider": "anthropic",
            "model": "claude-haiku-5-5",
            "incident_id": rule.ai_incident_id,
        }

    def test_the_owner_saying_it_themselves_makes_it_theirs(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        rule = self.given_by_ai(session, settings)

        response = give(
            client,
            csrf_token,
            address=str(rule.address),
            source=rule.source,
            signature=rule.signature,
        )

        assert response.status_code == 200
        assert (response.json()["given_by"], response.json()["ai"]) == ("owner", None)
        (event,) = audited(session, Action.VERDICT_CHANGED)
        assert event.detail is not None
        assert event.detail["verdict_id"] == rule.id
        assert audited(session, Action.VERDICT_TAKEN_BACK_FROM_AI) == []

    def test_changing_it_makes_it_theirs(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        rule = self.given_by_ai(session, settings)

        response = client.patch(
            f"{BASE}/{rule.id}", json={"verdict": "low_priority"}, headers=headers(csrf_token)
        )

        assert (response.json()["given_by"], response.json()["ai"]) == ("owner", None)

    def test_a_note_alone_makes_it_theirs_too(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        rule = self.given_by_ai(session, settings)

        response = client.patch(
            f"{BASE}/{rule.id}", json={"note": "Yes, mine"}, headers=headers(csrf_token)
        )

        assert response.json()["given_by"] == "owner"
        assert response.json()["note"] == "Yes, mine"

    def test_saying_nothing_new_of_a_verdict_the_owners_changes_nothing(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        give(client, csrf_token, address=ATTACKER, note="mine")

        response = give(client, csrf_token, address=ATTACKER, note="mine")

        assert response.status_code == 200
        assert audited(session, Action.VERDICT_CHANGED) == []

    def test_taking_it_back_says_so_and_tells_the_ai_not_to_do_it_again(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        rule = self.given_by_ai(session, settings)
        incident = session.scalars(select(Incident)).one()
        assert incident.verdict == "not_suspicious"

        response = client.delete(f"{BASE}/{rule.id}", headers=headers(csrf_token))

        assert response.status_code == 204
        session.expire_all()
        assert session.scalars(select(VerdictRule)).all() == []
        assert incident.verdict is None
        (event,) = audited(session, Action.VERDICT_TAKEN_BACK_FROM_AI)
        assert event.detail is not None
        assert event.detail["verdict_id"] == rule.id
        assert audited(session, Action.VERDICT_REMOVED) == []
        (veto,) = session.scalars(select(AiClearVeto))
        assert (veto.source, veto.signature) == (rule.source, rule.signature)
