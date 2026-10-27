import csv
import io
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api import asking
from app.audit import Action
from app.config import Settings
from app.events import queries, search
from app.events.event import Severity
from app.events.store import record as record_events
from app.models import AuditEvent, Event, Incident, IncidentSignal, User
from tests.helpers import new_event

BASE = "/api/logs"
NOW = datetime(2026, 10, 27, 15, 30, tzinfo=UTC)
MINUTE = timedelta(minutes=1)
ATTACKER = "203.0.113.7"
DEVICE = "192.168.1.20"


def store(session: Session, settings: Settings, *events: Any) -> None:
    for event in events:
        record_events(session, settings, [event], event.occurred_at)
    session.commit()


def make(session: Session, settings: Settings) -> list[Event]:
    """Four events, the oldest first, from three programs."""
    store(
        session,
        settings,
        new_event(
            source="wazuh",
            occurred_at=NOW - 30 * MINUTE,
            identity=("a",),
            severity=Severity.HIGH,
            summary="sshd: authentication failed",
            signature="Brute force on ssh",
            src_address=ATTACKER,
            src_port=41000,
            dst_address=DEVICE,
            dst_port=22,
            protocol="tcp",
            raw={"rule": {"id": "5710"}},
        ),
        new_event(
            source="opnsense",
            connection="api",
            kind="firewall",
            occurred_at=NOW - 20 * MINUTE,
            identity=("b",),
            severity=Severity.LOW,
            summary="Blocked tcp",
            src_address=ATTACKER,
            dst_address=DEVICE,
            dst_port=443,
        ),
        new_event(
            source="opnsense",
            connection="api",
            kind="firewall",
            occurred_at=NOW - 10 * MINUTE,
            identity=("c",),
            severity=Severity.LOW,
            summary="Blocked udp",
            src_address=ATTACKER,
        ),
        new_event(
            source="ntopng",
            connection="api",
            occurred_at=NOW - 5 * MINUTE,
            identity=("d",),
            severity=Severity.INFO,
            summary="DNS query volume",
        ),
    )
    return list(session.scalars(select(Event).order_by(Event.occurred_at, Event.id)))


def listed(client: TestClient, **params: Any) -> dict[str, Any]:
    response = client.get(BASE, params=params)
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


def summaries(client: TestClient, **params: Any) -> list[str]:
    return [item["summary"] for item in listed(client, **params)["items"]]


def test_it_is_only_for_someone_signed_in(client: TestClient, account: User) -> None:
    assert client.get(BASE).status_code == 401
    assert client.get(f"{BASE}/1.1").status_code == 401
    assert client.get(f"{BASE}/export").status_code == 401


class TestCursor:
    def test_it_says_when_and_which_and_reads_back_the_same(self) -> None:
        cursor = queries.Cursor(datetime(2026, 10, 27, 15, 30, 1, 123456, tzinfo=UTC), 88)

        assert str(cursor) == "1793115001123456.88"
        assert queries.Cursor.parse(str(cursor)) == cursor

    @pytest.mark.parametrize("text", ["1", "1.", ".1", "a.1", "1.a", "1.2.3", "-1.2"])
    def test_a_cursor_that_is_not_one_is_refused(
        self, client: TestClient, csrf_token: str, text: str
    ) -> None:
        assert client.get(BASE, params={"before": text}).status_code == 422
        assert client.get(f"{BASE}/{text}").status_code == 422


class TestListing:
    def test_an_install_with_no_events_has_an_empty_list(
        self, client: TestClient, csrf_token: str
    ) -> None:
        body = listed(client)

        assert body["items"] == []
        assert body["more"] is False
        assert body["terms"] == []
        assert body["summary"] == {
            "matched": 0,
            "capped": False,
            "facets": {
                "severity": {"info": 0, "low": 0, "medium": 0, "high": 0, "critical": 0},
                "sources": [],
                "kinds": [],
            },
            "volume": None,
        }

    def test_the_newest_come_first_with_what_they_say(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        make(session, settings)

        body = listed(client)

        assert summaries(client) == [
            "DNS query volume",
            "Blocked udp",
            "Blocked tcp",
            "sshd: authentication failed",
        ]
        oldest = body["items"][-1]
        assert oldest["source"] == "wazuh"
        assert oldest["source_name"] == "Wazuh"
        assert oldest["connection"] == "indexer"
        assert oldest["kind"] == "alert"
        assert oldest["severity"] == "high"
        assert oldest["signature"] == "Brute force on ssh"
        assert oldest["src_address"] == ATTACKER
        assert oldest["src_port"] == 41000
        assert oldest["dst_address"] == DEVICE
        assert oldest["dst_port"] == 22
        assert oldest["protocol"] == "tcp"
        assert oldest["has_raw"] is True
        assert "raw" not in oldest
        assert body["items"][0]["has_raw"] is False
        assert body["items"][0]["src_address"] is None

    def test_a_page_ends_where_the_next_begins(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        make(session, settings)

        first = listed(client, limit=3)
        assert [item["summary"] for item in first["items"]] == [
            "DNS query volume",
            "Blocked udp",
            "Blocked tcp",
        ]
        assert first["more"] is True

        last = first["items"][-1]["cursor"]
        second = listed(client, limit=3, before=last, summary=False)
        assert [item["summary"] for item in second["items"]] == ["sshd: authentication failed"]
        assert second["more"] is False
        assert second["summary"] is None

    def test_events_that_happened_at_the_same_moment_are_each_on_one_page(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        store(
            session,
            settings,
            *(
                new_event(occurred_at=NOW, identity=(f"same-{n}",), summary=f"Same {n}")
                for n in range(5)
            ),
        )

        seen: list[str] = []
        cursor: str | None = None
        while True:
            params: dict[str, Any] = {"limit": 2, "summary": False}
            if cursor:
                params["before"] = cursor
            page = listed(client, **params)
            seen += [item["summary"] for item in page["items"]]
            if not page["more"]:
                break
            cursor = page["items"][-1]["cursor"]

        assert sorted(seen) == [f"Same {n}" for n in range(5)]

    def test_the_ones_that_came_after_are_the_oldest_of_them_first_in_the_order_of_the_list(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        events = make(session, settings)
        after = str(queries.Cursor.of(events[0]))

        everything = listed(client, after=after)
        assert [item["summary"] for item in everything["items"]] == [
            "DNS query volume",
            "Blocked udp",
            "Blocked tcp",
        ]
        assert everything["more"] is False

        some = listed(client, after=after, limit=2)
        assert [item["summary"] for item in some["items"]] == ["Blocked udp", "Blocked tcp"]
        assert some["more"] is True

        assert listed(client, after=str(queries.Cursor.of(events[-1])))["items"] == []

    def test_older_and_newer_are_not_asked_together(
        self, client: TestClient, csrf_token: str
    ) -> None:
        response = client.get(BASE, params={"before": "1.1", "after": "1.1"})

        assert response.status_code == 422
        assert response.json()["detail"] == "Ask for older events or newer ones, not both."

    def test_the_size_of_a_page_is_limited(self, client: TestClient, csrf_token: str) -> None:
        assert client.get(BASE, params={"limit": 0}).status_code == 422
        assert client.get(BASE, params={"limit": 201}).status_code == 422


class TestSearching:
    def test_a_search_narrows_the_list_and_says_how_it_was_understood(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        make(session, settings)

        body = listed(client, q="source:opnsense severity<medium")

        assert [item["summary"] for item in body["items"]] == ["Blocked udp", "Blocked tcp"]
        assert [(term["field"], term["label"]) for term in body["terms"]] == [
            ("source", "Source: OPNsense"),
            ("severity", "Severity: under medium"),
        ]
        assert body["terms"][0]["start"] == 0
        assert body["terms"][0]["end"] == len("source:opnsense")
        assert body["terms"][0]["negated"] is False

    def test_the_summary_is_of_what_was_found_not_of_the_page(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        make(session, settings)

        body = listed(client, q="source:opnsense,wazuh", limit=1)

        assert len(body["items"]) == 1
        summary = body["summary"]
        assert summary["matched"] == 3
        assert summary["capped"] is False
        assert summary["facets"]["severity"] == {
            "info": 0,
            "low": 2,
            "medium": 0,
            "high": 1,
            "critical": 0,
        }
        assert summary["facets"]["sources"] == [
            {"key": "opnsense", "name": "OPNsense", "count": 2},
            {"key": "wazuh", "name": "Wazuh", "count": 1},
        ]
        assert summary["facets"]["kinds"] == [
            {"kind": "firewall", "count": 2},
            {"kind": "alert", "count": 1},
        ]

    def test_a_search_that_cannot_be_understood_says_why(
        self, client: TestClient, csrf_token: str
    ) -> None:
        response = client.get(BASE, params={"q": "sevrity:high"})

        assert response.status_code == 422
        assert 'Did you mean "severity"?' in response.json()["detail"]

    def test_a_time_zone_that_does_not_exist_is_refused(
        self, client: TestClient, csrf_token: str
    ) -> None:
        response = client.get(BASE, params={"q": "since:today", "tz": "Mars/Olympus"})

        assert response.status_code == 422
        assert response.json()["detail"] == "That isn't a time zone."

    def test_today_is_where_the_person_is(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        store(
            session,
            settings,
            new_event(occurred_at=NOW - 2 * MINUTE, identity=("x",), summary="Now"),
        )

        body = listed(client, q="since:yesterday", tz="America/Halifax")

        assert [term["label"] for term in body["terms"]] == ["Since: yesterday"]

    def test_the_database_is_told_to_stop_a_search_that_takes_too_long(
        self,
        client: TestClient,
        csrf_token: str,
        session: Session,
        settings: Settings,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        make(session, settings)
        slow = func.pg_sleep(1).is_not(None)

        def parse(text: str, context: search.Context) -> search.Search:
            return search.Search((search.Term(None, False, "Slow", 0, 1, slow),))

        monkeypatch.setattr(search, "parse", parse)
        monkeypatch.setattr(asking, "SEARCH_TIMEOUT_MS", 50)

        response = client.get(BASE, params={"q": "x"})

        assert response.status_code == 422
        assert response.json()["detail"] == (
            "That search took too long. Narrow it, for example with since:7d."
        )


class TestSummary:
    def test_the_newest_that_match_are_what_it_reads(
        self,
        client: TestClient,
        csrf_token: str,
        session: Session,
        settings: Settings,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        make(session, settings)
        monkeypatch.setattr(queries, "SUMMARY_WINDOW", 2)

        summary = listed(client)["summary"]

        assert summary["capped"] is True
        assert summary["matched"] == 2

    def test_the_volume_is_counted_in_bars_of_a_width_that_fits_the_time(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        make(session, settings)

        volume = listed(client)["summary"]["volume"]

        # Twenty-five minutes between the first and the last, which fit in bars of a minute.
        assert volume["seconds"] == 60
        assert volume["start"] == "2026-10-27T15:00:00Z"
        assert len(volume["counts"]) == 26
        assert sum(sum(bar) for bar in volume["counts"]) == 4
        # By severity, info first: the oldest event is the high one, the newest the info one.
        assert volume["counts"][0] == [0, 0, 0, 1, 0]
        assert volume["counts"][-1] == [1, 0, 0, 0, 0]
        assert volume["counts"][10] == [0, 1, 0, 0, 0]

    def test_a_bar_is_wider_for_longer_times(self) -> None:
        assert queries.bar_width(timedelta(minutes=30)) == 60
        assert queries.bar_width(timedelta(hours=1)) == 60
        assert queries.bar_width(timedelta(hours=2)) == 300
        assert queries.bar_width(timedelta(hours=24)) == 1800
        assert queries.bar_width(timedelta(days=7)) == 3 * 3600
        assert queries.bar_width(timedelta(days=30)) == 12 * 3600
        assert queries.bar_width(timedelta(days=60)) == 86400
        assert queries.bar_width(timedelta(days=3650)) == 7 * 86400

    def test_one_event_makes_one_bar(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        store(session, settings, new_event(occurred_at=NOW, identity=("only",)))

        volume = listed(client)["summary"]["volume"]

        assert volume["counts"] == [[0, 0, 1, 0, 0]]


class TestDetail:
    def test_an_event_comes_whole_with_the_programs_own_record(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        make(session, settings)
        cursor = listed(client)["items"][-1]["cursor"]

        response = client.get(f"{BASE}/{cursor}")

        assert response.status_code == 200
        body = response.json()
        assert body["cursor"] == cursor
        assert body["summary"] == "sshd: authentication failed"
        assert body["raw"] == {"rule": {"id": "5710"}}
        assert body["incident"] is None
        assert body["received_at"]

    def test_an_event_without_a_record_has_none(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        make(session, settings)
        cursor = listed(client)["items"][0]["cursor"]

        body = client.get(f"{BASE}/{cursor}").json()

        assert body["raw"] is None
        assert body["has_raw"] is False

    def test_it_says_which_incident_the_event_was_filed_into(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        events = make(session, settings)
        incident = Incident(
            subject=ATTACKER,
            title="Brute force on ssh (203.0.113.7)",
            severity=3,
            confidence=80,
            status="investigating",
            first_seen_at=NOW,
            last_seen_at=NOW,
            signal_count=1,
            sources=["wazuh"],
            addresses=[],
            ports=[],
            activities=[],
            top_source="wazuh",
            top_summary="An alert",
            banned=False,
            verdict=None,
            waves=1,
        )
        session.add(incident)
        session.flush()
        session.add(
            IncidentSignal(
                incident_id=incident.id,
                event_id=events[0].id,
                occurred_at=events[0].occurred_at,
                source="wazuh",
                kind="alert",
                severity=3,
                summary="An alert",
            )
        )
        session.commit()

        body = client.get(f"{BASE}/{queries.Cursor.of(events[0])}").json()

        assert body["incident"] == {
            "id": incident.id,
            "title": "Brute force on ssh (203.0.113.7)",
            "status": "investigating",
            "severity": "high",
        }

    def test_an_event_that_is_gone_is_not_found(self, client: TestClient, csrf_token: str) -> None:
        response = client.get(f"{BASE}/1793115001123456.88")

        assert response.status_code == 404
        assert response.json()["detail"] == (
            "That event isn't there. It may have passed the time events are kept for."
        )


class TestExport:
    def test_a_csv_has_a_row_for_each_event_with_a_header(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        make(session, settings)

        response = client.get(f"{BASE}/export", params={"q": "source:opnsense"})

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/csv; charset=utf-8"
        assert response.headers["content-disposition"].startswith(
            'attachment; filename="aresgate-logs-'
        )
        assert response.headers["content-disposition"].endswith('.csv"')
        assert response.headers["cache-control"] == "no-store"
        rows = list(csv.reader(io.StringIO(response.text)))
        assert rows[0] == [
            "time",
            "received",
            "source",
            "connection",
            "kind",
            "severity",
            "summary",
            "signature",
            "src_address",
            "src_port",
            "dst_address",
            "dst_port",
            "protocol",
        ]
        assert [row[6] for row in rows[1:]] == ["Blocked udp", "Blocked tcp"]
        newest = rows[1]
        assert newest[0] == (NOW - 10 * MINUTE).isoformat()
        assert newest[2:6] == ["opnsense", "api", "firewall", "low"]
        assert newest[8] == ATTACKER
        assert newest[7] == ""
        assert newest[9] == ""
        assert rows[2][11] == "443"

    def test_a_spreadsheet_is_not_given_a_formula_to_run(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        store(
            session,
            settings,
            *(
                new_event(occurred_at=NOW - n * MINUTE, identity=(f"f{n}",), summary=text)
                for n, text in enumerate(
                    ["=1+1", "+1", "-1", "@SUM(1)", "plain, with a comma"], start=1
                )
            ),
        )

        rows = list(csv.reader(io.StringIO(client.get(f"{BASE}/export").text)))

        assert [row[6] for row in rows[1:]] == [
            "'=1+1",
            "'+1",
            "'-1",
            "'@SUM(1)",
            "plain, with a comma",
        ]

    def test_a_json_file_is_a_list_of_events_with_their_records(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        make(session, settings)

        response = client.get(f"{BASE}/export", params={"format": "json"})

        assert response.headers["content-type"] == "application/json"
        assert response.headers["content-disposition"].endswith('.json"')
        events = json.loads(response.text)
        assert [event["summary"] for event in events] == [
            "DNS query volume",
            "Blocked udp",
            "Blocked tcp",
            "sshd: authentication failed",
        ]
        assert events[-1]["raw"] == {"rule": {"id": "5710"}}
        assert events[-1]["severity"] == "high"
        assert events[-1]["src_port"] == 41000
        assert events[0]["raw"] is None
        assert events[0]["src_address"] is None

    def test_the_record_can_be_left_out(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        make(session, settings)

        events = json.loads(
            client.get(f"{BASE}/export", params={"format": "json", "raw": "false"}).text
        )

        assert all("raw" not in event for event in events)

    def test_nothing_found_is_an_empty_list_or_only_a_header(
        self, client: TestClient, csrf_token: str
    ) -> None:
        assert json.loads(client.get(f"{BASE}/export", params={"format": "json"}).text) == []
        assert client.get(f"{BASE}/export").text.count("\n") == 1

    def test_it_stops_at_the_most_asked_for(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        make(session, settings)

        events = json.loads(
            client.get(f"{BASE}/export", params={"format": "json", "limit": 3}).text
        )

        assert len(events) == 3
        assert client.get(f"{BASE}/export", params={"limit": 0}).status_code == 422
        assert client.get(f"{BASE}/export", params={"limit": 50_001}).status_code == 422

    def test_it_reads_in_chunks_and_goes_on_to_the_end(
        self,
        client: TestClient,
        csrf_token: str,
        session: Session,
        settings: Settings,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        make(session, settings)
        monkeypatch.setattr(queries, "EXPORT_CHUNK", 3)

        events = json.loads(client.get(f"{BASE}/export", params={"format": "json"}).text)

        assert len(events) == 4
        assert len({event["time"] for event in events}) == 4

    def test_a_search_that_cannot_be_understood_is_refused_before_anything_is_sent(
        self, client: TestClient, csrf_token: str
    ) -> None:
        response = client.get(f"{BASE}/export", params={"q": "sevrity:high"})

        assert response.status_code == 422

    def test_each_export_is_in_the_audit_log(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        make(session, settings)

        client.get(f"{BASE}/export", params={"format": "json", "q": "source:wazuh", "limit": 10})

        entry = session.scalars(
            select(AuditEvent).where(AuditEvent.action == Action.LOGS_EXPORTED)
        ).one()
        assert entry.detail == {"format": "json", "search": "source:wazuh", "limit": 10}
