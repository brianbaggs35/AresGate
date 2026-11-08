"""The alerts log: what became of each message, listed, counted and kept for a while."""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.alerts import log
from app.config import Settings
from app.models import AlertDelivery, AlertDestination, Incident, User
from tests.test_alerts_api import ADDRESS, add

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
BASE = "/api/alerts/deliveries"


def destination(session: Session, name: str = "Security") -> AlertDestination:
    row = AlertDestination(kind="discord", name=name, hint="…6789")
    session.add(row)
    session.flush()
    return row


def delivery(session: Session, row: AlertDestination, **changes: Any) -> AlertDelivery:
    fields: dict[str, Any] = {
        "destination_id": row.id,
        "reason": "new",
        "key": f"k{len(changes)}-{id(changes)}",
        "state": "sent",
        "title": "A scan",
        "severity": 3,
        "confidence": 70,
        "created_at": NOW,
        "due_at": NOW,
    }
    fields.update(changes)
    made = AlertDelivery(**fields)
    session.add(made)
    session.flush()
    return made


class TestListing:
    def test_the_newest_come_first_with_the_name_of_their_destination(
        self, session: Session
    ) -> None:
        a, b = destination(session, "A"), destination(session, "B")
        first = delivery(session, a, key="1")
        second = delivery(session, b, key="2")

        found = log.listing(session)

        assert [(row.id, name) for row, name in found] == [(second.id, "B"), (first.id, "A")]

    def test_it_can_be_narrowed_to_a_destination_or_a_state(self, session: Session) -> None:
        a, b = destination(session, "A"), destination(session, "B")
        delivery(session, a, key="1", state="sent")
        failed = delivery(session, a, key="2", state="failed")
        delivery(session, b, key="3", state="failed")

        found = log.listing(session, destination_id=a.id, state="failed")

        assert [row.id for row, _ in found] == [failed.id]

    def test_a_page_ends_where_the_next_begins(self, session: Session) -> None:
        a = destination(session)
        made = [delivery(session, a, key=str(number)) for number in range(5)]

        first = log.listing(session, limit=2)
        second = log.listing(session, before=first[-1][0].id, limit=2)

        assert [row.id for row, _ in first] == [made[4].id, made[3].id]
        assert [row.id for row, _ in second] == [made[2].id, made[1].id]

    def test_a_page_is_never_longer_than_the_most(self, session: Session) -> None:
        a = destination(session)
        for number in range(3):
            delivery(session, a, key=str(number))

        assert len(log.listing(session, limit=log.MAX_PAGE + 100)) == 3

    def test_it_counts_the_messages_in_each_state(self, session: Session) -> None:
        a, b = destination(session, "A"), destination(session, "B")
        delivery(session, a, key="1", state="sent")
        delivery(session, a, key="2", state="sent")
        delivery(session, b, key="3", state="failed")

        assert log.counts(session) == {"sent": 2, "failed": 1}
        assert log.counts(session, a.id) == {"sent": 2}


class TestThePage:
    def test_it_is_only_for_someone_signed_in(self, client: TestClient, account: User) -> None:
        assert client.get(BASE).status_code == 401

    def test_it_lists_what_was_sent_and_why_not(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        row = destination(session)
        incident = Incident(
            subject="93.184.216.34",
            title="A scan",
            severity=3,
            confidence=70,
            first_seen_at=NOW,
            last_seen_at=NOW,
            top_source="wazuh",
            top_summary="x",
        )
        session.add(incident)
        session.flush()
        delivery(session, row, key="1", incident_id=incident.id, sent_at=NOW, attempts=1)
        delivery(
            session,
            row,
            key="2",
            kind="summary",
            reason="limit",
            state="queued",
            covers=4,
            severity=0,
            note="Waiting.",
        )
        session.commit()

        response = client.get(BASE)

        assert response.status_code == 200
        body = response.json()
        assert body["counts"] == {"sent": 1, "queued": 1}
        assert body["next_before"] is None
        summary, told = body["items"]
        assert (summary["kind"], summary["reason"], summary["covers"], summary["severity"]) == (
            "summary",
            "limit",
            4,
            "info",
        )
        assert summary["incident_id"] is None
        assert (told["destination"], told["state"], told["severity"], told["attempts"]) == (
            "Security",
            "sent",
            "high",
            1,
        )
        assert told["incident_id"] == incident.id
        assert told["sent_at"] == "2026-11-08T12:00:00Z"

    def test_it_pages_and_filters(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        row = destination(session)
        for number in range(3):
            delivery(session, row, key=str(number), state="failed" if number else "sent")
        session.commit()

        first = client.get(BASE, params={"limit": 2}).json()
        second = client.get(BASE, params={"limit": 2, "before": first["next_before"]}).json()
        failed = client.get(BASE, params={"state": "failed", "destination_id": row.id}).json()

        assert len(first["items"]) == 2
        assert first["next_before"] == first["items"][-1]["id"]
        assert len(second["items"]) == 1
        assert second["next_before"] is None
        assert [item["state"] for item in failed["items"]] == ["failed", "failed"]
        assert failed["counts"] == {"sent": 1, "failed": 2}

    def test_a_state_that_is_not_one_is_refused(self, client: TestClient, csrf_token: str) -> None:
        assert client.get(BASE, params={"state": "bogus"}).status_code == 422
        assert client.get(BASE, params={"limit": 0}).status_code == 422


class TestWhenItListens:
    def listening(self, session: Session) -> datetime:
        row = session.query(AlertDestination).one()
        session.refresh(row)
        return row.listening_since

    def test_a_new_destination_listens_from_now(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        add(client, csrf_token)

        assert abs(datetime.now(UTC) - self.listening(session)) < timedelta(seconds=30)

    def test_turning_it_on_again_or_changing_its_rules_starts_it_listening_again(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        added = add(client, csrf_token).json()
        row = session.query(AlertDestination).one()
        row.listening_since = NOW
        session.commit()
        headers = {"X-CSRF-Token": csrf_token}

        client.patch(
            f"/api/alerts/destinations/{added['id']}", json={"enabled": False}, headers=headers
        )
        assert self.listening(session) == NOW
        client.patch(
            f"/api/alerts/destinations/{added['id']}", json={"enabled": True}, headers=headers
        )
        assert self.listening(session) > NOW
        row.listening_since = NOW
        session.commit()
        client.put(
            f"/api/alerts/destinations/{added['id']}/rules",
            json={**added["rules"], "min_confidence": 20},
            headers=headers,
        )
        assert self.listening(session) > NOW
        assert ADDRESS  # the address stays sealed: nothing here returns it
