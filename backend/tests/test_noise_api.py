from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import Action, Outcome
from app.config import Settings
from app.events.event import Severity
from app.incidents import attention, filters
from app.models import AuditEvent, Incident, IncidentSignal, NoiseSettings, User
from tests.helpers import OTHER_ORIGIN
from tests.test_incidents_engine import (
    ATTACKER,
    HOUR,
    NEIGHBOUR,
    NOW,
    alert,
    run,
    say,
    store,
)

BASE = "/api/noise-filters"
OTHER_DEVICE = "192.168.1.30"
EVERYTHING: dict[str, Any] = {"confidence_floor": 35, "quiet_inside": False, "source_floors": {}}


def headers(token: str) -> dict[str, str]:
    return {"X-CSRF-Token": token}


def change(client: TestClient, token: str, **body: Any) -> Any:
    return client.put(BASE, json={**EVERYTHING, **body}, headers=headers(token))


def preview(client: TestClient, token: str, **body: Any) -> Any:
    return client.post(f"{BASE}/preview", json={**EVERYTHING, **body}, headers=headers(token))


def audited(session: Session) -> list[AuditEvent]:
    session.expire_all()
    return list(
        session.scalars(
            select(AuditEvent)
            .where(AuditEvent.action == Action.NOISE_FILTERS_CHANGED)
            .order_by(AuditEvent.id)
        )
    )


@pytest.fixture(autouse=True)
def this_week(monkeypatch: pytest.MonkeyPatch) -> None:
    """The tests' alerts are from a fixed day; this is the same day, a little later."""
    monkeypatch.setattr("app.api.noise.utcnow", lambda: NOW + HOUR)


def noisy(session: Session, settings: Settings) -> None:
    """A high alert (40 sure), a low one from a program the owner might silence, and an alert
    between two devices."""
    store(
        session,
        settings,
        alert(n=1, severity=Severity.HIGH),
        alert(NOW + timedelta(minutes=1), n=2, src_address="1.1.1.1", severity=Severity.LOW),
        alert(NOW + timedelta(minutes=2), n=3, src_address=OTHER_DEVICE, severity=Severity.HIGH),
        alert(
            NOW + timedelta(minutes=3),
            n=4,
            source="opnsense",
            connection="api",
            src_address="9.9.9.9",
        ),
    )
    run(session)


def test_it_is_only_for_someone_signed_in(client: TestClient, account: User) -> None:
    answers = [
        client.get(BASE),
        client.put(BASE, json=EVERYTHING),
        client.post(f"{BASE}/preview", json=EVERYTHING),
    ]

    assert [answer.status_code for answer in answers] == [401, 401, 401]


class TestReadingThem:
    def test_an_install_that_never_saved_them_has_the_defaults(
        self, client: TestClient, csrf_token: str
    ) -> None:
        assert client.get(BASE).json() == {
            "confidence_floor": 35,
            "default_floor": 35,
            "medium_from": 35,
            "high_from": 65,
            "quiet_inside": False,
            "scan_gap_hours": 4,
            "default_scan_gap_hours": 4,
            "brute_force_gap_hours": 6,
            "default_brute_force_gap_hours": 6,
            "thin_low_signals": 1,
            "default_thin_low_signals": 1,
            "sources": [],
            "verdicts": 0,
            "updated_at": None,
        }

    def test_the_programs_that_reported_this_week_are_listed_with_what_they_reported(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        noisy(session, settings)

        body = client.get(BASE).json()

        assert body["sources"] == [
            {"key": "opnsense", "name": "OPNsense", "floor": None, "week": {"medium": 1}},
            {
                "key": "wazuh",
                "name": "Wazuh",
                "floor": None,
                "week": {"high": 2, "low": 1},
            },
        ]

    def test_a_ban_is_not_an_alert_and_an_old_alert_is_not_this_week(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        store(
            session,
            settings,
            alert(n=1, source="crowdsec", kind="decision"),
            alert(NOW - timedelta(days=9), n=2, src_address="1.1.1.1"),
        )
        run(session, NOW + timedelta(days=1))

        assert client.get(BASE).json()["sources"] == []

    def test_a_program_with_a_floor_is_listed_though_it_reported_nothing(
        self, client: TestClient, csrf_token: str
    ) -> None:
        change(client, csrf_token, source_floors={"ntopng": "high"})

        (source,) = client.get(BASE).json()["sources"]

        assert source == {"key": "ntopng", "name": "ntopng", "floor": "high", "week": {}}

    def test_it_counts_the_verdicts_and_says_when_the_filters_were_saved(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        say(session, "low_priority", address=ATTACKER)
        say(session, "threat", address=NEIGHBOUR)
        change(client, csrf_token, quiet_inside=True)

        body = client.get(BASE).json()

        assert body["verdicts"] == 2
        assert body["quiet_inside"] is True
        assert body["updated_at"] is not None


class TestChangingThem:
    def test_they_are_kept_and_a_record_is_made(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        response = change(
            client,
            csrf_token,
            confidence_floor=50,
            quiet_inside=True,
            source_floors={"wazuh": "high", "ntopng": "critical"},
        )

        assert response.status_code == 200
        assert response.json()["confidence_floor"] == 50
        assert filters.load(session) == filters.Filters(
            50, True, {"wazuh": int(Severity.HIGH), "ntopng": int(Severity.CRITICAL)}
        )
        (record,) = audited(session)
        assert record.outcome == Outcome.SUCCESS
        assert record.username == "brian"
        assert record.detail == {
            "confidence_floor": 50,
            "from_confidence_floor": 35,
            "quiet_inside": True,
            "from_quiet_inside": False,
            "source_floors": "ntopng=critical, wazuh=high",
            "from_source_floors": "",
        }

    def test_the_record_only_says_what_changed(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        change(client, csrf_token, source_floors={"wazuh": "high"})

        change(client, csrf_token, source_floors={"wazuh": "medium"}, quiet_inside=True)

        first, second = audited(session)
        assert first.detail == {"source_floors": "wazuh=high", "from_source_floors": ""}
        assert second.detail == {
            "quiet_inside": True,
            "from_quiet_inside": False,
            "source_floors": "wazuh=medium",
            "from_source_floors": "wazuh=high",
        }

    def test_saving_what_is_already_so_makes_no_record_and_no_change(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        change(client, csrf_token, quiet_inside=True)
        saved = session.scalars(select(NoiseSettings)).one().updated_at

        response = change(client, csrf_token, quiet_inside=True)

        assert response.status_code == 200
        assert len(audited(session)) == 1
        session.expire_all()
        assert session.scalars(select(NoiseSettings)).one().updated_at == saved

    def test_the_incidents_that_are_going_on_are_judged_again_at_once(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        noisy(session, settings)
        found = {item.subject: item for item in session.scalars(select(Incident))}
        assert found[ATTACKER].confidence == 40
        assert found["1.1.1.1"].confidence == 10

        change(client, csrf_token, source_floors={"wazuh": "high"}, quiet_inside=True)

        session.expire_all()
        found = {item.subject: item for item in session.scalars(select(Incident))}
        assert found[ATTACKER].confidence == 40
        assert (found["1.1.1.1"].confidence, found["1.1.1.1"].filtered_count) == (0, 1)
        assert found[OTHER_DEVICE].filtered_count == 1
        assert {signal.filtered_by for signal in session.scalars(select(IncidentSignal))} == {
            None,
            "severity",
            "inside",
        }

    def test_the_dashboard_goes_by_the_floor(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        change(client, csrf_token, confidence_floor=50)

        assert client.get("/api/dashboard").json()["attention"]["floor"] == 50

    @pytest.mark.parametrize(
        "body",
        [
            {"confidence_floor": 0},
            {"confidence_floor": 101},
            {"confidence_floor": "high"},
            {"source_floors": {"wazuh": "low"}},
            {"source_floors": {"wazuh": "info"}},
            {"source_floors": {"wazuh": 3}},
            {"source_floors": {"nothing": "high"}},
            {"quiet_inside": "sometimes"},
            {"another": 1},
        ],
    )
    def test_nonsense_is_refused(
        self, client: TestClient, csrf_token: str, session: Session, body: dict[str, Any]
    ) -> None:
        assert change(client, csrf_token, **body).status_code == 422
        assert preview(client, csrf_token, **body).status_code == 422
        assert session.scalars(select(NoiseSettings)).first() is None

    def test_all_of_them_have_to_be_said(self, client: TestClient, csrf_token: str) -> None:
        response = client.put(BASE, json={"quiet_inside": True}, headers=headers(csrf_token))

        assert response.status_code == 422

    def test_they_are_only_changed_from_one_of_its_own_pages(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        response = client.put(
            BASE,
            json={**EVERYTHING, "quiet_inside": True},
            headers={**headers(csrf_token), "Origin": OTHER_ORIGIN},
        )

        assert response.status_code == 403
        assert session.scalars(select(NoiseSettings)).first() is None


class TestPreviewingThem:
    def test_it_says_what_the_filters_do_now_and_what_they_would_do(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        noisy(session, settings)

        body = preview(
            client,
            csrf_token,
            confidence_floor=45,
            quiet_inside=True,
            source_floors={"wazuh": "high"},
        ).json()

        assert body["now"] == {
            "incidents": {
                "active": 4,
                "needs_you": 2,
                "urgent": 0,
                "unsure": 2,
                "cleared": 0,
                "muted": 0,
            },
            "set_aside": {"total": 0, "inside": 0, "severity": 0, "thin": 0, "by_source": {}},
            "scan_gap_hours": 4,
            "brute_force_gap_hours": 6,
            "thin_low_signals": 1,
        }
        assert body["after"] == {
            "incidents": {
                "active": 4,
                "needs_you": 0,
                "urgent": 0,
                "unsure": 4,
                "cleared": 0,
                "muted": 0,
            },
            "set_aside": {
                "total": 2,
                "inside": 1,
                "severity": 1,
                "thin": 0,
                "by_source": {"wazuh": 2},
            },
            "scan_gap_hours": 4,
            "brute_force_gap_hours": 6,
            "thin_low_signals": 1,
        }

    def test_it_changes_nothing(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        noisy(session, settings)
        before = [
            (item.subject, item.confidence, item.filtered_count)
            for item in session.scalars(select(Incident).order_by(Incident.id))
        ]

        preview(
            client,
            csrf_token,
            confidence_floor=90,
            quiet_inside=True,
            source_floors={"wazuh": "critical"},
        )

        session.expire_all()
        assert filters.load(session) == filters.Filters()
        assert session.scalars(select(NoiseSettings)).first() is None
        assert audited(session) == []
        assert before == [
            (item.subject, item.confidence, item.filtered_count)
            for item in session.scalars(select(Incident).order_by(Incident.id))
        ]
        assert {signal.filtered_by for signal in session.scalars(select(IncidentSignal))} == {None}

    def test_it_is_what_saving_them_does(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        noisy(session, settings)
        say(session, "low_priority", address=NEIGHBOUR)
        asked = {
            "confidence_floor": 20,
            "quiet_inside": True,
            "source_floors": {"wazuh": "medium"},
        }
        expected = preview(client, csrf_token, **asked).json()["after"]

        change(client, csrf_token, **asked)
        session.expire_all()

        found = attention.tally(session, 20)
        assert expected["incidents"] == {
            "active": found.active,
            "needs_you": found.needs_you,
            "urgent": found.urgent,
            "unsure": found.unsure,
            "cleared": found.cleared,
            "muted": found.muted,
        }
        aside = session.scalars(
            select(IncidentSignal).where(IncidentSignal.filtered_by.is_not(None))
        ).all()
        assert expected["set_aside"]["total"] == len(aside)

    def test_what_is_over_is_not_counted(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        noisy(session, settings)
        for item in session.scalars(select(Incident)):
            item.status = "resolved"
        session.commit()

        body = preview(client, csrf_token, quiet_inside=True).json()

        assert body["after"]["incidents"]["active"] == 0
        assert body["after"]["set_aside"]["total"] == 0


class TestTheGapsAndTheMinimum:
    def test_they_are_saved_and_said_back(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        response = change(
            client, csrf_token, scan_gap_hours=8, brute_force_gap_hours=2, thin_low_signals=3
        )

        assert response.status_code == 200
        assert response.json()["scan_gap_hours"] == 8
        assert response.json()["brute_force_gap_hours"] == 2
        assert response.json()["thin_low_signals"] == 3
        assert filters.load(session) == filters.Filters(
            scan_gap_hours=8, brute_force_gap_hours=2, thin_low_signals=3
        )

    def test_the_record_says_what_changed_in_them(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        change(client, csrf_token, scan_gap_hours=8, thin_low_signals=3)

        (record,) = audited(session)
        assert record.detail == {
            "scan_gap_hours": 8,
            "from_scan_gap_hours": 4,
            "thin_low_signals": 3,
            "from_thin_low_signals": 1,
        }

    @pytest.mark.parametrize(
        ("setting", "value"),
        [
            ("scan_gap_hours", 0),
            ("scan_gap_hours", 25),
            ("brute_force_gap_hours", 0),
            ("brute_force_gap_hours", 25),
            ("thin_low_signals", 0),
            ("thin_low_signals", 11),
        ],
    )
    def test_one_outside_its_range_is_refused(
        self, client: TestClient, csrf_token: str, session: Session, setting: str, value: int
    ) -> None:
        response = change(client, csrf_token, **{setting: value})

        assert response.status_code == 422
        assert session.scalars(select(NoiseSettings)).first() is None

    @pytest.mark.parametrize(
        ("setting", "value"),
        [
            ("scan_gap_hours", 1),
            ("scan_gap_hours", 24),
            ("brute_force_gap_hours", 24),
            ("thin_low_signals", 10),
        ],
    )
    def test_the_ends_of_their_ranges_are_allowed(
        self, client: TestClient, csrf_token: str, setting: str, value: int
    ) -> None:
        assert change(client, csrf_token, **{setting: value}).status_code == 200

    def test_the_preview_says_how_many_signals_a_minimum_would_set_aside(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        noisy(session, settings)

        body = preview(client, csrf_token, thin_low_signals=2).json()

        assert body["now"]["thin_low_signals"] == 1
        assert body["now"]["set_aside"]["thin"] == 0
        assert body["after"]["thin_low_signals"] == 2
        assert body["after"]["set_aside"] == {
            "total": 1,
            "inside": 0,
            "severity": 0,
            "thin": 1,
            "by_source": {"wazuh": 1},
        }
