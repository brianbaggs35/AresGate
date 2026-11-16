"""Trends: what the pages that list the present show of how things have been going."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import trends
from app.config import Settings
from app.models import AlertDelivery, AlertDestination, ApiCall, IncidentFamily, User, utcnow
from e2e import factories
from e2e.factories import EventSpec
from tests.test_alerts_api import incident

BASE = "/api/trends"
MOMENT = datetime(2026, 11, 16, 14, 35, 20, tzinfo=UTC)


def family(session: Session, number: int) -> IncidentFamily:
    made = IncidentFamily(
        key=f"{number:040d}", source="wazuh", label=f"Scan {number}", reach="internet"
    )
    session.add(made)
    session.commit()
    return made


class TestTheBuckets:
    def test_hours_end_with_the_one_under_way(self) -> None:
        found = trends.starts(MOMENT, "hour", 3)

        assert [moment.hour for moment in found] == [12, 13, 14]
        assert all(moment.minute == 0 for moment in found)

    def test_days_start_at_midnight_utc(self) -> None:
        found = trends.starts(MOMENT, "day", 2)

        assert found == [
            datetime(2026, 11, 15, tzinfo=UTC),
            datetime(2026, 11, 16, tzinfo=UTC),
        ]


def test_it_is_only_for_someone_signed_in(client: TestClient, account: User) -> None:
    paths = [
        "/deliveries",
        "/addresses?address=192.168.1.20",
        "/kinds?id=1",
        "/integrations",
    ]

    assert [client.get(BASE + path).status_code for path in paths] == [401] * 4


class TestDeliveries:
    def deliver(
        self, session: Session, destination: AlertDestination, hours_ago: float, **changes: Any
    ) -> None:
        session.add(
            AlertDelivery(
                destination_id=destination.id,
                reason="new",
                key=f"k{hours_ago}-{len(changes)}-{id(changes)}",
                state=changes.pop("state", "sent"),
                title="A scan",
                severity=changes.pop("severity", 3),
                created_at=utcnow() - timedelta(hours=hours_ago),
                due_at=utcnow(),
                **changes,
            )
        )

    def test_counts_the_messages_of_each_hour_by_severity(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        first = AlertDestination(kind="discord", name="A", hint="…1")
        session.add(first)
        session.flush()
        self.deliver(session, first, 0.0, severity=4)
        self.deliver(session, first, 0.0, severity=4)
        self.deliver(session, first, 5.0, severity=1)
        self.deliver(session, first, 400.0)
        session.commit()

        found: Any = client.get(f"{BASE}/deliveries?hours=12").json()

        assert len(found["times"]) == 12
        assert found["step"] == "hour"
        assert found["severities"]["critical"][-1] == 2
        assert sum(found["severities"]["low"]) == 1
        assert sum(found["severities"]["high"]) == 0
        assert sum(sum(counts) for counts in found["severities"].values()) == 3

    def test_follows_the_destination_and_the_state_of_the_page(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        one = AlertDestination(kind="discord", name="A", hint="…1")
        two = AlertDestination(kind="discord", name="B", hint="…2")
        session.add_all([one, two])
        session.flush()
        self.deliver(session, one, 1.0)
        self.deliver(session, one, 1.0, state="failed")
        self.deliver(session, two, 1.0)
        session.commit()

        def total(query: str) -> int:
            found: Any = client.get(f"{BASE}/deliveries?hours=6&{query}").json()
            return sum(sum(counts) for counts in found["severities"].values())

        assert total("destination_id=" + str(one.id)) == 2
        assert total(f"destination_id={one.id}&state=failed") == 1
        assert total("state=sent") == 2

    def test_asks_for_at_least_two_hours_and_at_most_a_week(
        self, client: TestClient, csrf_token: str
    ) -> None:
        assert client.get(f"{BASE}/deliveries?hours=1").status_code == 422
        assert client.get(f"{BASE}/deliveries?hours=169").status_code == 422


class TestAddresses:
    @pytest.fixture(autouse=True)
    def events(self, session: Session, settings: Settings) -> None:
        factories.events(
            session,
            settings,
            utcnow(),
            [
                EventSpec(src_address="203.0.113.9", dst_address="192.168.1.20", repeat=3),
                EventSpec(
                    src_address="192.168.1.20",
                    dst_address="93.184.216.34",
                    seconds_ago=3 * 86400,
                    repeat=2,
                ),
            ],
        )

    def test_counts_the_connections_to_and_from_each_address_by_day(
        self, client: TestClient, csrf_token: str
    ) -> None:
        found: Any = client.get(
            f"{BASE}/addresses?address=192.168.1.20&address=198.51.100.1"
        ).json()

        assert len(found["times"]) == 7
        assert found["step"] == "day"
        laptop = found["items"]["192.168.1.20"]
        assert sum(laptop["incoming"]) == 3
        assert sum(laptop["outgoing"]) == 2
        assert laptop["incoming"][-1] + laptop["incoming"][-2] == 3
        assert found["items"]["198.51.100.1"] == {"incoming": [0] * 7, "outgoing": [0] * 7}

    def test_can_count_by_the_hour_for_a_week(self, client: TestClient, csrf_token: str) -> None:
        found: Any = client.get(f"{BASE}/addresses?address=192.168.1.20&step=hour&count=168").json()

        assert len(found["times"]) == 168
        assert sum(found["items"]["192.168.1.20"]["incoming"]) == 3

    def test_writes_an_address_one_way(self, client: TestClient, csrf_token: str) -> None:
        found: Any = client.get(
            f"{BASE}/addresses?address=2001:DB8:0:0:0:0:0:1&address=2001:db8::1"
        ).json()

        assert list(found["items"]) == ["2001:db8::1"]

    def test_refuses_what_is_not_an_address(self, client: TestClient, csrf_token: str) -> None:
        assert client.get(f"{BASE}/addresses?address=laptop").status_code == 422
        assert client.get(f"{BASE}/addresses").status_code == 422

    def test_keeps_days_to_a_quarter(self, client: TestClient, csrf_token: str) -> None:
        found: Any = client.get(f"{BASE}/addresses?address=192.168.1.20&count=168").json()

        assert len(found["times"]) == 90


class TestKinds:
    def test_counts_the_incidents_of_each_kind_that_began_each_day(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        scan, brute = family(session, 1), family(session, 2)
        incident(session, family_id=scan.id, first_seen_at=utcnow() - timedelta(minutes=5))
        incident(session, family_id=scan.id, first_seen_at=utcnow() - timedelta(minutes=6))
        incident(session, family_id=scan.id, first_seen_at=utcnow() - timedelta(days=3))
        incident(session, family_id=scan.id, first_seen_at=utcnow() - timedelta(days=30))
        incident(session, family_id=None)

        found: Any = client.get(f"{BASE}/kinds?id={scan.id}&id={brute.id}").json()

        assert len(found["times"]) == 7
        assert sum(found["items"][str(scan.id)]) == 3
        assert found["items"][str(brute.id)] == [0] * 7

    def test_wants_a_kind_and_at_most_ninety_days(
        self, client: TestClient, csrf_token: str
    ) -> None:
        assert client.get(f"{BASE}/kinds").status_code == 422
        assert client.get(f"{BASE}/kinds?id=1&days=91").status_code == 422


class TestIntegrations:
    def call(self, session: Session, name: str, hours_ago: float, error: str | None) -> None:
        session.add(
            ApiCall(
                occurred_at=utcnow() - timedelta(hours=hours_ago),
                integration=name,
                connection="api",
                method="GET",
                path="/status",
                status_code=None if error else 200,
                duration_ms=5,
                error=error,
            )
        )

    def test_says_how_each_hour_went(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        self.call(session, "opnsense", 0.0, None)
        self.call(session, "opnsense", 2.0, None)
        self.call(session, "opnsense", 2.0, "It timed out.")
        self.call(session, "wazuh", 5.0, None)
        self.call(session, "wazuh", 100.0, "Too old to show.")
        session.commit()

        found: Any = client.get(f"{BASE}/integrations?hours=6").json()

        assert len(found["times"]) == 6
        opnsense = found["items"]["opnsense"]
        assert opnsense[-1] == "ok"
        assert opnsense[-3] == "problem"
        assert opnsense[-2] == "none"
        assert found["items"]["wazuh"].count("ok") == 1
        assert set(found["items"]) == {"opnsense", "wazuh"}

    def test_is_empty_before_anything_was_called(self, client: TestClient, csrf_token: str) -> None:
        assert client.get(f"{BASE}/integrations").json()["items"] == {}
