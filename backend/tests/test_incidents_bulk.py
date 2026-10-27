from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.api import incidents
from app.audit import Action, Outcome
from app.config import Settings
from app.events.event import Severity
from app.incidents import bulk, search
from app.models import AuditEvent, Incident, User, VerdictRule
from tests.test_incidents_engine import (
    ATTACKER,
    NOW,
    OTHER_ATTACKER,
    alert,
    run,
    store,
)

BASE = "/api/incidents/bulk"
UNDO = f"{BASE}/undo"
THIRD = "1.1.1.1"
DAY = timedelta(days=1)


def headers(token: str) -> dict[str, str]:
    return {"X-CSRF-Token": token}


def change(client: TestClient, token: str, **body: Any) -> Any:
    return client.post(BASE, json=body, headers=headers(token))


def audited(session: Session, action: Action) -> list[AuditEvent]:
    session.expire_all()
    return list(
        session.scalars(
            select(AuditEvent).where(AuditEvent.action == action).order_by(AuditEvent.id)
        )
    )


def seed(session: Session, settings: Settings) -> list[Incident]:
    """Three attackers, in blocks of their own: one that scanned (two signals), one that
    brute-forced, and one whose alert is the weakest. Their incidents, the oldest id first."""
    store(
        session,
        settings,
        alert(NOW, n=1, severity=Severity.HIGH),
        alert(NOW + timedelta(minutes=1), n=2, severity=Severity.HIGH),
        alert(NOW, n=3, src_address=OTHER_ATTACKER, severity=Severity.MEDIUM, signature="Brute"),
        alert(NOW, n=4, src_address=THIRD, severity=Severity.LOW),
    )
    run(session)
    return found(session)


def found(session: Session) -> list[Incident]:
    session.expire_all()
    return list(session.scalars(select(Incident).order_by(Incident.id)))


def ids(incidents: list[Incident], *subjects: str) -> list[int]:
    return [incident.id for incident in incidents if incident.subject in subjects]


def test_it_is_only_for_someone_signed_in(client: TestClient, account: User) -> None:
    assert client.post(BASE, json={"ids": [1], "status": "resolved"}).status_code == 401
    assert client.post(UNDO, json={}).status_code == 401


class TestChangingStatuses:
    def test_it_changes_them_all_and_keeps_one_record(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        everything = seed(session, settings)
        picked = ids(everything, ATTACKER, OTHER_ATTACKER)

        response = change(client, csrf_token, ids=picked, status="resolved")

        assert response.status_code == 200
        body = response.json()
        assert body["preview"] is False
        assert body["incidents"] == 2
        assert body["signals"] == 3
        assert body["changed"] == 2
        assert body["skipped"] == 0
        assert body["verdicts"] == 0
        assert body["undo"] == {"statuses": {"open": picked}, "rules": []}
        rows = {incident.subject: incident for incident in found(session)}
        assert rows[ATTACKER].status == "resolved"
        assert rows[ATTACKER].status_changed_at is not None
        assert rows[OTHER_ATTACKER].status == "resolved"
        assert rows[THIRD].status == "open"
        assert rows[THIRD].status_changed_at is None
        (record,) = audited(session, Action.INCIDENTS_CHANGED)
        assert record.outcome == Outcome.SUCCESS
        assert record.username == "brian"
        assert record.detail == {
            "change": "status",
            "to": "resolved",
            "incidents": 2,
            "ids": ",".join(str(number) for number in picked),
        }

    def test_the_ones_that_already_are_so_are_left_alone(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        everything = seed(session, settings)
        change(client, csrf_token, ids=ids(everything, ATTACKER), status="investigating")

        response = change(
            client,
            csrf_token,
            ids=ids(everything, ATTACKER, OTHER_ATTACKER),
            status="investigating",
        )

        body = response.json()
        assert (body["incidents"], body["changed"]) == (2, 1)
        assert body["undo"]["statuses"] == {"open": ids(everything, OTHER_ATTACKER)}
        assert len(audited(session, Action.INCIDENTS_CHANGED)) == 2

    def test_saying_what_they_all_are_changes_nothing_and_says_nothing(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        everything = seed(session, settings)

        response = change(client, csrf_token, ids=ids(everything, ATTACKER), status="open")

        body = response.json()
        assert (body["incidents"], body["changed"], body["undo"]) == (1, 0, None)
        assert audited(session, Action.INCIDENTS_CHANGED) == []

    def test_asking_what_it_would_do_changes_nothing(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        everything = seed(session, settings)

        response = change(
            client, csrf_token, ids=ids(everything, ATTACKER), status="dismissed", preview=True
        )

        body = response.json()
        assert body["preview"] is True
        assert (body["incidents"], body["signals"], body["changed"]) == (1, 2, 1)
        assert body["undo"] is None
        assert {incident.status for incident in found(session)} == {"open"}
        assert audited(session, Action.INCIDENTS_CHANGED) == []

    def test_an_incident_that_is_gone_is_not_counted(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        everything = seed(session, settings)

        response = change(
            client, csrf_token, ids=[*ids(everything, ATTACKER), 987654], status="resolved"
        )

        assert (response.json()["incidents"], response.json()["changed"]) == (1, 1)

    def test_it_changes_all_that_match_what_a_list_was_asked(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        seed(session, settings)

        response = change(
            client,
            csrf_token,
            matching={"min_severity": "high", "status": ["open"]},
            status="resolved",
        )

        body = response.json()
        assert (body["incidents"], body["changed"]) == (1, 1)
        assert {i.subject for i in found(session) if i.status == "resolved"} == {ATTACKER}

    def test_what_matches_can_be_said_in_words(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        seed(session, settings)

        response = change(
            client,
            csrf_token,
            matching={"q": f"-address:{ATTACKER} severity<high", "tz": "America/Halifax"},
            status="dismissed",
        )

        assert (response.json()["incidents"], response.json()["changed"]) == (2, 2)
        assert {i.subject for i in found(session) if i.status == "dismissed"} == {
            OTHER_ATTACKER,
            THIRD,
        }

    def test_what_matches_can_be_the_ones_a_verdict_was_said_of(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        everything = seed(session, settings)
        change(client, csrf_token, ids=ids(everything, THIRD), verdict="not_suspicious")

        asked = change(
            client, csrf_token, matching={"verdict": ["not_suspicious"]}, status="resolved"
        )
        rest = change(client, csrf_token, matching={"verdict": ["none"]}, status="dismissed")

        assert asked.json()["incidents"] == 1
        assert rest.json()["incidents"] == 2
        assert {i.status for i in found(session)} == {"resolved", "dismissed"}

    def test_it_will_not_change_more_than_can_be_looked_over(
        self,
        client: TestClient,
        csrf_token: str,
        session: Session,
        settings: Settings,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        seed(session, settings)
        monkeypatch.setattr(bulk, "MAX_INCIDENTS", 2)

        response = change(client, csrf_token, matching={}, status="resolved")

        assert response.status_code == 422
        assert response.json()["detail"] == (
            "That is 3 incidents, and 2 is the most that can be changed at once. "
            "Narrow it down first."
        )
        assert {incident.status for incident in found(session)} == {"open"}

    @pytest.mark.parametrize(
        "matching",
        [{"q": "sevrity:high"}, {"tz": "Mars/Olympus"}, {"min_severity": "huge"}],
    )
    def test_what_matches_has_to_make_sense(
        self, client: TestClient, csrf_token: str, matching: dict[str, Any]
    ) -> None:
        response = change(client, csrf_token, matching=matching, status="resolved")

        assert response.status_code == 422

    def test_a_search_that_takes_too_long_is_stopped(
        self,
        client: TestClient,
        csrf_token: str,
        session: Session,
        settings: Settings,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        seed(session, settings)
        slow = func.pg_sleep(1).is_not(None)

        def parse(text: str, context: search.Context) -> search.Search:
            return search.Search((search.Term(None, False, "Slow", 0, 1, slow),))

        monkeypatch.setattr(search, "parse", parse)
        monkeypatch.setattr(incidents, "SEARCH_TIMEOUT_MS", 50)

        response = change(client, csrf_token, matching={"q": "x"}, status="resolved")

        assert response.status_code == 422
        assert response.json()["detail"].startswith("That search took too long.")
        assert {incident.status for incident in found(session)} == {"open"}

    def test_what_it_does_to_what_it_found_is_not_timed(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        seed(session, settings)

        change(client, csrf_token, matching={"q": "severity>=low"}, status="resolved")

        assert session.scalar(select(func.current_setting("statement_timeout"))) == "0"

    @pytest.mark.parametrize(
        "body",
        [
            {"status": "resolved"},
            {"ids": [1], "matching": {}, "status": "resolved"},
            {"ids": [1]},
            {"ids": [1], "status": "resolved", "verdict": "threat"},
            {"ids": [1], "status": "resolved", "note": "x"},
            {"ids": [], "status": "resolved"},
            {"ids": [0], "status": "resolved"},
            {"ids": list(range(1, 1002)), "status": "resolved"},
            {"ids": [1], "status": "ignored"},
            {"ids": [1], "status": "resolved", "title": "x"},
            {"ids": [1], "verdict": "fine"},
            {"matching": {"status": ["gone"]}, "status": "resolved"},
            {"matching": {"min_confidence": 101}, "status": "resolved"},
        ],
    )
    def test_nonsense_is_refused(
        self, client: TestClient, csrf_token: str, session: Session, body: dict[str, Any]
    ) -> None:
        response = client.post(BASE, json=body, headers=headers(csrf_token))

        assert response.status_code == 422
        assert audited(session, Action.INCIDENTS_CHANGED) == []

    def test_the_same_incident_picked_twice_is_one(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        everything = seed(session, settings)
        one = ids(everything, ATTACKER)[0]

        response = change(client, csrf_token, ids=[one, one], status="resolved")

        assert (response.json()["incidents"], response.json()["changed"]) == (1, 1)

    def test_it_needs_the_security_token(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        everything = seed(session, settings)

        response = client.post(BASE, json={"ids": ids(everything, ATTACKER), "status": "resolved"})

        assert response.status_code == 403
        assert {incident.status for incident in found(session)} == {"open"}


class TestGivingVerdicts:
    def test_a_verdict_is_said_of_what_each_is_about_and_judges_them_at_once(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        everything = seed(session, settings)
        picked = ids(everything, ATTACKER, OTHER_ATTACKER)

        response = change(
            client, csrf_token, ids=picked, verdict="not_suspicious", note="  The scanner I run  "
        )

        assert response.status_code == 200
        body = response.json()
        assert (body["incidents"], body["signals"], body["changed"]) == (2, 3, 2)
        assert (body["skipped"], body["verdicts"]) == (0, 2)
        rules = {str(rule.address): rule for rule in session.scalars(select(VerdictRule))}
        assert set(rules) == {ATTACKER, OTHER_ATTACKER}
        assert {rule.verdict for rule in rules.values()} == {"not_suspicious"}
        assert {rule.note for rule in rules.values()} == {"The scanner I run"}
        assert body["undo"]["statuses"] == {}
        assert {(back["id"], back["replaced"]) for back in body["undo"]["rules"]} == {
            (rules[ATTACKER].id, None),
            (rules[OTHER_ATTACKER].id, None),
        }
        rows = {incident.subject: incident for incident in found(session)}
        assert rows[ATTACKER].verdict == "not_suspicious"
        assert rows[OTHER_ATTACKER].verdict == "not_suspicious"
        assert rows[THIRD].verdict is None
        (record,) = audited(session, Action.INCIDENTS_CHANGED)
        assert record.detail is not None
        assert record.detail["change"] == "verdict"
        assert record.detail["verdict"] == "not_suspicious"
        assert record.detail["verdicts"] == 2
        assert record.detail["incidents"] == 2
        assert record.detail["ids"] == ",".join(str(number) for number in sorted(picked))

    def test_one_verdict_covers_the_incidents_about_the_same_address(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        store(
            session,
            settings,
            alert(NOW, n=1, severity=Severity.HIGH),
            alert(NOW + 3 * DAY, n=2, severity=Severity.HIGH),
        )
        run(session)
        run(session, NOW + 3 * DAY + timedelta(hours=12))
        both = found(session)
        assert len(both) == 2

        response = change(
            client, csrf_token, ids=[incident.id for incident in both], verdict="threat"
        )

        body = response.json()
        assert (body["incidents"], body["changed"], body["verdicts"]) == (2, 2, 1)
        assert session.scalar(select(func.count()).select_from(VerdictRule)) == 1
        assert {incident.verdict for incident in found(session)} == {"threat"}

    def test_an_incident_about_a_rule_is_judged_by_its_first_alert(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        store(
            session,
            settings,
            alert(NOW, n=1, src_address=None, dst_address=None, signature="Rule 5710"),
            alert(
                NOW + timedelta(minutes=2),
                n=2,
                src_address=None,
                dst_address=None,
                signature="Rule 5710",
            ),
        )
        run(session)
        (incident,) = found(session)
        assert incident.subject.startswith("rule:")

        response = change(client, csrf_token, ids=[incident.id], verdict="low_priority")

        assert response.json()["verdicts"] == 1
        rule = session.scalars(select(VerdictRule)).one()
        assert (rule.address, rule.source, rule.signature) == (None, "wazuh", "Rule 5710")
        assert found(session)[0].verdict == "low_priority"

    def test_what_names_no_address_and_no_alert_is_left_out_and_said_so(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        store(
            session, settings, alert(NOW, n=1, src_address=None, dst_address=None, signature=None)
        )
        run(session)
        (incident,) = found(session)
        assert incident.subject.startswith("rule:")

        response = change(client, csrf_token, ids=[incident.id], verdict="threat")

        body = response.json()
        assert (body["incidents"], body["changed"], body["skipped"], body["verdicts"]) == (
            1,
            0,
            1,
            0,
        )
        assert body["undo"] is None
        assert session.scalars(select(VerdictRule)).all() == []
        assert audited(session, Action.INCIDENTS_CHANGED) == []

    def test_a_verdict_that_says_so_already_is_left_alone(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        everything = seed(session, settings)
        picked = ids(everything, ATTACKER)
        change(client, csrf_token, ids=picked, verdict="threat")

        response = change(client, csrf_token, ids=picked, verdict="threat")

        body = response.json()
        assert (body["incidents"], body["changed"], body["verdicts"], body["undo"]) == (
            1,
            0,
            0,
            None,
        )
        assert len(audited(session, Action.INCIDENTS_CHANGED)) == 1

    def test_one_that_says_another_is_changed_and_remembers_what_it_said(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        everything = seed(session, settings)
        picked = ids(everything, ATTACKER)
        change(client, csrf_token, ids=picked, verdict="not_suspicious", note="First")

        response = change(client, csrf_token, ids=picked, verdict="threat")

        body = response.json()
        assert (body["changed"], body["verdicts"]) == (1, 1)
        rule = session.scalars(select(VerdictRule)).one()
        session.refresh(rule)
        assert (rule.verdict, rule.note) == ("threat", "First")
        assert body["undo"]["rules"] == [{"id": rule.id, "replaced": "not_suspicious"}]

    def test_a_new_note_is_kept_though_there_is_nothing_to_take_back(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        everything = seed(session, settings)
        picked = ids(everything, ATTACKER)
        change(client, csrf_token, ids=picked, verdict="threat", note="First")

        response = change(client, csrf_token, ids=picked, verdict="threat", note="Second")

        body = response.json()
        assert (body["changed"], body["verdicts"], body["undo"]) == (1, 1, None)
        rule = session.scalars(select(VerdictRule)).one()
        session.refresh(rule)
        assert rule.note == "Second"
        assert len(audited(session, Action.INCIDENTS_CHANGED)) == 2

    def test_asking_what_it_would_do_makes_no_verdict(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        everything = seed(session, settings)

        response = change(
            client,
            csrf_token,
            ids=ids(everything, ATTACKER, THIRD),
            verdict="not_suspicious",
            preview=True,
        )

        body = response.json()
        assert (body["incidents"], body["changed"], body["verdicts"]) == (2, 2, 2)
        assert body["undo"] is None
        assert session.scalars(select(VerdictRule)).all() == []
        assert {incident.verdict for incident in found(session)} == {None}

    def test_asking_what_it_would_do_leaves_a_verdict_that_exists_as_it_is(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        everything = seed(session, settings)
        picked = ids(everything, ATTACKER)
        change(client, csrf_token, ids=picked, verdict="threat")

        response = change(client, csrf_token, ids=picked, verdict="low_priority", preview=True)

        assert (response.json()["changed"], response.json()["verdicts"]) == (1, 1)
        assert session.scalars(select(VerdictRule)).one().verdict == "threat"
        assert len(audited(session, Action.INCIDENTS_CHANGED)) == 1


class TestTakingAChangeBack:
    def test_the_statuses_go_back_to_what_they_were(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        everything = seed(session, settings)
        change(client, csrf_token, ids=ids(everything, ATTACKER), status="investigating")
        done = change(
            client,
            csrf_token,
            ids=ids(everything, ATTACKER, OTHER_ATTACKER),
            status="resolved",
        ).json()

        response = client.post(UNDO, json=done["undo"], headers=headers(csrf_token))

        assert response.status_code == 200
        assert response.json() == {"incidents": 2, "verdicts": 0}
        rows = {incident.subject: incident.status for incident in found(session)}
        assert rows == {ATTACKER: "investigating", OTHER_ATTACKER: "open", THIRD: "open"}
        (record,) = audited(session, Action.INCIDENTS_CHANGE_UNDONE)
        assert record.detail == {"incidents": 2, "verdicts": 0}

    def test_the_verdicts_go_or_say_again_what_they_said(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        everything = seed(session, settings)
        change(client, csrf_token, ids=ids(everything, ATTACKER), verdict="not_suspicious")
        done = change(
            client,
            csrf_token,
            ids=ids(everything, ATTACKER, OTHER_ATTACKER),
            verdict="threat",
        ).json()

        response = client.post(UNDO, json=done["undo"], headers=headers(csrf_token))

        assert response.json() == {"incidents": 0, "verdicts": 2}
        rules = {str(rule.address): rule.verdict for rule in session.scalars(select(VerdictRule))}
        assert rules == {ATTACKER: "not_suspicious"}
        rows = {incident.subject: incident.verdict for incident in found(session)}
        assert rows == {ATTACKER: "not_suspicious", OTHER_ATTACKER: None, THIRD: None}

    def test_what_is_gone_is_not_missed(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        everything = seed(session, settings)
        done = change(client, csrf_token, ids=ids(everything, ATTACKER), verdict="threat").json()
        session.execute(delete(VerdictRule))
        session.commit()
        undo = {**done["undo"], "statuses": {"open": [987654]}}

        response = client.post(UNDO, json=undo, headers=headers(csrf_token))

        assert response.json() == {"incidents": 0, "verdicts": 0}
        assert audited(session, Action.INCIDENTS_CHANGE_UNDONE) == []

    def test_an_incident_that_is_already_as_it_was_is_not_counted(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        everything = seed(session, settings)

        response = client.post(
            UNDO,
            json={"statuses": {"open": ids(everything, ATTACKER)}},
            headers=headers(csrf_token),
        )

        assert response.json() == {"incidents": 0, "verdicts": 0}

    @pytest.mark.parametrize(
        "body",
        [
            {"statuses": {"gone": [1]}},
            {"statuses": {"open": []}},
            {"statuses": {"open": [0]}},
            {"rules": [{"id": 0}]},
            {"rules": [{"id": 1, "replaced": "fine"}]},
            {"rules": [{"id": 1}] * 1001},
            {"other": 1},
        ],
    )
    def test_nonsense_is_refused(
        self, client: TestClient, csrf_token: str, body: dict[str, Any]
    ) -> None:
        assert client.post(UNDO, json=body, headers=headers(csrf_token)).status_code == 422


def test_what_names_something_that_is_not_an_address_is_about_nothing() -> None:
    assert bulk.scope_of("not an address", None) is None
    assert bulk.scope_of("rule:wazuh:5710", None) is None
    assert bulk.scope_of("rule:wazuh:5710", ("wazuh", "Rule 5710")) == bulk.Scope(
        source="wazuh", signature="Rule 5710"
    )
