from datetime import datetime, timedelta
from ipaddress import ip_address
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.api import incidents
from app.audit import Action, Outcome
from app.config import Settings
from app.events.event import Severity
from app.incidents import engine as correlation
from app.incidents import episode, queries, search
from app.models import AuditEvent, Device, DeviceAddress, Incident, User
from tests.helpers import OTHER_ORIGIN, new_event
from tests.test_incidents_engine import (
    ATTACKER,
    DEVICE,
    NEIGHBOUR,
    NOW,
    OTHER_ATTACKER,
    alert,
    run,
    say,
    scan,
    store,
)

BASE = "/api/incidents"
MINUTE = timedelta(minutes=1)


def headers(token: str) -> dict[str, str]:
    return {"X-CSRF-Token": token}


def listed(client: TestClient, **params: Any) -> list[dict[str, Any]]:
    response = client.get(BASE, params=params)
    assert response.status_code == 200
    return response.json()["items"]  # type: ignore[no-any-return]


def make(session: Session, settings: Settings) -> None:
    """An attack from one address that two programs saw and one banned, and a quiet scan from
    another that only one program noticed, a little later."""
    store(
        session,
        settings,
        alert(NOW, n=1, severity=Severity.HIGH, signature="Brute force on ssh"),
        alert(NOW + MINUTE, n=2, source="opnsense", connection="api", signature="ET SCAN"),
        new_event(
            source="crowdsec",
            connection="lapi",
            kind="decision",
            severity=Severity.LOW,
            occurred_at=NOW + 2 * MINUTE,
            identity=("ban-1",),
            summary="Ban for ssh-bruteforce",
            src_address=ATTACKER,
        ),
        alert(NOW + 10 * MINUTE, n=3, src_address=OTHER_ATTACKER, severity=Severity.LOW),
    )
    run(session)


def test_it_is_only_for_someone_signed_in(client: TestClient, account: User) -> None:
    assert client.get(BASE).status_code == 401
    assert client.get(f"{BASE}/1").status_code == 401
    assert client.patch(f"{BASE}/1", json={"status": "resolved"}).status_code == 401


class TestListing:
    def test_an_install_with_no_incidents_has_an_empty_list(
        self, client: TestClient, csrf_token: str
    ) -> None:
        response = client.get(BASE)

        assert response.status_code == 200
        assert response.json() == {
            "total": 0,
            "items": [],
            "terms": [],
            "facets": {
                "severity": {"info": 0, "low": 0, "medium": 0, "high": 0, "critical": 0},
                "sources": [],
            },
            "counts": {"open": 0, "investigating": 0, "resolved": 0, "dismissed": 0},
            "quieted": 0,
        }

    def test_the_ones_going_most_recently_come_first(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        make(session, settings)

        response = client.get(BASE)

        body = response.json()
        assert body["total"] == 2
        assert body["counts"] == {"open": 2, "investigating": 0, "resolved": 0, "dismissed": 0}
        quiet, attack = body["items"]
        assert quiet["subject"] == OTHER_ATTACKER
        assert attack["subject"] == ATTACKER

    def test_the_most_serious_can_come_first(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        make(session, settings)

        assert [item["subject"] for item in listed(client, order="priority")] == [
            ATTACKER,
            OTHER_ATTACKER,
        ]
        assert [item["subject"] for item in listed(client, order="recent")] == [
            OTHER_ATTACKER,
            ATTACKER,
        ]

    def test_each_says_what_it_is(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        make(session, settings)

        attack = next(i for i in listed(client) if i["subject"] == ATTACKER)

        assert attack["title"] == f"Brute force on ssh ({ATTACKER})"
        assert attack["severity"] == "high"
        # The strongest signal 40, two more programs 30, the ban 20.
        assert attack["confidence"] == 90
        assert attack["confidence_level"] == "high"
        assert attack["status"] == "open"
        assert attack["signal_count"] == 3
        assert attack["sources"] == [
            {"key": "crowdsec", "name": "CrowdSec"},
            {"key": "opnsense", "name": "OPNsense"},
            {"key": "wazuh", "name": "Wazuh"},
        ]
        assert attack["addresses"] == [ATTACKER, DEVICE]
        assert attack["banned"] is True
        assert attack["first_seen_at"].startswith("2026-10-26T06:00:00")
        assert attack["last_seen_at"].startswith("2026-10-26T06:02:00")
        assert attack["status_changed_at"] is None
        assert attack["activities"] == ["brute_force"]
        assert (attack["waves"], attack["port_count"], attack["neighbours"]) == (1, 0, 0)
        assert attack["ports_capped"] is False

    def test_a_list_hasnt_the_timeline(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        make(session, settings)

        assert "signals" not in listed(client)[0]
        assert "reasons" not in listed(client)[0]

    @pytest.mark.parametrize(
        ("params", "subjects"),
        [
            ({"min_severity": "high"}, [ATTACKER]),
            ({"min_severity": "info"}, [OTHER_ATTACKER, ATTACKER]),
            ({"min_confidence": 50}, [ATTACKER]),
            ({"min_confidence": 91}, []),
            ({"address": ATTACKER}, [ATTACKER]),
            ({"address": DEVICE}, [OTHER_ATTACKER, ATTACKER]),
            ({"address": "10.9.9.9"}, []),
            ({"since": "2026-10-26T06:05:00Z"}, [OTHER_ATTACKER]),
            ({"limit": 1}, [OTHER_ATTACKER]),
            ({"limit": 1, "offset": 1}, [ATTACKER]),
            ({"offset": 2}, []),
        ],
        ids=[
            "serious",
            "anything",
            "sure",
            "surer than any",
            "an attacker",
            "a device",
            "an address in none",
            "recent",
            "first page",
            "second page",
            "past the end",
        ],
    )
    def test_it_can_be_narrowed(
        self,
        client: TestClient,
        csrf_token: str,
        session: Session,
        settings: Settings,
        params: dict[str, Any],
        subjects: list[str],
    ) -> None:
        make(session, settings)

        assert [item["subject"] for item in listed(client, **params)] == subjects

    def test_the_total_counts_what_matched_not_the_page(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        make(session, settings)

        body = client.get(BASE, params={"limit": 1}).json()

        assert (body["total"], len(body["items"])) == (2, 1)

    def test_it_can_be_narrowed_by_status(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        make(session, settings)
        attack = session.scalars(select(Incident).where(Incident.subject == ATTACKER)).one()
        attack.status = "investigating"
        session.commit()

        def subjects(**params: Any) -> list[str]:
            return [item["subject"] for item in listed(client, **params)]

        assert subjects(status="investigating") == [ATTACKER]
        assert subjects(status="open") == [OTHER_ATTACKER]
        assert subjects(status=["open", "investigating"]) == [OTHER_ATTACKER, ATTACKER]
        assert subjects(status="resolved") == []
        counts = client.get(BASE, params={"status": "resolved"}).json()["counts"]
        assert counts["open"] == 1
        assert counts["investigating"] == 1

    @pytest.mark.parametrize(
        "params",
        [
            {"status": "ignored"},
            {"min_severity": "scary"},
            {"min_confidence": 101},
            {"min_confidence": -1},
            {"address": "not-an-address"},
            {"since": "yesterday"},
            {"limit": 0},
            {"limit": 201},
            {"offset": -1},
            {"order": "random"},
        ],
    )
    def test_nonsense_is_refused(
        self, client: TestClient, csrf_token: str, params: dict[str, Any]
    ) -> None:
        assert client.get(BASE, params=params).status_code == 422


class TestSearching:
    def found(self, client: TestClient, q: str, **params: Any) -> list[str]:
        return [item["subject"] for item in listed(client, q=q, **params)]

    def test_a_search_in_words_narrows_the_list(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        make(session, settings)

        assert self.found(client, "severity>=high") == [ATTACKER]
        assert self.found(client, "source:crowdsec") == [ATTACKER]
        assert self.found(client, f"-address:{ATTACKER}") == [OTHER_ATTACKER]
        assert self.found(client, "") == [OTHER_ATTACKER, ATTACKER]

    def test_it_is_as_well_as_the_rest_of_what_was_asked_for(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        make(session, settings)

        assert self.found(client, "source:wazuh", status="resolved") == []
        assert self.found(client, "source:wazuh", min_severity="high") == [ATTACKER]
        body = client.get(BASE, params={"q": "source:wazuh", "limit": 1}).json()
        assert (body["total"], len(body["items"])) == (2, 1)

    def test_it_says_how_each_term_was_understood_and_where_it_was(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        make(session, settings)

        body = client.get(BASE, params={"q": "ssh  -source:wazuh"}).json()

        assert body["terms"] == [
            {"field": None, "label": "Contains: ssh", "negated": False, "start": 0, "end": 3},
            {
                "field": "source",
                "label": "Not source: Wazuh",
                "negated": True,
                "start": 5,
                "end": 18,
            },
        ]
        assert client.get(BASE).json()["terms"] == []

    def test_it_says_how_the_incidents_found_are_spread(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        make(session, settings)

        everything = client.get(BASE).json()["facets"]
        assert everything["severity"] == {
            "info": 0,
            "low": 1,
            "medium": 0,
            "high": 1,
            "critical": 0,
        }
        assert everything["sources"] == [
            {"key": "wazuh", "name": "Wazuh", "count": 2},
            {"key": "crowdsec", "name": "CrowdSec", "count": 1},
            {"key": "opnsense", "name": "OPNsense", "count": 1},
        ]
        narrowed = client.get(BASE, params={"q": "severity>=high"}).json()["facets"]
        assert narrowed["severity"]["low"] == 0
        assert [source["key"] for source in narrowed["sources"]] == [
            "crowdsec",
            "opnsense",
            "wazuh",
        ]
        nothing = client.get(BASE, params={"q": "zzz"}).json()["facets"]
        assert nothing["sources"] == []

    def test_the_facets_are_of_all_that_were_found_not_of_the_page(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        make(session, settings)

        body = client.get(BASE, params={"limit": 1}).json()

        assert sum(body["facets"]["severity"].values()) == 2

    def test_a_search_that_cannot_be_understood_says_why(
        self, client: TestClient, csrf_token: str
    ) -> None:
        response = client.get(BASE, params={"q": "sevrity:high"})

        assert response.status_code == 422
        assert 'Did you mean "severity"?' in response.json()["detail"]

    def test_times_are_where_the_person_is(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        make(session, settings)

        # The first incident began at 06:00 UTC. 06:05 in Halifax is 09:05 UTC, so it began before
        # that, and 06:05 where it is 14 hours ahead was the evening before.
        halifax = {"tz": "America/Halifax"}
        labels = [
            term["label"]
            for term in client.get(BASE, params={"q": "before:2026-10-26T06:05", **halifax}).json()[
                "terms"
            ]
        ]
        assert labels == ["Began before: 2026-10-26 06:05"]
        assert self.found(client, "before:2026-10-26T06:05", **halifax) == [
            OTHER_ATTACKER,
            ATTACKER,
        ]
        assert self.found(client, "before:2026-10-26T06:05", tz="Etc/GMT-14") == []

    def test_a_time_zone_that_is_not_one_is_refused(
        self, client: TestClient, csrf_token: str
    ) -> None:
        for zone in ("Nowhere/Atlantis", "../etc/passwd", "Europe", "/etc/localtime"):
            response = client.get(BASE, params={"q": "since:today", "tz": zone})
            assert response.status_code == 422
            assert response.json()["detail"] == "That isn't a time zone."

    def test_the_database_is_told_to_stop_a_search_that_takes_too_long(
        self,
        client: TestClient,
        csrf_token: str,
        session: Session,
        settings: Settings,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        make(session, settings)
        # A search the language can't say: it holds the database up for a second.
        slow = func.pg_sleep(1).is_not(None)

        def parse(text: str, context: search.Context) -> search.Search:
            return search.Search((search.Term(None, False, "Slow", 0, 1, slow),))

        monkeypatch.setattr(search, "parse", parse)
        monkeypatch.setattr(incidents, "SEARCH_TIMEOUT_MS", 50)

        response = client.get(BASE, params={"q": "x"})

        assert response.status_code == 422
        assert response.json()["detail"] == (
            "That search took too long. Narrow it, for example with since:7d."
        )

    def test_a_search_with_nothing_in_it_is_not_timed(
        self,
        client: TestClient,
        csrf_token: str,
        session: Session,
        settings: Settings,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        make(session, settings)
        monkeypatch.setattr(incidents, "SEARCH_TIMEOUT_MS", 1)

        assert len(listed(client)) == 2

    def test_a_failure_of_the_database_that_is_not_a_timeout_is_not_hidden(
        self,
        client: TestClient,
        csrf_token: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def fail(*args: Any, **kwargs: Any) -> Any:
            raise OperationalError("select", {}, Exception("the database is gone"))

        monkeypatch.setattr(queries, "search", fail)

        with pytest.raises(OperationalError):
            client.get(BASE)


class TestVerdicts:
    def calm(self, session: Session, settings: Settings) -> int:
        """The quiet scan is called fine. Returns the id of the rule."""
        make(session, settings)
        rule = say(session, "not_suspicious", address=OTHER_ATTACKER)
        correlation.reapply(session)
        session.commit()
        return rule.id

    def test_an_incident_says_what_the_owner_said_of_it(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        self.calm(session, settings)

        quiet, attack = listed(client)

        assert (quiet["verdict"], quiet["verdict_counts"]) == (
            "not_suspicious",
            {"not_suspicious": 1},
        )
        assert (quiet["confidence"], quiet["signal_count"]) == (0, 1)
        assert (attack["verdict"], attack["verdict_counts"]) == (None, {})

    def test_a_signal_says_which_rule_said_it(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        rule_id = self.calm(session, settings)
        quiet = session.scalars(select(Incident).where(Incident.subject == OTHER_ATTACKER)).one()

        detail = client.get(f"{BASE}/{quiet.id}").json()

        assert [(s["verdict"], s["verdict_rule_id"]) for s in detail["signals"]] == [
            ("not_suspicious", rule_id)
        ]
        assert [reason["rule"] for reason in detail["reasons"]] == ["muted"]

    @pytest.mark.parametrize(
        ("verdicts", "subjects"),
        [
            (["none"], [ATTACKER]),
            (["not_suspicious"], [OTHER_ATTACKER]),
            (["not_suspicious", "none"], [OTHER_ATTACKER, ATTACKER]),
            (["threat"], []),
            (["threat", "low_priority"], []),
        ],
        ids=["without one", "called fine", "either", "a threat", "other verdicts"],
    )
    def test_they_can_be_narrowed_by_what_was_said(
        self,
        client: TestClient,
        csrf_token: str,
        session: Session,
        settings: Settings,
        verdicts: list[str],
        subjects: list[str],
    ) -> None:
        self.calm(session, settings)

        found = listed(client, verdict=verdicts)

        assert [incident["subject"] for incident in found] == subjects

    def test_nonsense_is_refused(self, client: TestClient, csrf_token: str) -> None:
        assert client.get(BASE, params={"verdict": "maybe"}).status_code == 422

    def test_a_search_for_anything_else_says_how_many_it_left_out(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        self.calm(session, settings)

        asked = client.get(BASE, params={"verdict": ["none", "threat"]}).json()
        everything = client.get(BASE).json()

        assert [item["subject"] for item in asked["items"]] == [ATTACKER]
        assert (asked["total"], asked["quieted"]) == (1, 1)
        assert (everything["total"], everything["quieted"]) == (2, 1)

    def test_what_it_left_out_is_only_of_the_search(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        self.calm(session, settings)

        elsewhere = client.get(BASE, params={"address": ATTACKER, "verdict": "none"}).json()
        resolved = client.get(BASE, params={"status": "resolved", "verdict": "none"}).json()

        assert elsewhere["quieted"] == 0
        assert resolved["quieted"] == 0

    def test_the_counts_follow_the_verdicts_asked_about(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        self.calm(session, settings)

        hiding = client.get(BASE, params={"verdict": ["none", "threat"]}).json()["counts"]
        showing = client.get(BASE).json()["counts"]

        assert hiding == {"open": 1, "investigating": 0, "resolved": 0, "dismissed": 0}
        assert showing == {"open": 2, "investigating": 0, "resolved": 0, "dismissed": 0}


class TestOne:
    def test_it_shows_why_it_is_as_sure_as_it_is(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        make(session, settings)
        incident = session.scalars(select(Incident).where(Incident.subject == ATTACKER)).one()

        response = client.get(f"{BASE}/{incident.id}")

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == incident.id
        assert body["confidence"] == 90
        assert [(r["rule"], r["points"]) for r in body["reasons"]] == [
            ("strongest", 40),
            ("corroborated", 30),
            ("banned", 20),
        ]
        assert sum(reason["points"] for reason in body["reasons"]) == body["confidence"]
        assert body["reasons"][1]["text"] == "3 programs saw it: CrowdSec, OPNsense and Wazuh."

    def test_it_says_what_made_it_one_incident(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        store(
            session,
            settings,
            scan(NOW, n=1, dst_port=22),
            scan(NOW + MINUTE, n=2, src_address=NEIGHBOUR, dst_port=80),
            scan(NOW + 40 * MINUTE, n=3, src_address=NEIGHBOUR, dst_port=22),
        )
        run(session)
        incident = session.scalars(select(Incident)).one()

        listing = listed(client)[0]
        body = client.get(f"{BASE}/{incident.id}").json()

        assert listing["title"] == "ET SCAN Potential SSH Scan (93.184.216.0/24)"
        assert (listing["waves"], listing["port_count"], listing["neighbours"]) == (2, 2, 1)
        assert listing["activities"] == ["scan"]
        assert body["ports"] == [22, 80]
        assert body["grouping"] == [
            (
                "Signals from 2 addresses of 93.184.216.0/24 doing the same thing are grouped: "
                "a bot spread over a block is one actor."
            ),
            (
                "Each scanning signal came less than 4 hours after the one before it. "
                "A longer quiet, or more than 24 hours in all, starts another incident."
            ),
            (
                "It came in 2 waves: 3 signals in bursts with at least 15 minutes of quiet "
                "between them."
            ),
            "It touched 2 ports.",
        ]

    def test_an_incident_from_before_it_was_worked_out_is_one_wave(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        make(session, settings)
        incident = session.scalars(select(Incident).where(Incident.subject == ATTACKER)).one()
        incident.waves = 0
        session.commit()

        body = client.get(f"{BASE}/{incident.id}").json()

        assert body["waves"] == 1

    def test_it_says_when_it_has_as_many_ports_as_it_keeps(
        self,
        client: TestClient,
        csrf_token: str,
        session: Session,
        settings: Settings,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(episode, "MAX_PORTS", 2)
        store(
            session,
            settings,
            scan(NOW, n=1, dst_port=22),
            scan(NOW + MINUTE, n=2, dst_port=80),
            scan(NOW + 2 * MINUTE, n=3, dst_port=443),
        )
        run(session)

        listing = listed(client)[0]

        assert (listing["port_count"], listing["ports_capped"]) == (2, True)

    def test_it_has_a_timeline_oldest_first(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        make(session, settings)
        incident = session.scalars(select(Incident).where(Incident.subject == ATTACKER)).one()

        body = client.get(f"{BASE}/{incident.id}").json()

        assert [(s["source_name"], s["kind"], s["severity"]) for s in body["signals"]] == [
            ("Wazuh", "alert", "high"),
            ("OPNsense", "alert", "medium"),
            ("CrowdSec", "decision", "low"),
        ]
        first = body["signals"][0]
        assert first["summary"] == "sshd: authentication failed"
        assert first["signature"] == "Brute force on ssh"
        assert (first["src_address"], first["dst_address"]) == (ATTACKER, DEVICE)
        assert (first["src_port"], first["dst_port"], first["protocol"]) == (None, None, None)
        assert body["signals"][2]["dst_address"] is None

    def test_it_names_the_devices_in_it(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        make(session, settings)
        incident = session.scalars(select(Incident).where(Incident.subject == ATTACKER)).one()
        phone = Device(
            mac="aa:bb:cc:00:00:01",
            hostname="phone",
            vendor="Acme",
            first_seen_at=NOW,
            last_seen_at=NOW,
        )
        old = Device(mac="aa:bb:cc:00:00:02", first_seen_at=NOW, last_seen_at=NOW)
        session.add_all([phone, old])
        session.flush()
        # The address passed from one device to another: the one seen with it last has it.
        session.add_all(
            [
                DeviceAddress(
                    device_id=old.id,
                    address=ip_address(DEVICE),
                    first_seen_at=NOW,
                    last_seen_at=NOW - timedelta(days=2),
                ),
                DeviceAddress(
                    device_id=phone.id,
                    address=ip_address(DEVICE),
                    first_seen_at=NOW,
                    last_seen_at=NOW,
                ),
            ]
        )
        session.commit()

        body = client.get(f"{BASE}/{incident.id}").json()

        assert body["devices"] == [
            {
                "id": phone.id,
                "address": DEVICE,
                "mac": "aa:bb:cc:00:00:01",
                "hostname": "phone",
                "vendor": "Acme",
            }
        ]

    def test_no_device_is_not_a_problem(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        make(session, settings)
        incident = session.scalars(select(Incident)).first()
        assert incident is not None

        assert client.get(f"{BASE}/{incident.id}").json()["devices"] == []

    def test_it_counts_the_blocks_around_it(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        def block(n: int, at: datetime, address: str = ATTACKER, **changes: Any) -> Any:
            return new_event(
                **{
                    "source": "opnsense",
                    "connection": "api",
                    "kind": "firewall",
                    "severity": Severity.LOW,
                    "occurred_at": at,
                    "identity": (f"block-{n}",),
                    "summary": "Blocked",
                    "src_address": address,
                    **changes,
                }
            )

        make(session, settings)
        store(
            session,
            settings,
            block(1, NOW - correlation.GAP),
            block(2, NOW - 30 * MINUTE),
            block(3, NOW + 3 * MINUTE),
            block(4, NOW + 2 * MINUTE + 59 * MINUTE),
            block(5, NOW + 3 * MINUTE, address=OTHER_ATTACKER),
            block(6, NOW + 3 * MINUTE, severity=Severity.INFO),
        )
        incident = session.scalars(select(Incident).where(Incident.subject == ATTACKER)).one()

        body = client.get(f"{BASE}/{incident.id}").json()

        # One just before, one during and one just after, but not the one hours before, nor
        # another address's, nor one of no importance. They are no part of the incident itself.
        assert body["blocked"] == 3
        assert body["signal_count"] == 3

    def test_an_incident_about_a_rule_has_no_blocks_to_count(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        store(session, settings, alert(src_address=None, dst_address=None))
        run(session)
        incident = session.scalars(select(Incident)).one()

        body = client.get(f"{BASE}/{incident.id}").json()

        assert body["subject"].startswith("rule:")
        assert body["blocked"] is None
        assert body["addresses"] == []

    def test_a_very_long_one_lists_only_so_many_signals(
        self,
        client: TestClient,
        csrf_token: str,
        session: Session,
        settings: Settings,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(correlation, "MAX_SIGNALS", 2)
        store(session, settings, *(alert(NOW + n * MINUTE, n=n) for n in range(4)))
        run(session)
        incident = session.scalars(select(Incident)).one()

        body = client.get(f"{BASE}/{incident.id}").json()

        assert body["signal_count"] == 4
        assert len(body["signals"]) == 2

    @pytest.mark.parametrize("incident_id", ["999999", "9223372036854775807"])
    def test_there_is_no_such_incident(
        self, client: TestClient, csrf_token: str, incident_id: str
    ) -> None:
        assert client.get(f"{BASE}/{incident_id}").status_code == 404

    @pytest.mark.parametrize("incident_id", ["0", "-1", "abc", "9223372036854775808"])
    def test_an_id_that_cannot_be_one_is_refused(
        self, client: TestClient, csrf_token: str, incident_id: str
    ) -> None:
        assert client.get(f"{BASE}/{incident_id}").status_code == 422


class TestSayingWhatIsBeingDone:
    def one(self, session: Session, settings: Settings) -> Incident:
        store(session, settings, alert())
        run(session)
        return session.scalars(select(Incident)).one()

    def test_it_changes_the_status_and_keeps_a_record(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        incident = self.one(session, settings)

        response = client.patch(
            f"{BASE}/{incident.id}", json={"status": "investigating"}, headers=headers(csrf_token)
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "investigating"
        assert body["status_changed_at"] is not None
        assert len(body["signals"]) == 1
        session.expire_all()
        assert incident.status == "investigating"
        audited = session.scalars(
            select(AuditEvent).where(AuditEvent.action == Action.INCIDENT_STATUS_CHANGED)
        ).one()
        assert audited.outcome == Outcome.SUCCESS
        assert audited.username == "brian"
        assert audited.detail == {"incident": incident.id, "from": "open", "to": "investigating"}

    def test_it_can_be_opened_again(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        incident = self.one(session, settings)

        for status in ("resolved", "open"):
            response = client.patch(
                f"{BASE}/{incident.id}", json={"status": status}, headers=headers(csrf_token)
            )
            assert response.json()["status"] == status

        assert client.get(BASE, params={"status": "open"}).json()["total"] == 1

    def test_saying_what_it_already_is_changes_nothing(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        incident = self.one(session, settings)

        response = client.patch(
            f"{BASE}/{incident.id}", json={"status": "open"}, headers=headers(csrf_token)
        )

        assert response.status_code == 200
        assert response.json()["status_changed_at"] is None
        assert (
            session.scalars(
                select(AuditEvent).where(AuditEvent.action == Action.INCIDENT_STATUS_CHANGED)
            ).all()
            == []
        )

    @pytest.mark.parametrize(
        "body", [{"status": "ignored"}, {}, {"status": "open", "title": "x"}, {"status": None}]
    )
    def test_nonsense_is_refused(
        self,
        client: TestClient,
        csrf_token: str,
        session: Session,
        settings: Settings,
        body: dict[str, Any],
    ) -> None:
        incident = self.one(session, settings)

        response = client.patch(f"{BASE}/{incident.id}", json=body, headers=headers(csrf_token))

        assert response.status_code == 422

    def test_there_is_no_such_incident_to_change(self, client: TestClient, csrf_token: str) -> None:
        response = client.patch(
            f"{BASE}/999999", json={"status": "resolved"}, headers=headers(csrf_token)
        )

        assert response.status_code == 404

    def test_it_only_changes_from_one_of_its_own_pages(
        self, client: TestClient, csrf_token: str, session: Session, settings: Settings
    ) -> None:
        incident = self.one(session, settings)

        response = client.patch(
            f"{BASE}/{incident.id}",
            json={"status": "resolved"},
            headers={**headers(csrf_token), "Origin": OTHER_ORIGIN},
        )

        assert response.status_code == 403
        session.expire_all()
        assert incident.status == "open"
