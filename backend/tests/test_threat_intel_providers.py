"""Searching AlienVault OTX and GreyNoise by hand, which works as searching VirusTotal does: what
each is asked about, what is kept under its own name, and the limits of its own."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations import netguard, service
from app.integrations.client import Target
from app.intel import greynoise, otx, store, subjects, virustotal
from app.models import IntegrationConnection, IntelLookup, IntelSubject
from app.models.base import utcnow

URL = "/api/threat-intel/lookups"
KNOWN = "/api/threat-intel/subjects"
ADDRESS = "93.184.216.34"
ORIGINS = {"otx": "https://otx.alienvault.com", "greynoise": "https://api.greynoise.io"}
OTX_REPORT = virustotal.Report(
    malicious=2,
    suspicious=3,
    harmless=0,
    undetected=0,
    reputation=-4,
    analysed_at=datetime(2026, 11, 7, tzinfo=UTC),
    country="RU",
    owner="Example Net",
    asn=64500,
    categories=("Mirai",),
    details=(("Pulses", "5"), ("Malware", "Mirai")),
)
NOISE_REPORT = virustotal.Report(
    malicious=0,
    suspicious=1,
    harmless=0,
    undetected=0,
    reputation=0,
    analysed_at=datetime(2026, 11, 7, tzinfo=UTC),
    details=(("Classification", "unknown"),),
)


def search(
    client: TestClient, token: str, provider: str, subject: str = ADDRESS
) -> tuple[int, dict[str, object]]:
    response = client.post(
        URL, json={"subject": subject, "provider": provider}, headers={"X-CSRF-Token": token}
    )
    return response.status_code, response.json()


def connect(session: Session, integration: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """A tested connection of a service whose key opens."""
    session.add(
        IntegrationConnection(
            integration=integration,
            connection="api",
            base_url=ORIGINS[integration],
            tls_mode="system",
            options={},
            last_success_at=utcnow(),
        )
    )
    session.commit()
    origin = netguard.parse_origin(ORIGINS[integration], allow_http=False)

    def load(*args: object, **kwargs: object) -> Target:
        del args, kwargs
        return Target(
            integration=integration,
            connection="api",
            origin=origin,
            tls_mode="system",
            tls_ca_pem=None,
            tls_fingerprint=None,
            options={},
            secrets={"api_key": "a-key"},
        )

    monkeypatch.setattr(service, "load_target", load)


def answering(monkeypatch: pytest.MonkeyPatch, module: object, answer: object) -> list[object]:
    asked: list[object] = []

    async def look_up(*args: object) -> object:
        asked.append(args)
        return answer

    monkeypatch.setattr(module, "look_up", look_up)
    return asked


@pytest.mark.parametrize(
    ("provider", "name"), [("otx", "AlienVault OTX"), ("greynoise", "GreyNoise")]
)
def test_a_search_needs_the_service_to_be_connected(
    client: TestClient, csrf_token: str, provider: str, name: str
) -> None:
    code, body = search(client, csrf_token, provider)

    assert code == 409
    assert body == {"detail": f"Connect {name} and test it before searching."}


def test_a_search_is_for_a_service_that_there_is(client: TestClient, csrf_token: str) -> None:
    code, _ = search(client, csrf_token, "shodan")

    assert code == 422


@pytest.mark.parametrize(
    ("provider", "subject", "detail"),
    [
        (
            "otx",
            "https://example.com/login",
            "AlienVault OTX answers about IP addresses and domains, not web addresses.",
        ),
        (
            "greynoise",
            "example.com",
            "GreyNoise answers about IP addresses, not domains.",
        ),
        (
            "greynoise",
            "2606:2800:220:1:248:1893:25c8:1946",
            "GreyNoise only answers about IPv4 addresses.",
        ),
    ],
)
def test_a_service_is_not_asked_about_what_it_does_not_answer_about(
    client: TestClient,
    csrf_token: str,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    subject: str,
    detail: str,
) -> None:
    connect(session, provider, monkeypatch)
    module = otx if provider == "otx" else greynoise
    asked = answering(monkeypatch, module, virustotal.Unknown())

    code, body = search(client, csrf_token, provider, subject)

    assert (code, body) == (422, {"detail": detail})
    assert asked == []


def test_an_address_is_reported_by_otx_and_kept_under_otx(
    client: TestClient, csrf_token: str, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    connect(session, "otx", monkeypatch)
    asked = answering(monkeypatch, otx, virustotal.Reported(OTX_REPORT))

    code, body = search(client, csrf_token, "otx")

    assert code == 200
    assert (body["provider"], body["provider_name"]) == ("otx", "AlienVault OTX")
    assert (body["judgement"], body["malicious"], body["suspicious"]) == ("malicious", 2, 3)
    assert body["details"] == [
        {"label": "Pulses", "value": "5"},
        {"label": "Malware", "value": "Mirai"},
    ]
    assert body["link"] == f"https://otx.alienvault.com/indicator/ip/{ADDRESS}"
    assert len(asked) == 1
    [kept] = session.scalars(select(IntelSubject)).all()
    assert (kept.provider, kept.subject) == ("otx", ADDRESS)
    [lookup] = session.scalars(select(IntelLookup)).all()
    assert lookup.provider == "otx"


def test_a_domain_has_a_page_on_otx_and_a_web_address_has_none(
    client: TestClient, csrf_token: str, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    connect(session, "otx", monkeypatch)
    answering(monkeypatch, otx, virustotal.Reported(OTX_REPORT))

    _, body = search(client, csrf_token, "otx", "example.com")

    assert body["link"] == "https://otx.alienvault.com/indicator/domain/example.com"
    store.keep(
        session, "otx", subjects.parse("https://example.org/a"), virustotal.Unknown(), utcnow()
    )
    session.commit()
    listed = client.get(KNOWN, params={"provider": "otx"}).json()
    assert [item["link"] for item in listed["items"] if item["kind"] == "url"] == [None]


def test_an_address_is_reported_by_greynoise_with_its_page(
    client: TestClient, csrf_token: str, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    connect(session, "greynoise", monkeypatch)
    answering(monkeypatch, greynoise, virustotal.Reported(NOISE_REPORT))

    code, body = search(client, csrf_token, "greynoise")

    assert code == 200
    assert (body["provider"], body["provider_name"]) == ("greynoise", "GreyNoise")
    assert body["judgement"] == "suspicious"
    assert body["link"] == f"https://viz.greynoise.io/ip/{ADDRESS}"


def test_a_service_that_gives_no_answer_is_a_bad_gateway_that_names_it(
    client: TestClient, csrf_token: str, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    connect(session, "otx", monkeypatch)
    answering(monkeypatch, otx, virustotal.Failed("OTX didn't accept the key."))

    code, body = search(client, csrf_token, "otx")

    assert (code, body) == (502, {"detail": "OTX didn't accept the key."})


def test_each_service_has_its_own_limits(
    client: TestClient, csrf_token: str, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    connect(session, "otx", monkeypatch)
    session.add(
        IntelLookup(
            provider="otx",
            kind="ip",
            requested_at=utcnow() + timedelta(hours=1),
            outcome=store.LIMITED,
        )
    )
    session.commit()
    asked = answering(monkeypatch, otx, virustotal.Unknown())

    code, body = search(client, csrf_token, "otx")

    assert code == 429
    assert str(body["detail"]).startswith(
        "AlienVault OTX's daily limit is reached. Searches resume"
    )
    assert asked == []


def test_a_search_answered_by_one_service_is_not_answered_from_what_another_kept(
    client: TestClient, csrf_token: str, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    store.keep(
        session,
        virustotal.PROVIDER,
        subjects.parse(ADDRESS),
        virustotal.Reported(OTX_REPORT),
        utcnow(),
    )
    session.commit()
    connect(session, "otx", monkeypatch)
    asked = answering(monkeypatch, otx, virustotal.Reported(OTX_REPORT))

    code, body = search(client, csrf_token, "otx")

    assert (code, body["cached"]) == (200, False)
    assert len(asked) == 1


def test_what_is_kept_is_listed_for_one_service_at_a_time(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    now = utcnow()
    store.keep(session, otx.PROVIDER, subjects.parse(ADDRESS), virustotal.Reported(OTX_REPORT), now)
    store.keep(
        session,
        greynoise.PROVIDER,
        subjects.parse("1.1.1.1"),
        virustotal.Reported(NOISE_REPORT),
        now,
    )
    store.keep(
        session, virustotal.PROVIDER, subjects.parse("example.com"), virustotal.Unknown(), now
    )
    session.commit()

    def subjects_of(provider: str | None) -> list[tuple[str, str]]:
        params = {} if provider is None else {"provider": provider}
        items = client.get(KNOWN, params=params).json()["items"]
        return [(item["provider"], item["subject"]) for item in items]

    assert subjects_of(None) == [("virustotal", "example.com")]
    assert subjects_of("otx") == [("otx", ADDRESS)]
    assert subjects_of("greynoise") == [("greynoise", "1.1.1.1")]
    assert client.get(KNOWN, params={"provider": "shodan"}).status_code == 422


def test_a_ruling_is_one_ruling_whichever_service_is_asked(
    client: TestClient, csrf_token: str, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    connect(session, "otx", monkeypatch)
    answering(monkeypatch, otx, virustotal.Reported(OTX_REPORT))
    client.put(
        "/api/threat-intel/overrides",
        json={"subject": ADDRESS, "verdict": "safe", "note": None},
        headers={"X-CSRF-Token": csrf_token},
    )

    _, body = search(client, csrf_token, "otx")

    assert (body["judgement"], body["reported_judgement"]) == ("clean", "malicious")
