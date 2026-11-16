"""The lists as files: what the filters and the order show, in words, for the owner's zone."""

import csv
import io
import json
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import exporting
from app.api import exports
from app.audit import Action
from app.config import Settings
from app.models import AuditEvent
from tests.test_alerts_api import incident
from tests.test_alerts_log import delivery, destination
from tests.test_assets_api import stock as stock_assets
from tests.test_devices_api import stock as stock_devices


def table(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


def audited(session: Session) -> list[AuditEvent]:
    return list(
        session.scalars(select(AuditEvent).where(AuditEvent.action == Action.LIST_EXPORTED))
    )


def test_each_list_is_only_for_someone_signed_in(client: TestClient) -> None:
    paths = [
        "/api/incidents/export",
        "/api/alerts/deliveries/export",
        "/api/devices/export",
        "/api/assets/export",
    ]

    assert [client.get(path).status_code for path in paths] == [401] * 4


class TestIncidents:
    def test_the_incidents_are_in_words_as_csv(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        incident(session, title="=HYPERLINK(1)", severity=4)
        incident(session, subject="198.51.100.9", title="Scan from 198.51.100.9")

        response = client.get("/api/incidents/export", params={"order": "priority"})

        assert response.headers["content-type"] == "text/csv; charset=utf-8"
        rows = table(response.text)
        assert [row["Title"] for row in rows] == ["'=HYPERLINK(1)", "Scan from 198.51.100.9"]
        assert rows[0]["Severity"] == "critical"
        assert rows[0]["Status"] == "open"
        assert rows[0]["Signals"] == "3"
        assert rows[0]["Activity"] == "scan"
        assert set(rows[0]) == set(exports.INCIDENT_COLUMNS)

    def test_it_is_what_the_filters_show_and_not_all_of_them(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        incident(session, title="Open one")
        incident(session, title="Done one", status="resolved")

        rows = table(client.get("/api/incidents/export", params={"status": "resolved"}).text)

        assert [row["Title"] for row in rows] == ["Done one"]

    def test_the_times_are_in_the_zone_asked_for(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        incident(session)

        halifax = table(client.get("/api/incidents/export", params={"tz": "America/Halifax"}).text)
        utc = table(client.get("/api/incidents/export").text)

        assert halifax[0]["First seen"].endswith(("-03:00", "-04:00"))
        assert utc[0]["First seen"].endswith("+00:00")

    def test_json_has_the_same_columns(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        incident(session)

        [row] = json.loads(client.get("/api/incidents/export", params={"format": "json"}).text)

        assert list(row) == list(exports.INCIDENT_COLUMNS)
        assert "Wazuh" in row["Programs"]

    def test_it_asks_for_a_page_at_a_time_up_to_the_most(
        self,
        client: TestClient,
        csrf_token: str,
        session: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        for number in range(5):
            incident(
                session,
                subject=f"203.0.113.{number * 20}",
                title=f"Incident {number}",
                last_seen_at=incident_time(number),
            )
        monkeypatch.setattr(exporting, "PAGE", 2)
        monkeypatch.setattr(exporting, "MAX_ROWS", 4)

        rows = table(client.get("/api/incidents/export").text)

        assert len(rows) == 4

    def test_a_search_that_cannot_be_understood_is_refused(
        self, client: TestClient, csrf_token: str
    ) -> None:
        response = client.get("/api/incidents/export", params={"q": "sevrity:high"})

        assert response.status_code == 422

    def test_it_is_in_the_audit_log_as_the_list_it_was(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        client.get("/api/incidents/export", params={"format": "json", "q": "ssh"})

        [entry] = audited(session)
        assert entry.detail == {
            "list": "incidents",
            "format": "json",
            "search": "ssh",
            "limit": exporting.MAX_ROWS,
        }


def incident_time(number: int) -> Any:
    from app.models import utcnow

    return utcnow() - timedelta(hours=number)


class TestDevices:
    def test_the_devices_are_in_words(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        stock_devices(session, settings)

        rows = table(client.get("/api/devices/export", params={"sort": "address"}).text)

        laptop = next(row for row in rows if row["Address"] == "192.168.1.20")
        assert laptop["Scope"] == "yours"
        assert laptop["Connections it made"] == "3"
        assert laptop["Ports"] == "443"
        assert set(laptop) == set(exports.DEVICE_COLUMNS)

    def test_it_is_what_the_filters_show(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        stock_devices(session, settings)

        rows = table(client.get("/api/devices/export", params={"q": "192.168.1.30"}).text)

        assert [row["Address"] for row in rows] == ["192.168.1.30"]

    def test_it_is_in_the_audit_log(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        client.get("/api/devices/export")

        assert [(entry.detail or {})["list"] for entry in audited(session)] == ["devices"]


class TestAssets:
    def test_the_assets_are_in_words(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        stock_assets(session)

        rows = table(client.get("/api/assets/export", params={"sort": "name"}).text)

        assert {row["Name"] for row in rows} == {"laptop", "phone"}
        laptop = next(row for row in rows if row["Name"] == "laptop")
        assert laptop["Maker"] == "Example Devices Inc."
        assert laptop["Listed by"] == "OPNsense; Wazuh"
        assert set(laptop) == set(exports.ASSET_COLUMNS)

    def test_it_is_what_the_filters_show(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        stock_assets(session)

        rows = table(client.get("/api/assets/export", params={"q": "phone"}).text)

        assert [row["Name"] for row in rows] == ["phone"]

    def test_it_is_in_the_audit_log(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        client.get("/api/assets/export", params={"format": "json"})

        assert [(entry.detail or {})["list"] for entry in audited(session)] == ["assets"]


class TestAlerts:
    def test_the_messages_are_in_words_the_newest_first(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        sent = destination(session, "Security")
        delivery(session, sent, key="1", title="First")
        delivery(session, sent, key="2", title="=Second", state="failed", note="It refused")
        session.commit()

        rows = table(client.get("/api/alerts/deliveries/export").text)

        assert [row["Title"] for row in rows] == ["'=Second", "First"]
        assert rows[0]["State"] == "failed"
        assert rows[0]["Note"] == "It refused"
        assert rows[0]["Destination"] == "Security"
        assert set(rows[0]) == set(exports.ALERT_COLUMNS)

    def test_it_is_what_the_filters_show(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        sent = destination(session, "Security")
        delivery(session, sent, key="1", title="Fine")
        delivery(session, sent, key="2", title="Broken", state="failed")
        session.commit()

        rows = table(client.get("/api/alerts/deliveries/export", params={"state": "failed"}).text)

        assert [row["Title"] for row in rows] == ["Broken"]

    def test_it_goes_on_past_a_page_and_stops_at_the_most(
        self,
        client: TestClient,
        csrf_token: str,
        session: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        sent = destination(session, "Security")
        for number in range(5):
            delivery(session, sent, key=str(number), title=f"Message {number}")
        session.commit()
        monkeypatch.setattr(exporting, "PAGE", 2)

        everything = table(client.get("/api/alerts/deliveries/export").text)
        monkeypatch.setattr(exporting, "MAX_ROWS", 3)
        most = table(client.get("/api/alerts/deliveries/export").text)

        assert [len(everything), len(most)] == [5, 3]

    def test_it_is_in_the_audit_log(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        client.get("/api/alerts/deliveries/export")

        assert [(entry.detail or {})["list"] for entry in audited(session)] == ["alerts"]
