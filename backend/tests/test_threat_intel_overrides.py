"""The owner ruling a subject safe or suspicious, whatever the services made of it: what is
refused, what is kept, how it shows beside what a service said, and what is logged."""

from datetime import UTC, datetime, timedelta
from ipaddress import ip_address

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import Action
from app.intel import known, overrides, store, subjects, virustotal
from app.models import AuditEvent, IntelOverride
from app.models.base import utcnow

RULINGS = "/api/threat-intel/overrides"
KNOWN = "/api/threat-intel/subjects"
LOOKUPS = "/api/threat-intel/lookups"
ADDRESS = "93.184.216.34"
FLAGGED = virustotal.Report(
    malicious=3,
    suspicious=1,
    harmless=60,
    undetected=20,
    reputation=-12,
    analysed_at=datetime(2026, 11, 7, tzinfo=UTC),
    country="NL",
    owner="Example Hosting",
    asn=64500,
)
CLEAN = virustotal.Report(
    malicious=0,
    suspicious=0,
    harmless=70,
    undetected=10,
    reputation=3,
    analysed_at=datetime(2026, 11, 7, tzinfo=UTC),
    country="US",
    owner="Tidy Networks",
    asn=64501,
)


def headers(token: str) -> dict[str, str]:
    return {"X-CSRF-Token": token}


def rule(
    client: TestClient, token: str, subject: str, verdict: str, note: str | None = None
) -> dict[str, object]:
    body: dict[str, object] = {"subject": subject, "verdict": verdict}
    if note is not None:
        body["note"] = note
    response = client.put(RULINGS, json=body, headers=headers(token))
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


def audited(session: Session, action: Action) -> list[AuditEvent]:
    session.expire_all()
    return list(session.scalars(select(AuditEvent).where(AuditEvent.action == action.value)))


def keep(session: Session, text: str, report: virustotal.Report, when: datetime) -> None:
    store.keep(
        session, virustotal.PROVIDER, subjects.parse(text), virustotal.Reported(report), when
    )
    session.commit()


class TestTheModule:
    def test_a_ruling_is_what_a_subject_comes_to_and_nothing_means_what_the_service_said(
        self,
    ) -> None:
        assert overrides.effective("malicious", "safe") == "clean"
        assert overrides.effective("unknown", "suspicious") == "suspicious"
        assert overrides.effective("malicious", None) == "malicious"

    def test_ruling_again_replaces_the_ruling_and_there_is_one_per_subject(
        self, session: Session
    ) -> None:
        subject = subjects.parse(ADDRESS)
        now = utcnow()

        overrides.rule(session, subject, "safe", "first", now)
        again = overrides.rule(session, subject, "suspicious", None, now + timedelta(minutes=1))
        session.commit()

        assert (again.verdict, again.note) == ("suspicious", None)
        assert again.set_at == now + timedelta(minutes=1)
        assert len(session.scalars(select(IntelOverride)).all()) == 1

    def test_a_ruling_is_found_for_its_subject_and_can_be_taken_back_once(
        self, session: Session
    ) -> None:
        subject = subjects.parse("https://example.com/login?next=1")
        overrides.rule(session, subject, "safe", None, utcnow())
        session.commit()

        found = overrides.ruling_for(session, subject)
        assert found is not None and found.kind == "url" and found.host == "example.com"
        # A web address is kept as its hash, never as its text.
        assert found.subject == subject.key and "login" not in found.subject

        taken = overrides.take_back(session, subject)
        session.commit()

        assert taken is not None and taken.verdict == "safe"
        assert overrides.ruling_for(session, subject) is None
        assert overrides.take_back(session, subject) is None

    def test_the_rulings_of_some_addresses_are_found_by_address_and_only_of_addresses(
        self, session: Session
    ) -> None:
        overrides.rule(session, subjects.parse(ADDRESS), "safe", None, utcnow())
        overrides.rule(session, subjects.parse(ADDRESS.replace("93", "94")), "safe", None, utcnow())
        overrides.rule(session, subjects.parse("example.org"), "safe", None, utcnow())
        session.commit()

        found = overrides.for_addresses(session, [ip_address(ADDRESS), ip_address("1.1.1.1")])

        assert list(found) == [ADDRESS]
        assert overrides.for_addresses(session, []) == {}

    def test_the_rulings_are_listed_latest_first(self, session: Session) -> None:
        now = utcnow()
        overrides.rule(session, subjects.parse("old.example.org"), "safe", None, now)
        overrides.rule(
            session, subjects.parse(ADDRESS), "suspicious", None, now + timedelta(hours=1)
        )
        session.commit()

        assert [row.host for row in overrides.listing(session)] == [ADDRESS, "old.example.org"]


class TestRuling:
    def test_it_is_for_someone_signed_in(self, client: TestClient) -> None:
        assert client.get(RULINGS).status_code == 401
        assert client.put(RULINGS, json={"subject": ADDRESS, "verdict": "safe"}).status_code == 401
        assert client.delete(RULINGS, params={"subject": ADDRESS}).status_code == 401

    def test_it_needs_the_csrf_token(self, client: TestClient, csrf_token: str) -> None:
        response = client.put(RULINGS, json={"subject": ADDRESS, "verdict": "safe"})

        assert response.status_code == 403

    def test_an_address_is_ruled_safe_without_any_service_having_answered(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        ruled = rule(client, csrf_token, ADDRESS, "safe", "My friend's server")

        assert ruled["kind"] == "ip"
        assert ruled["subject"] == ADDRESS
        assert (ruled["verdict"], ruled["judgement"]) == ("safe", "clean")
        assert ruled["note"] == "My friend's server"
        assert ruled["set_at"]
        [event] = audited(session, Action.THREAT_INTEL_RULED)
        # What was ruled is logged, and why is not: that stays with the ruling.
        assert event.detail == {"kind": "ip", "subject": ADDRESS, "verdict": "safe"}

    def test_a_domain_and_a_web_address_are_ruled_the_way_they_are_searched(
        self, client: TestClient, csrf_token: str
    ) -> None:
        domain = rule(client, csrf_token, "Tidy.Example.org.", "suspicious")
        url = rule(client, csrf_token, "https://shop.example.net/pay?id=1#top", "safe")

        assert (domain["kind"], domain["subject"], domain["judgement"]) == (
            "domain",
            "tidy.example.org",
            "suspicious",
        )
        # A web address is shown as its host, which is all that is kept of it.
        assert (url["kind"], url["subject"]) == ("url", "shop.example.net")

    def test_ruling_again_changes_what_was_ruled_and_the_note(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        rule(client, csrf_token, ADDRESS, "safe", "first")
        ruled = rule(client, csrf_token, ADDRESS, "suspicious")

        assert (ruled["verdict"], ruled["note"]) == ("suspicious", None)
        assert len(client.get(RULINGS).json()["items"]) == 1
        assert len(audited(session, Action.THREAT_INTEL_RULED)) == 2

    def test_a_note_is_made_safe_to_keep(self, client: TestClient, csrf_token: str) -> None:
        ruled = rule(client, csrf_token, ADDRESS, "safe", "line one\u0000line two")

        assert ruled["note"] == "line one line two"

    @pytest.mark.parametrize(
        "subject",
        [
            "10.0.0.5",
            "192.168.1.20",
            "fritz.box.lan",
            "localhost",
            "not a name",
            "",
            "http://u:p@a.com",
        ],
    )
    def test_what_is_not_on_the_internet_or_is_malformed_is_refused_and_says_why(
        self, client: TestClient, csrf_token: str, subject: str
    ) -> None:
        response = client.put(
            RULINGS, json={"subject": subject, "verdict": "safe"}, headers=headers(csrf_token)
        )

        assert response.status_code == 422
        assert response.json()["detail"]

    @pytest.mark.parametrize(
        "body",
        [
            {"subject": ADDRESS, "verdict": "malicious"},
            {"subject": ADDRESS, "verdict": "safe", "note": "x" * 501},
            {"subject": ADDRESS, "verdict": "safe", "extra": 1},
            {"verdict": "safe"},
        ],
    )
    def test_a_ruling_asked_for_wrongly_is_refused(
        self, client: TestClient, csrf_token: str, body: dict[str, object]
    ) -> None:
        response = client.put(RULINGS, json=body, headers=headers(csrf_token))

        assert response.status_code == 422

    def test_the_rulings_are_listed_latest_first_with_what_they_come_to(
        self, client: TestClient, csrf_token: str
    ) -> None:
        assert client.get(RULINGS).json() == {"items": []}
        rule(client, csrf_token, "old.example.org", "safe")
        rule(client, csrf_token, ADDRESS, "suspicious", "scanned me")

        items = client.get(RULINGS).json()["items"]

        assert [(item["subject"], item["verdict"], item["judgement"]) for item in items] == [
            (ADDRESS, "suspicious", "suspicious"),
            ("old.example.org", "safe", "clean"),
        ]
        assert items[0]["note"] == "scanned me"

    def test_a_ruling_is_taken_back_and_the_log_says_so(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        rule(client, csrf_token, ADDRESS, "safe", "my own note")

        response = client.delete(RULINGS, params={"subject": ADDRESS}, headers=headers(csrf_token))

        assert response.status_code == 204
        assert client.get(RULINGS).json() == {"items": []}
        [event] = audited(session, Action.THREAT_INTEL_RULING_CLEARED)
        assert event.detail == {"kind": "ip", "subject": ADDRESS, "verdict": "safe"}

    def test_taking_back_what_was_never_ruled_is_not_found(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        response = client.delete(RULINGS, params={"subject": ADDRESS}, headers=headers(csrf_token))

        assert response.status_code == 404
        assert audited(session, Action.THREAT_INTEL_RULING_CLEARED) == []

    def test_taking_back_what_is_not_a_subject_is_refused(
        self, client: TestClient, csrf_token: str
    ) -> None:
        response = client.delete(
            RULINGS, params={"subject": "10.0.0.5"}, headers=headers(csrf_token)
        )

        assert response.status_code == 422


class TestWhatIsKept:
    @pytest.fixture
    def kept(self, session: Session) -> None:
        now = utcnow()
        keep(session, ADDRESS, FLAGGED, now - timedelta(minutes=2))
        keep(session, "tidy.example.org", CLEAN, now - timedelta(minutes=1))
        keep(session, "plain.example.net", FLAGGED, now)

    def test_a_ruling_shows_in_place_of_the_judgement_and_the_service_s_stays_beside_it(
        self, client: TestClient, csrf_token: str, kept: None
    ) -> None:
        rule(client, csrf_token, ADDRESS, "safe", "My friend's server")
        rule(client, csrf_token, "tidy.example.org", "suspicious")

        items = {item["subject"]: item for item in client.get(KNOWN).json()["items"]}

        flagged = items[ADDRESS]
        assert (flagged["judgement"], flagged["reported_judgement"]) == ("clean", "malicious")
        assert flagged["ruling"]["verdict"] == "safe"
        assert flagged["ruling"]["note"] == "My friend's server"
        # The counts are the service's, which a ruling does not change.
        assert flagged["malicious"] == 3
        tidy = items["tidy.example.org"]
        assert (tidy["judgement"], tidy["reported_judgement"]) == ("suspicious", "clean")
        untouched = items["plain.example.net"]
        assert (untouched["judgement"], untouched["ruling"]) == ("malicious", None)

    def test_the_counts_and_the_filters_follow_the_rulings(
        self, client: TestClient, csrf_token: str, kept: None
    ) -> None:
        rule(client, csrf_token, ADDRESS, "safe")

        everything = client.get(KNOWN).json()
        clean = client.get(KNOWN, params={"judgement": "clean"}).json()
        malicious = client.get(KNOWN, params={"judgement": "malicious"}).json()

        assert everything["counts"] == {"malicious": 1, "suspicious": 0, "clean": 2, "unknown": 0}
        assert sorted(item["subject"] for item in clean["items"]) == [ADDRESS, "tidy.example.org"]
        assert [item["subject"] for item in malicious["items"]] == ["plain.example.net"]
        assert (clean["total"], malicious["total"]) == (2, 1)

    def test_a_subject_ruled_on_with_no_answer_kept_is_not_in_the_list_of_answers(
        self, client: TestClient, csrf_token: str, kept: None
    ) -> None:
        rule(client, csrf_token, "never-asked.example.org", "safe")

        assert client.get(KNOWN).json()["total"] == 3
        assert "never-asked.example.org" in [
            item["subject"] for item in client.get(RULINGS).json()["items"]
        ]

    def test_a_newer_answer_does_not_replace_a_ruling(
        self, client: TestClient, csrf_token: str, kept: None, session: Session
    ) -> None:
        rule(client, csrf_token, ADDRESS, "safe")

        keep(session, ADDRESS, FLAGGED, utcnow() + timedelta(days=3))

        item = next(
            item for item in client.get(KNOWN).json()["items"] if item["subject"] == ADDRESS
        )
        assert (item["judgement"], item["reported_judgement"]) == ("clean", "malicious")

    def test_the_page_of_the_module_pairs_each_answer_with_its_ruling(
        self, session: Session, kept: None
    ) -> None:
        overrides.rule(session, subjects.parse(ADDRESS), "safe", None, utcnow())
        session.commit()

        found = known.page(session, virustotal.PROVIDER)

        assert {row.host: (ruling.verdict if ruling else None) for row, ruling in found.rows} == {
            ADDRESS: "safe",
            "tidy.example.org": None,
            "plain.example.net": None,
        }


class TestSearching:
    def test_a_search_of_a_ruled_subject_says_what_was_ruled_beside_the_answer_kept(
        self, client: TestClient, csrf_token: str, session: Session
    ) -> None:
        from tests.test_threat_intel_api import connect

        connect(session)
        keep(session, ADDRESS, FLAGGED, utcnow())
        rule(client, csrf_token, ADDRESS, "safe", "My friend's server")

        body = client.post(LOOKUPS, json={"subject": ADDRESS}, headers=headers(csrf_token)).json()

        assert (body["judgement"], body["reported_judgement"]) == ("clean", "malicious")
        assert body["ruling"]["verdict"] == "safe"
        assert body["cached"] is True
