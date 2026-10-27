from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import dashboard
from app.api.dashboard import build
from app.config import Settings
from app.events.event import Severity
from app.events.store import record as record_events
from app.models import User, utcnow
from tests.helpers import new_event
from tests.test_dashboard import NOW, alert, blocked_event, incident

BASE = "/api/dashboard"


def test_it_is_only_for_someone_signed_in(client: TestClient, account: User) -> None:
    assert client.get(BASE).status_code == 401


def test_an_install_with_nothing_stored_still_has_a_dashboard(
    client: TestClient, csrf_token: str
) -> None:
    response = client.get(BASE)

    assert response.status_code == 200
    body = response.json()
    assert body["window"]["key"] == "24h"
    assert len(body["window"]["buckets"]) == 24
    assert len(body["window"]["traffic_buckets"]) == 96
    assert body["alerts"]["total"] == 0
    assert body["alerts"]["highest"] is None
    assert set(body["alerts"]["by_severity"]) == {"info", "low", "medium", "high", "critical"}
    assert body["recent_alerts"] == []
    assert body["blocked"] == {"total": 0, "previous": 0, "per_bucket": [0] * 24, "top_sources": []}
    assert body["traffic"] == []
    assert body["devices"] == {"total": 0, "new": 0}
    assert body["marks"] == []


def test_the_last_week_is_cut_into_longer_buckets(client: TestClient, csrf_token: str) -> None:
    body = client.get(BASE, params={"window": "7d"}).json()

    assert body["window"]["key"] == "7d"
    assert len(body["window"]["buckets"]) == 28
    assert len(body["window"]["traffic_buckets"]) == 168


def test_a_window_nobody_offers_is_refused(client: TestClient, csrf_token: str) -> None:
    assert client.get(BASE, params={"window": "30d"}).status_code == 422


def test_what_was_stored_is_counted(
    client: TestClient, csrf_token: str, session: Session, settings: Settings
) -> None:
    now = utcnow()
    record_events(
        session,
        settings,
        [
            new_event(severity=Severity.HIGH, occurred_at=now, identity=("a",), summary="Scan"),
            blocked_event("203.0.113.9", now, "b"),
        ],
        now,
    )
    session.commit()

    body = client.get(BASE).json()

    assert body["alerts"]["total"] == 1
    assert body["alerts"]["highest"] == "high"
    assert sum(body["alerts"]["by_severity"]["high"]) == 1
    assert body["blocked"]["total"] == 1
    assert body["blocked"]["top_sources"] == [{"address": "203.0.113.9", "count": 1}]
    [latest] = body["recent_alerts"]
    assert latest["summary"] == "Scan"
    assert latest["severity"] == "high"


class TestBuild:
    """The numbers at a time that is set, so the buckets they fall in can be told."""

    def test_an_alert_is_given_with_where_it_came_from_and_who_it_names(
        self, session: Session, settings: Settings
    ) -> None:
        record_events(
            session,
            settings,
            [
                alert(
                    Severity.CRITICAL,
                    NOW - timedelta(minutes=5),
                    "x",
                    source="ntopng",
                    summary="Remote to local insecure flow",
                    signature="remote_to_local_insecure_flow",
                    src_address="198.51.100.4",
                    dst_address="192.168.1.20",
                ),
                alert(Severity.LOW, NOW - timedelta(minutes=30), "y", source="homebrew"),
            ],
            NOW,
        )
        session.commit()

        found = build(session, "24h", NOW)

        assert found.alerts.highest == "critical"
        first, second = found.recent_alerts
        assert (first.source, first.source_name) == ("ntopng", "ntopng")
        assert first.severity == "critical"
        assert first.signature == "remote_to_local_insecure_flow"
        assert (first.src_address, first.dst_address) == ("198.51.100.4", "192.168.1.20")
        # An integration the app has never heard of is called what it calls itself.
        assert (second.source, second.source_name) == ("homebrew", "homebrew")
        assert (second.src_address, second.dst_address, second.signature) == (None, None, None)

    def test_the_last_bucket_is_the_one_still_filling(
        self, session: Session, settings: Settings
    ) -> None:
        record_events(
            session, settings, [alert(Severity.MEDIUM, NOW - timedelta(minutes=1), "z")], NOW
        )
        session.commit()

        found = build(session, "24h", NOW)

        assert found.window.end == dashboard.window("24h", NOW).end
        assert found.window.buckets[-1] == found.window.end - timedelta(hours=1)
        assert found.alerts.by_severity["medium"][-1] == 1

    def test_an_incident_is_marked_with_what_the_flag_says(self, session: Session) -> None:
        began = NOW - timedelta(hours=3)
        session.add(
            incident(
                "93.184.216.34",
                began,
                NOW - timedelta(hours=2),
                severity=int(Severity.CRITICAL),
                confidence=85,
                status="investigating",
                banned=True,
            )
        )
        session.commit()

        found = build(session, "24h", NOW)

        [mark] = found.marks
        assert (mark.title, mark.subject) == ("About 93.184.216.34", "93.184.216.34")
        assert (mark.severity, mark.confidence, mark.status) == ("critical", 85, "investigating")
        assert (mark.first_seen_at, mark.last_seen_at) == (began, NOW - timedelta(hours=2))
        assert mark.banned is True
