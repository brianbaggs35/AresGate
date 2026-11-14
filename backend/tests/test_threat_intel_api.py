"""Searching VirusTotal by hand: what is refused and never sent, what comes back, what is kept, and
the limits a search shares with the background lookups."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import threat_intel as threat_intel_api
from app.integrations import netguard, service
from app.integrations.client import CallFailed, Target
from app.intel import store, subjects, virustotal
from app.models import IntegrationConnection, IntelLookup, IntelSubject, Interface
from app.models.base import utcnow

URL = "/api/threat-intel/lookups"
ADDRESS = "93.184.216.34"
REPORT = virustotal.Report(
    malicious=3,
    suspicious=1,
    harmless=60,
    undetected=20,
    reputation=-12,
    analysed_at=datetime(2026, 11, 7, tzinfo=UTC),
    country="NL",
    owner="Example Hosting",
    asn=64500,
    categories=("malware",),
    details=(("Owner", "Example Hosting"), ("Country", "NL"), ("Network", "AS64500")),
)


def headers(token: str) -> dict[str, str]:
    return {"X-CSRF-Token": token}


def search(client: TestClient, token: str, subject: str, *, refresh: bool = False) -> Response:
    body: dict[str, object] = {"subject": subject}
    if refresh:
        body["refresh"] = True
    return client.post(URL, json=body, headers=headers(token))


def connect(session: Session, *, tested: bool = True) -> None:
    session.add(
        IntegrationConnection(
            integration="virustotal",
            connection="api",
            base_url="https://www.virustotal.com",
            tls_mode="system",
            options={"tier": "free"},
            last_success_at=utcnow() if tested else None,
        )
    )
    session.commit()


@pytest.fixture
def connected(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """A tested VirusTotal connection whose key opens."""
    origin = netguard.parse_origin("https://www.virustotal.com", allow_http=False)

    def load(*args: object, **kwargs: object) -> Target:
        del args, kwargs
        return Target(
            integration="virustotal",
            connection="api",
            origin=origin,
            tls_mode="system",
            tls_ca_pem=None,
            tls_fingerprint=None,
            options={"tier": "free"},
            secrets={"api_key": "vt-key"},
        )

    monkeypatch.setattr(service, "load_target", load)
    connect(session)


def answering(monkeypatch: pytest.MonkeyPatch, answer: object) -> list[object]:
    """Makes VirusTotal answer with the answer given, or raise it. Returns the requests made."""
    asked: list[object] = []

    async def look_up(*args: object) -> object:
        asked.append(args)
        if isinstance(answer, BaseException):
            raise answer
        return answer

    monkeypatch.setattr(virustotal, "look_up", look_up)
    return asked


def test_a_search_is_for_a_signed_in_user(client: TestClient) -> None:
    response = client.post(URL, json={"subject": ADDRESS})

    assert response.status_code == 401


def test_a_search_needs_a_connection(client: TestClient, csrf_token: str) -> None:
    response = search(client, csrf_token, ADDRESS)

    assert response.status_code == 409
    assert response.json() == {"detail": "Connect VirusTotal and test it before searching."}


def test_a_search_needs_a_connection_that_has_been_tested(
    client: TestClient, csrf_token: str, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    connect(session, tested=False)
    asked = answering(monkeypatch, virustotal.Unknown())

    response = search(client, csrf_token, ADDRESS)

    assert response.status_code == 409
    assert response.json() == {"detail": "Connect VirusTotal and test it before searching."}
    assert asked == []


def test_a_search_needs_a_key_that_still_opens(
    client: TestClient, csrf_token: str, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    connect(session)

    def gone(*args: object, **kwargs: object) -> Target:
        del args, kwargs
        raise service.Incomplete("The API key isn't saved any more.")

    monkeypatch.setattr(service, "load_target", gone)
    asked = answering(monkeypatch, virustotal.Unknown())

    response = search(client, csrf_token, ADDRESS)

    assert response.status_code == 409
    assert response.json() == {"detail": "The API key isn't saved any more."}
    assert asked == []


@pytest.mark.parametrize(
    ("subject", "detail"),
    [
        ("", subjects.EMPTY),
        (
            "192.168.1.20",
            "192.168.1.20 isn't a public internet address, so it isn't sent to VirusTotal.",
        ),
        ("router.lan", "router.lan is a name on your own network, so it isn't sent to VirusTotal."),
        ("not a thing", subjects.MALFORMED),
        ("http://user:pass@example.com", subjects.CREDENTIALS),
    ],
)
def test_what_is_refused_is_never_sent_and_says_why(
    client: TestClient,
    csrf_token: str,
    connected: None,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    subject: str,
    detail: str,
) -> None:
    asked = answering(monkeypatch, virustotal.Unknown())

    response = search(client, csrf_token, subject)

    assert response.status_code == 422
    assert response.json() == {"detail": detail}
    assert asked == []
    assert session.scalars(select(IntelLookup)).all() == []


def test_a_search_longer_than_a_web_address_can_be_is_refused(
    client: TestClient, csrf_token: str, connected: None
) -> None:
    response = search(client, csrf_token, "a" * (subjects.MAX_LENGTH + 1))

    assert response.status_code == 422


def test_a_search_takes_only_its_subject(
    client: TestClient, csrf_token: str, connected: None
) -> None:
    response = client.post(
        URL, json={"subject": ADDRESS, "kind": "url"}, headers=headers(csrf_token)
    )

    assert response.status_code == 422


def test_an_address_on_the_homes_own_internet_side_is_refused(
    client: TestClient,
    csrf_token: str,
    connected: None,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session.add(Interface(name="internet side", role="internet", networks=["93.184.216.0/24"]))
    session.commit()
    asked = answering(monkeypatch, virustotal.Unknown())

    response = search(client, csrf_token, ADDRESS)

    assert response.status_code == 422
    assert response.json() == {
        "detail": "That is this home's own address on the internet, so it isn't sent to VirusTotal."
    }
    assert asked == []


def test_an_address_is_reported_with_its_judgement_counts_and_details_and_its_report_is_kept(
    client: TestClient,
    csrf_token: str,
    connected: None,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answering(monkeypatch, virustotal.Reported(report=REPORT))

    response = search(client, csrf_token, ADDRESS)

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "ip"
    assert body["subject"] == ADDRESS
    assert body["judgement"] == "malicious"
    assert (body["malicious"], body["suspicious"], body["harmless"], body["undetected"]) == (
        3,
        1,
        60,
        20,
    )
    assert body["reputation"] == -12
    assert body["analysed_at"].startswith("2026-11-07T00:00:00")
    assert body["categories"] == ["malware"]
    assert body["details"] == [
        {"label": "Owner", "value": "Example Hosting"},
        {"label": "Country", "value": "NL"},
        {"label": "Network", "value": "AS64500"},
    ]
    assert body["link"] == "https://www.virustotal.com/gui/ip-address/93.184.216.34"
    [kept] = session.scalars(select(IntelSubject)).all()
    assert (kept.kind, kept.subject, kept.categories) == ("ip", ADDRESS, ["malware"])
    [lookup] = session.scalars(select(IntelLookup)).all()
    assert (lookup.kind, lookup.outcome, str(lookup.address)) == ("ip", store.REPORTED, ADDRESS)


def test_a_domain_is_reported_and_its_answer_is_kept_for_the_domain(
    client: TestClient,
    csrf_token: str,
    connected: None,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answering(monkeypatch, virustotal.Reported(report=REPORT))

    response = search(client, csrf_token, "Example.COM.")

    assert response.status_code == 200
    body = response.json()
    assert (body["kind"], body["subject"]) == ("domain", "example.com")
    assert body["link"] == "https://www.virustotal.com/gui/domain/example.com"
    [kept] = session.scalars(select(IntelSubject)).all()
    assert (kept.kind, kept.subject) == ("domain", "example.com")
    [lookup] = session.scalars(select(IntelLookup)).all()
    assert (lookup.kind, lookup.address, lookup.subject) == ("domain", None, "example.com")


def test_a_web_address_is_shown_as_searched_but_only_its_host_is_kept(
    client: TestClient,
    csrf_token: str,
    connected: None,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answering(monkeypatch, virustotal.Unknown())

    response = search(client, csrf_token, "https://example.com/login?token=secret#top")

    assert response.status_code == 200
    body = response.json()
    assert (body["kind"], body["subject"], body["judgement"]) == (
        "url",
        "https://example.com/login?token=secret",
        "unknown",
    )
    [lookup] = session.scalars(select(IntelLookup)).all()
    assert (lookup.kind, lookup.address, lookup.subject) == ("url", None, "example.com")
    [kept] = session.scalars(select(IntelSubject)).all()
    assert kept.subject == subjects.url_key("https://example.com/login?token=secret")


def test_an_address_with_no_report_is_unknown_and_has_no_counts(
    client: TestClient,
    csrf_token: str,
    connected: None,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answering(monkeypatch, virustotal.Unknown())

    response = search(client, csrf_token, ADDRESS)

    assert response.status_code == 200
    body = response.json()
    assert body["judgement"] == "unknown"
    assert (body["malicious"], body["suspicious"], body["harmless"], body["undetected"]) == (
        0,
        0,
        0,
        0,
    )
    assert (body["reputation"], body["analysed_at"], body["categories"], body["details"]) == (
        None,
        None,
        [],
        [],
    )
    [kept] = session.scalars(select(IntelSubject)).all()
    assert kept.outcome == store.UNKNOWN


@pytest.mark.parametrize(
    ("answer", "detail"),
    [
        (virustotal.Failed("VirusTotal answered HTTP 403."), "VirusTotal answered HTTP 403."),
        (
            CallFailed("Couldn't connect to www.virustotal.com:443."),
            "Couldn't connect to www.virustotal.com:443.",
        ),
    ],
)
def test_a_search_that_gets_no_report_is_a_bad_gateway_and_is_kept_as_failed(
    client: TestClient,
    csrf_token: str,
    connected: None,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    answer: object,
    detail: str,
) -> None:
    answering(monkeypatch, answer)

    response = search(client, csrf_token, ADDRESS)

    assert response.status_code == 502
    assert response.json() == {"detail": detail}
    [lookup] = session.scalars(select(IntelLookup)).all()
    assert lookup.outcome == store.FAILED


def test_a_search_within_the_spacing_of_the_last_lookup_waits_and_says_how_long(
    client: TestClient,
    csrf_token: str,
    connected: None,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The clock stands still, so that no time passes between the lookup and the search: the wait
    # is rounded up to whole seconds and a busy computer could take one of them.
    moment = utcnow()
    monkeypatch.setattr(threat_intel_api, "utcnow", lambda: moment)
    session.add(
        IntelLookup(
            provider=virustotal.PROVIDER,
            address=ip_address("1.1.1.1"),
            requested_at=moment - timedelta(seconds=10),
            outcome=store.REPORTED,
        )
    )
    session.commit()
    asked = answering(monkeypatch, virustotal.Unknown())

    response = search(client, csrf_token, ADDRESS)

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "5"
    assert response.json() == {
        "detail": "VirusTotal's limit on searches is reached. Try again in 5 seconds."
    }
    assert asked == []
    assert len(session.scalars(select(IntelLookup)).all()) == 1


def age_every_lookup(session: Session, age: timedelta) -> None:
    """Moves every lookup kept back by ``age``, so the spacing and the allowances have passed."""
    for lookup in session.scalars(select(IntelLookup)).all():
        lookup.requested_at = utcnow() - age
    session.commit()


def limit_at(session: Session, outcome: str, when: datetime) -> None:
    """A lookup that VirusTotal's limit held, kept as it is when a limit answers."""
    session.add(IntelLookup(provider="virustotal", kind="ip", requested_at=when, outcome=outcome))
    session.commit()


def test_a_search_while_the_daily_quota_holds_says_so_and_sends_nothing(
    client: TestClient,
    csrf_token: str,
    connected: None,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limit_at(session, store.LIMITED, utcnow())
    asked = answering(monkeypatch, virustotal.Unknown())

    response = search(client, csrf_token, ADDRESS)

    assert response.status_code == 429
    assert response.json() == {
        "detail": "VirusTotal's daily limit is reached. Searches resume at 00:00 UTC."
    }
    assert int(response.headers["Retry-After"]) > 0
    assert asked == []


def test_a_search_within_a_minute_of_too_many_requests_says_when_to_try_again(
    client: TestClient,
    csrf_token: str,
    connected: None,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limit_at(session, store.THROTTLED, utcnow() - timedelta(seconds=5))
    asked = answering(monkeypatch, virustotal.Unknown())

    response = search(client, csrf_token, ADDRESS)

    assert response.status_code == 429
    assert response.json()["detail"].startswith(
        "VirusTotal asked for fewer requests. Try again in "
    )
    assert asked == []


def test_a_search_that_finds_the_daily_quota_used_up_keeps_the_key_connected(
    client: TestClient,
    csrf_token: str,
    connected: None,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = answering(monkeypatch, virustotal.Limited(until=virustotal.next_reset(utcnow())))

    response = search(client, csrf_token, ADDRESS)

    assert response.status_code == 429
    assert response.json() == {
        "detail": "VirusTotal's daily limit is reached. Searches resume at 00:00 UTC."
    }
    session.expire_all()
    [lookup] = session.scalars(select(IntelLookup)).all()
    assert lookup.outcome == store.LIMITED
    assert session.scalars(select(IntelSubject)).all() == []
    [row] = session.scalars(select(IntegrationConnection)).all()
    assert row.last_error is None
    assert row.last_success_at is not None
    assert len(asked) == 1


def test_a_search_asked_to_slow_down_says_when_to_try_again(
    client: TestClient,
    csrf_token: str,
    connected: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answering(monkeypatch, virustotal.Throttled(until=utcnow() + timedelta(minutes=1)))

    response = search(client, csrf_token, ADDRESS)

    assert response.status_code == 429
    assert response.json()["detail"].startswith(
        "VirusTotal asked for fewer requests. Try again in "
    )
    assert int(response.headers["Retry-After"]) > 0


def test_a_search_answered_lately_is_answered_from_what_was_kept_and_not_asked_again(
    client: TestClient,
    csrf_token: str,
    connected: None,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = answering(monkeypatch, virustotal.Reported(report=REPORT))
    first = search(client, csrf_token, ADDRESS)

    second = search(client, csrf_token, ADDRESS)

    assert (first.status_code, second.status_code) == (200, 200)
    assert len(asked) == 1
    assert (first.json()["cached"], second.json()["cached"]) == (False, True)
    assert second.json()["checked_at"] == first.json()["checked_at"]
    assert (second.json()["judgement"], second.json()["malicious"]) == ("malicious", 3)
    assert len(session.scalars(select(IntelLookup)).all()) == 1


def test_a_domain_or_web_address_answered_lately_is_answered_from_what_was_kept(
    client: TestClient,
    csrf_token: str,
    connected: None,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = answering(monkeypatch, virustotal.Reported(report=REPORT))
    search(client, csrf_token, "example.com")

    again = search(client, csrf_token, "EXAMPLE.com.")

    assert again.status_code == 200
    assert again.json()["cached"] is True
    assert again.json()["subject"] == "example.com"
    assert len(asked) == 1


def test_a_search_is_asked_again_once_its_answer_is_no_longer_fresh(
    client: TestClient,
    csrf_token: str,
    connected: None,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = answering(monkeypatch, virustotal.Unknown())
    search(client, csrf_token, ADDRESS)
    [kept] = session.scalars(select(IntelSubject)).all()
    kept.checked_at = utcnow() - store.SOONER - timedelta(minutes=1)
    age_every_lookup(session, timedelta(days=8))

    response = search(client, csrf_token, ADDRESS)

    assert response.status_code == 200
    assert response.json()["cached"] is False
    assert len(asked) == 2


def test_a_search_that_failed_is_not_kept_and_the_next_search_asks_again(
    client: TestClient,
    csrf_token: str,
    connected: None,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answering(monkeypatch, CallFailed("Couldn't connect to www.virustotal.com:443."))
    assert search(client, csrf_token, ADDRESS).status_code == 502
    age_every_lookup(session, timedelta(minutes=1))
    asked = answering(monkeypatch, virustotal.Unknown())

    response = search(client, csrf_token, ADDRESS)

    assert response.status_code == 200
    assert response.json()["cached"] is False
    assert len(asked) == 1


def test_a_search_answered_lately_is_answered_from_what_was_kept_while_the_daily_quota_holds(
    client: TestClient,
    csrf_token: str,
    connected: None,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answering(monkeypatch, virustotal.Reported(report=REPORT))
    first = search(client, csrf_token, ADDRESS)
    limit_at(session, store.LIMITED, utcnow())
    asked = answering(monkeypatch, virustotal.Unknown())

    second = search(client, csrf_token, ADDRESS)

    assert (first.status_code, second.status_code) == (200, 200)
    assert (second.json()["cached"], second.json()["judgement"]) == (True, "malicious")
    assert second.json()["checked_at"] == first.json()["checked_at"]
    assert asked == []


# -- what is kept, and what a search says of it

KNOWN = "/api/threat-intel/subjects"
CLEAN = replace(REPORT, malicious=0, suspicious=0, owner="Tidy Networks")


def age_the_answer(session: Session, age: timedelta) -> None:
    """Moves the one answer kept back by ``age``, and its lookups with it."""
    [kept] = session.scalars(select(IntelSubject)).all()
    kept.checked_at = utcnow() - age
    age_every_lookup(session, age)


def test_a_search_says_what_is_kept_of_its_subject(
    client: TestClient,
    csrf_token: str,
    connected: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answering(monkeypatch, virustotal.Reported(report=REPORT))

    body = search(client, csrf_token, ADDRESS).json()

    assert (body["cached"], body["stale"], body["notice"]) == (False, False, None)
    assert (body["checks"], body["repeatable"]) == (1, True)
    assert body["first_checked_at"] == body["checked_at"]
    assert (body["changed_at"], body["previous_judgement"]) == (None, None)
    checked = datetime.fromisoformat(body["checked_at"])
    assert datetime.fromisoformat(body["fresh_until"]) == checked + store.SOONER


def test_a_search_can_ask_again_while_the_answer_is_fresh_and_says_what_changed(
    client: TestClient,
    csrf_token: str,
    connected: None,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answering(monkeypatch, virustotal.Reported(report=CLEAN))
    first = search(client, csrf_token, ADDRESS).json()
    age_every_lookup(session, timedelta(minutes=1))
    asked = answering(monkeypatch, virustotal.Reported(report=REPORT))

    body = search(client, csrf_token, ADDRESS, refresh=True).json()

    assert len(asked) == 1
    assert (body["cached"], body["judgement"], body["checks"]) == (False, "malicious", 2)
    assert body["first_checked_at"] == first["checked_at"]
    assert (body["changed_at"], body["previous_judgement"]) == (body["checked_at"], "clean")


def test_an_old_answer_is_shown_while_the_daily_quota_holds_and_says_why_it_is_old(
    client: TestClient,
    csrf_token: str,
    connected: None,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answering(monkeypatch, virustotal.Reported(report=REPORT))
    first = search(client, csrf_token, ADDRESS).json()
    age_the_answer(session, timedelta(days=9))
    limit_at(session, store.LIMITED, utcnow())
    asked = answering(monkeypatch, virustotal.Unknown())

    response = search(client, csrf_token, ADDRESS)

    assert response.status_code == 200
    body = response.json()
    assert (body["cached"], body["stale"], body["judgement"]) == (True, True, "malicious")
    assert body["notice"] == "VirusTotal's daily limit is reached. Searches resume at 00:00 UTC."
    assert body["checked_at"] != first["checked_at"]
    assert asked == []


def test_an_answer_asked_for_again_too_soon_is_shown_as_kept_and_says_when_to_try(
    client: TestClient,
    csrf_token: str,
    connected: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = answering(monkeypatch, virustotal.Reported(report=REPORT))
    search(client, csrf_token, ADDRESS)

    response = search(client, csrf_token, ADDRESS, refresh=True)

    assert response.status_code == 200
    body = response.json()
    assert (body["cached"], body["stale"]) == (True, False)
    assert body["notice"].startswith("VirusTotal's limit on searches is reached. Try again in ")
    assert len(asked) == 1


@pytest.mark.parametrize(
    ("answer", "notice"),
    [
        (virustotal.Failed("VirusTotal answered HTTP 500."), "VirusTotal answered HTTP 500."),
        (
            virustotal.Limited(until=virustotal.next_reset(utcnow())),
            "VirusTotal's daily limit is reached. Searches resume at 00:00 UTC.",
        ),
        (
            virustotal.Throttled(until=utcnow() + timedelta(minutes=1)),
            "VirusTotal asked for fewer requests. Try again in ",
        ),
    ],
)
def test_an_old_answer_is_shown_when_asking_again_gets_no_answer(
    client: TestClient,
    csrf_token: str,
    connected: None,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    answer: object,
    notice: str,
) -> None:
    answering(monkeypatch, virustotal.Reported(report=REPORT))
    search(client, csrf_token, ADDRESS)
    age_the_answer(session, timedelta(days=9))
    asked = answering(monkeypatch, answer)

    response = search(client, csrf_token, ADDRESS)

    assert response.status_code == 200
    body = response.json()
    assert (body["cached"], body["stale"], body["judgement"]) == (True, True, "malicious")
    assert body["notice"].startswith(notice)
    assert len(asked) == 1
    session.expire_all()
    [kept] = session.scalars(select(IntelSubject)).all()
    assert kept.checks == 1


def test_the_answers_kept_are_for_a_signed_in_user(client: TestClient) -> None:
    assert client.get(KNOWN).status_code == 401


def test_nothing_kept_is_an_empty_list(client: TestClient, csrf_token: str) -> None:
    assert client.get(KNOWN).json() == {
        "total": 0,
        "counts": {"malicious": 0, "suspicious": 0, "clean": 0, "unknown": 0},
        "items": [],
    }


def keep(session: Session, text: str, answer: store.Answered, when: datetime) -> None:
    store.keep(session, virustotal.PROVIDER, subjects.parse(text), answer, when)
    session.commit()


@pytest.fixture
def kept(session: Session) -> datetime:
    """Four answers kept, a minute apart, and one of another service. Returns the newest's time."""
    now = utcnow()
    keep(session, ADDRESS, virustotal.Reported(REPORT), now - timedelta(minutes=3))
    keep(session, "tidy.example.org", virustotal.Reported(CLEAN), now - timedelta(minutes=2))
    keep(session, "https://example.com/login?next=1", virustotal.Unknown(), now)
    keep(
        session,
        "odd.example.net",
        virustotal.Reported(replace(REPORT, malicious=0, owner="100%_odd Hosting")),
        now - timedelta(days=30),
    )
    store.keep(session, "another", subjects.parse("1.1.1.1"), virustotal.Reported(REPORT), now)
    session.commit()
    return now


def test_the_answers_kept_are_listed_newest_first_with_their_counts(
    client: TestClient, csrf_token: str, kept: datetime
) -> None:
    body = client.get(KNOWN).json()

    assert body["total"] == 4
    assert body["counts"] == {"malicious": 1, "suspicious": 1, "clean": 1, "unknown": 1}
    assert [(item["kind"], item["subject"], item["judgement"]) for item in body["items"]] == [
        ("url", "example.com", "unknown"),
        ("domain", "tidy.example.org", "clean"),
        ("ip", ADDRESS, "malicious"),
        ("domain", "odd.example.net", "suspicious"),
    ]
    assert all(item["cached"] and item["notice"] is None for item in body["items"])
    assert [item["stale"] for item in body["items"]] == [False, False, False, True]


def test_a_kept_web_address_shows_its_host_and_cannot_be_searched_again_from_the_list(
    client: TestClient, csrf_token: str, kept: datetime, session: Session
) -> None:
    [item] = client.get(KNOWN, params={"kind": "url"}).json()["items"]

    key = subjects.url_key("https://example.com/login?next=1")
    assert (item["subject"], item["repeatable"]) == ("example.com", False)
    assert item["link"] == f"https://www.virustotal.com/gui/url/{key}"

    for row in session.scalars(select(IntelSubject).where(IntelSubject.kind == "url")):
        row.host = None
    session.commit()
    [item] = client.get(KNOWN, params={"kind": "url"}).json()["items"]
    assert item["subject"] == "A web address"


def test_the_answers_kept_are_filtered_by_judgement_and_the_counts_stay_whole(
    client: TestClient, csrf_token: str, kept: datetime
) -> None:
    body = client.get(KNOWN, params={"judgement": "malicious"}).json()

    assert body["total"] == 1
    assert body["counts"] == {"malicious": 1, "suspicious": 1, "clean": 1, "unknown": 1}
    [item] = body["items"]
    assert (item["subject"], item["repeatable"]) == (ADDRESS, True)
    assert item["link"] == f"https://www.virustotal.com/gui/ip-address/{ADDRESS}"


def test_the_answers_kept_are_filtered_by_kind_and_the_counts_follow(
    client: TestClient, csrf_token: str, kept: datetime
) -> None:
    body = client.get(KNOWN, params={"kind": "domain"}).json()

    assert body["total"] == 2
    assert body["counts"] == {"malicious": 0, "suspicious": 1, "clean": 1, "unknown": 0}


@pytest.mark.parametrize(
    ("text", "found"),
    [
        ("TIDY.example", ["tidy.example.org"]),
        ("tidy networks", ["tidy.example.org"]),
        (" 184.216 ", [ADDRESS]),
        ("100%_odd", ["odd.example.net"]),
        ("%", ["odd.example.net"]),
        ("_", ["odd.example.net"]),
        ("\\", []),
        ("nothing like it", []),
    ],
)
def test_the_answers_kept_are_searched_by_name_address_or_owner_with_no_wildcards(
    client: TestClient, csrf_token: str, kept: datetime, text: str, found: list[str]
) -> None:
    body = client.get(KNOWN, params={"q": text}).json()

    assert [item["subject"] for item in body["items"]] == found
    assert body["total"] == len(found)


def test_the_answers_kept_come_a_page_at_a_time(
    client: TestClient, csrf_token: str, kept: datetime
) -> None:
    body = client.get(KNOWN, params={"limit": 2, "offset": 2}).json()

    assert body["total"] == 4
    assert [item["subject"] for item in body["items"]] == [ADDRESS, "odd.example.net"]


@pytest.mark.parametrize(
    "params",
    [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"kind": "file"}, {"judgement": "bad"}],
)
def test_a_list_asked_for_wrongly_is_refused(
    client: TestClient, csrf_token: str, params: dict[str, int | str]
) -> None:
    assert client.get(KNOWN, params=params).status_code == 422
