"""What is new since the owner last looked: counted for the account, on the server."""

from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import since
from app.models import DashboardVisit, Device, User, VerdictRule, utcnow
from e2e import factories
from tests.test_alerts_api import incident

BASE = "/api/dashboard"


def headers(token: str) -> dict[str, str]:
    return {"X-CSRF-Token": token}


def visit(session: Session, user: User, ago: timedelta) -> None:
    session.add(DashboardVisit(user_id=user.id, viewed_at=utcnow() - ago))
    session.commit()


def device(session: Session, hours_ago: int) -> None:
    session.add(
        Device(
            mac=f"00:11:22:33:44:{hours_ago:02x}",
            first_seen_at=utcnow() - timedelta(hours=hours_ago),
            last_seen_at=utcnow(),
        )
    )
    session.commit()


def clear(
    session: Session, hours_ago: int, given_by: str = "ai", address: str = "198.51.100.7"
) -> None:
    session.add(
        VerdictRule(
            verdict="not_suspicious",
            address=address,
            given_by=given_by,
            created_at=utcnow() - timedelta(hours=hours_ago),
        )
    )
    session.commit()


def test_it_is_only_for_someone_signed_in(client: TestClient, account: User) -> None:
    answers = [client.get(f"{BASE}/since"), client.post(f"{BASE}/seen")]

    assert [answer.status_code for answer in answers] == [401, 401]


class TestTheFirstVisit:
    def test_says_nothing_and_starts_the_count(
        self, client: TestClient, csrf_token: str, session: Session, account: User
    ) -> None:
        incident(session)

        first: Any = client.get(f"{BASE}/since").json()

        assert first["since"] is None
        assert first["total"] == 0
        assert session.get(DashboardVisit, account.id) is not None
        assert client.get(f"{BASE}/since").json()["since"] is not None


class TestWhatIsNew:
    def test_the_incidents_that_began_since_by_how_serious(
        self, client: TestClient, csrf_token: str, session: Session, account: User
    ) -> None:
        visit(session, account, timedelta(hours=3))
        incident(session, severity=4, first_seen_at=utcnow() - timedelta(hours=1))
        incident(session, severity=4, first_seen_at=utcnow() - timedelta(hours=2))
        incident(session, severity=2, first_seen_at=utcnow() - timedelta(minutes=5))
        incident(session, severity=3, first_seen_at=utcnow() - timedelta(hours=5))

        found: Any = client.get(f"{BASE}/since").json()

        assert found["incidents"] == {
            "info": 0,
            "low": 0,
            "medium": 1,
            "high": 0,
            "critical": 2,
        }
        assert found["total"] == 3

    def test_an_incident_the_owner_called_quiet_is_not_news(
        self, client: TestClient, csrf_token: str, session: Session, account: User
    ) -> None:
        visit(session, account, timedelta(hours=3))
        incident(session, severity=3, verdict="not_suspicious")
        incident(session, severity=3, verdict="low_priority")
        incident(session, severity=3, verdict="threat")
        incident(session, severity=3)

        assert client.get(f"{BASE}/since").json()["total"] == 2

    def test_what_the_ai_cleared_and_not_what_the_owner_did(
        self, client: TestClient, csrf_token: str, session: Session, account: User
    ) -> None:
        visit(session, account, timedelta(hours=3))
        clear(session, 1, address="198.51.100.1")
        clear(session, 2, "owner", address="198.51.100.2")
        clear(session, 5, address="198.51.100.3")

        assert client.get(f"{BASE}/since").json()["cleared_by_ai"] == 1

    def test_the_devices_that_appeared(
        self, client: TestClient, csrf_token: str, session: Session, account: User
    ) -> None:
        visit(session, account, timedelta(hours=3))
        device(session, 1)
        device(session, 2)
        device(session, 9)

        assert client.get(f"{BASE}/since").json()["new_devices"] == 2

    def test_nothing_new_is_nothing(
        self, client: TestClient, csrf_token: str, session: Session, account: User
    ) -> None:
        visit(session, account, timedelta(hours=3))

        found: Any = client.get(f"{BASE}/since").json()

        assert found["total"] == 0
        assert found["cleared_by_ai"] == found["new_devices"] == 0


class TestLookingNow:
    def test_looking_moves_the_mark_forward_so_it_is_not_news_again(
        self, client: TestClient, csrf_token: str, session: Session, account: User
    ) -> None:
        visit(session, account, timedelta(hours=3))
        incident(session, first_seen_at=utcnow() - timedelta(hours=1))
        assert client.get(f"{BASE}/since").json()["total"] == 1

        response = client.post(f"{BASE}/seen", headers=headers(csrf_token))

        assert response.status_code == 204
        assert client.get(f"{BASE}/since").json()["total"] == 0

    def test_a_first_look_is_kept_too(
        self, client: TestClient, csrf_token: str, session: Session, account: User
    ) -> None:
        client.post(f"{BASE}/seen", headers=headers(csrf_token))

        assert session.scalars(select(DashboardVisit)).one().user_id == account.id

    def test_it_needs_the_security_token(self, client: TestClient, csrf_token: str) -> None:
        assert client.post(f"{BASE}/seen").status_code == 403


class TestWhoseItIs:
    def test_another_accounts_visit_is_its_own(
        self, client: TestClient, csrf_token: str, session: Session, account: User
    ) -> None:
        someone = factories.account(session, username="someone-else")
        session.add(DashboardVisit(user_id=someone.id, viewed_at=utcnow() - timedelta(days=9)))
        session.commit()
        incident(session, first_seen_at=utcnow() - timedelta(days=1))

        first: Any = client.get(f"{BASE}/since").json()

        assert first["since"] is None
        assert since.of(session, someone.id, utcnow()).total == 1
