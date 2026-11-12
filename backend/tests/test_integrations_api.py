import json
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import Action, Outcome
from app.config import Settings, get_settings
from app.integrations import netguard, service
from app.integrations.client import Target
from app.intel import connection, store, subjects, virustotal
from app.models import (
    ApiCall,
    AuditEvent,
    CollectorHealth,
    IntegrationConnection,
    IntelLookup,
    IntelSubject,
    User,
)
from app.models.base import utcnow
from app.security import credential_store
from app.security.credential_store import Kind
from tests.helpers import OTHER_ORIGIN
from tests.stubs import Answer, Seen, Serve, StubServer, make_certificate, make_chain

BASE = "/api/integrations"
SECRET = "a-very-secret-api-key-for-tests"


def headers(token: str) -> dict[str, str]:
    return {"X-CSRF-Token": token}


def crowdsec_body(
    server: StubServer, key: str | None = SECRET, **changes: object
) -> dict[str, object]:
    connection: dict[str, object] = {"url": server.url, "secrets": {"api_key": key} if key else {}}
    return {"connections": {"lapi": {**connection, **changes}}}


def put(client: TestClient, token: str, key: str, body: object):
    return client.put(f"{BASE}/{key}", json=body, headers=headers(token))


def test_it_is_only_for_someone_signed_in(client: TestClient, account: User) -> None:
    for method, path in (
        ("get", BASE),
        ("get", f"{BASE}/opnsense"),
        ("put", f"{BASE}/opnsense"),
        ("delete", f"{BASE}/opnsense"),
        ("post", f"{BASE}/opnsense/test"),
        ("post", f"{BASE}/opnsense/certificate"),
        ("get", f"{BASE}/opnsense/calls"),
    ):
        response = client.request(method, path)
        assert response.status_code == 401, (method, path)


def test_a_change_needs_the_security_token_and_an_origin_from_the_app(
    client: TestClient, csrf_token: str
) -> None:
    saved = client.put(f"{BASE}/crowdsec", json={"connections": {}})
    removed = client.delete(f"{BASE}/crowdsec")
    tested = client.post(f"{BASE}/crowdsec/test")
    foreign = client.delete(
        f"{BASE}/crowdsec", headers={**headers(csrf_token), "Origin": OTHER_ORIGIN}
    )

    assert saved.status_code == 403
    assert removed.status_code == 403
    assert tested.status_code == 403
    assert foreign.status_code == 403


def test_every_integration_is_listed_with_whether_it_is_connected(
    client: TestClient, csrf_token: str
) -> None:
    response = client.get(BASE)

    assert response.status_code == 200
    listed = response.json()
    assert [item["key"] for item in listed] == [
        "opnsense",
        "ntopng",
        "wazuh",
        "crowdsec",
        "virustotal",
    ]
    assert listed[0]["name"] == "OPNsense"
    assert "firewall" in listed[0]["provides"]
    assert [item["icon"] for item in listed] == [
        "firewall",
        "traffic",
        "alerts",
        "threats",
        "threats",
    ]
    assert [item["category"] for item in listed] == ["", "", "", "", "Threat intelligence"]
    assert all(item["status"] == "not_connected" for item in listed)
    assert all(item["last_success_at"] is None and item["services"] == [] for item in listed)


def test_an_integration_describes_what_it_takes_to_connect(
    client: TestClient, csrf_token: str
) -> None:
    body = client.get(f"{BASE}/opnsense").json()

    docs_url: str = body["docs_url"]
    assert urlsplit(docs_url).hostname == "docs.opnsense.org"
    assert body["status"] == "not_connected"
    guide = body["guide"]
    assert [part["connection"] for part in guide["parts"]] == ["api", "zenarmor"]
    assert [part["optional"] for part in guide["parts"]] == [False, True]
    assert guide["parts"][0]["steps"][0]["menu"] == ["System", "Access", "Users"]
    source_urls: list[str] = [source["url"] for source in guide["sources"]]
    assert {urlsplit(url).scheme for url in source_urls} == {"https"}
    assert [item["definition"]["key"] for item in body["connections"]] == ["api", "zenarmor"]
    api, zenarmor = body["connections"]
    assert [field["key"] for field in api["definition"]["fields"]] == ["api_key", "api_secret"]
    assert api["definition"]["fields"][0]["kind"] == "secret"
    assert zenarmor["definition"]["optional"] is True
    assert [module["key"] for module in api["modules"]][:3] == ["firewall", "suricata", "crowdsec"]
    assert all(module["state"] is None and module["enabled"] for module in api["modules"])
    assert '"path"' not in json.dumps(body)
    assert (api["url"], api["tls_mode"], api["secrets_set"]) == (None, "system", [])


def test_wazuh_says_its_lets_encrypt_certificate_is_not_the_one_its_other_parts_use(
    client: TestClient, csrf_token: str
) -> None:
    body = client.get(f"{BASE}/wazuh").json()

    manager, indexer = (connection["definition"] for connection in body["connections"])
    assert "dashboard only" in manager["certificate_note"]
    assert "self-signed" in manager["certificate_note"]
    assert "dashboard only" in indexer["certificate_note"]
    assert "root-ca.pem" in indexer["certificate_note"]
    others = [
        connection["definition"]["certificate_note"]
        for key in ("opnsense", "ntopng", "crowdsec")
        for connection in client.get(f"{BASE}/{key}").json()["connections"]
    ]
    assert others == [""] * len(others)


def test_an_integration_that_does_not_exist_is_not_found(
    client: TestClient, csrf_token: str
) -> None:
    requests: list[tuple[str, str, dict[str, object] | None]] = [
        ("get", f"{BASE}/nothing", None),
        ("put", f"{BASE}/nothing", {"connections": {}}),
        ("delete", f"{BASE}/nothing", None),
        ("post", f"{BASE}/nothing/test", None),
        ("post", f"{BASE}/nothing/certificate", {"url": "https://192.168.1.1"}),
        ("get", f"{BASE}/nothing/calls", None),
    ]
    for method, path, body in requests:
        response = client.request(method, path, headers=headers(csrf_token), json=body)
        assert response.status_code == 404, (method, path)
        assert response.json() == {"detail": "There is no such integration."}
    assert client.get(f"{BASE}/Not A Name").status_code == 422


def test_connecting_keeps_the_settings_and_never_sends_a_secret_back(
    client: TestClient, csrf_token: str, serve: Serve, session: Session, settings: Settings
) -> None:
    server = serve(lambda seen: Answer())

    response = put(client, csrf_token, "crowdsec", crowdsec_body(server))

    assert response.status_code == 200
    assert SECRET not in response.text
    body = response.json()
    assert body["status"] == "untested"
    [connection] = body["connections"]
    assert connection["url"] == server.url
    assert connection["secrets_set"] == ["api_key"]
    assert client.get(f"{BASE}/crowdsec").json() == body
    assert SECRET not in client.get(BASE).text
    session.expire_all()
    revealed = credential_store.reveal(
        session, settings, Kind.INTEGRATION, "crowdsec-lapi", "api_key"
    )
    assert revealed == SECRET
    event = session.scalars(select(AuditEvent).order_by(AuditEvent.id.desc())).first()
    assert event is not None
    assert (event.action, event.outcome) == (Action.INTEGRATION_CONNECTED, Outcome.SUCCESS)
    assert event.detail == {"integration": "crowdsec"}
    assert SECRET not in json.dumps(event.detail)


def test_connecting_again_without_the_secret_keeps_it(
    client: TestClient, csrf_token: str, serve: Serve
) -> None:
    server = serve(lambda seen: Answer())
    put(client, csrf_token, "crowdsec", crowdsec_body(server))

    response = put(client, csrf_token, "crowdsec", crowdsec_body(server, key=None))

    assert response.status_code == 200
    assert response.json()["connections"][0]["secrets_set"] == ["api_key"]


def test_a_mistake_is_reported_per_field_in_the_same_shape_as_the_rest(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    body: dict[str, object] = {"connections": {"lapi": {"url": "https://8.8.8.8", "secrets": {}}}}

    response = put(client, csrf_token, "crowdsec", body)

    assert response.status_code == 422
    detail = response.json()["detail"]
    problems = {tuple(item["loc"]): item["msg"] for item in detail}
    assert set(problems) == {
        ("body", "connections", "lapi", "url"),
        ("body", "connections", "lapi", "api_key"),
    }
    assert "isn't a private network address" in problems[("body", "connections", "lapi", "url")]
    assert all(item["type"] == "value_error" for item in detail)
    assert (
        session.scalars(
            select(AuditEvent).where(AuditEvent.action == Action.INTEGRATION_CONNECTED)
        ).all()
        == []
    )
    assert client.get(f"{BASE}/crowdsec").json()["status"] == "not_connected"


def test_a_request_that_is_not_the_right_shape_is_refused_without_quoting_it(
    client: TestClient, csrf_token: str
) -> None:
    body = {
        "connections": {
            "lapi": {"url": "http://192.168.1.4", "secrets": {"api_key": SECRET}, "extra": 1}
        }
    }

    response = put(client, csrf_token, "crowdsec", body)

    assert response.status_code == 422
    assert SECRET not in response.text


def test_disconnecting_forgets_it_and_says_so_in_the_audit_log(
    client: TestClient, csrf_token: str, serve: Serve, session: Session
) -> None:
    server = serve(lambda seen: Answer())
    put(client, csrf_token, "crowdsec", crowdsec_body(server))

    response = client.delete(f"{BASE}/crowdsec", headers=headers(csrf_token))

    after = client.get(f"{BASE}/crowdsec").json()
    again = client.delete(f"{BASE}/crowdsec", headers=headers(csrf_token))
    event = session.scalars(select(AuditEvent).order_by(AuditEvent.id.desc())).first()

    assert response.status_code == 204
    assert after["status"] == "not_connected"
    assert credential_store.entries(session) == []
    assert event is not None
    assert event.action == Action.INTEGRATION_DISCONNECTED
    assert again.status_code == 404


def test_disconnecting_takes_its_collectors_off_the_collectors_and_status_pages_at_once(
    client: TestClient, csrf_token: str, serve: Serve, session: Session
) -> None:
    server = serve(lambda seen: Answer())
    put(client, csrf_token, "crowdsec", crowdsec_body(server))
    session.add(
        CollectorHealth(
            collector="crowdsec-decisions",
            integration="crowdsec",
            connection="lapi",
            interval_seconds=60,
        )
    )
    session.commit()
    before = client.get("/api/collectors").json()["collectors"]
    status_before = [part["key"] for part in client.get("/api/status").json()["parts"]]

    client.delete(f"{BASE}/crowdsec", headers=headers(csrf_token))

    assert [item["integration"] for item in before] == ["crowdsec"]
    assert any(key.endswith("/crowdsec/lapi") for key in status_before)
    assert client.get("/api/collectors").json()["collectors"] == []
    status_after = [part["key"] for part in client.get("/api/status").json()["parts"]]
    assert not any(key.endswith("/crowdsec/lapi") for key in status_after)


def test_a_failed_disconnect_leaves_its_collectors_alone(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    session.add(
        CollectorHealth(
            collector="crowdsec-decisions",
            integration="crowdsec",
            connection="lapi",
            interval_seconds=60,
        )
    )
    session.commit()

    response = client.delete(f"{BASE}/crowdsec", headers=headers(csrf_token))

    assert response.status_code == 404
    assert len(session.scalars(select(CollectorHealth)).all()) == 1


def test_a_test_needs_the_integration_to_be_connected_first(
    client: TestClient, csrf_token: str
) -> None:
    response = client.post(f"{BASE}/crowdsec/test", headers=headers(csrf_token))

    assert response.status_code == 409
    assert response.json() == {"detail": "Connect it first."}


def crowdsec_router(seen: Seen) -> Answer:
    if seen.headers.get("x-api-key") == SECRET:
        return Answer(body="null")
    return Answer(status=403, body='{"message": "access forbidden"}')


def test_a_test_that_works_marks_it_connected_and_logs_the_call(
    client: TestClient, csrf_token: str, serve: Serve, session: Session
) -> None:
    server = serve(crowdsec_router)
    put(client, csrf_token, "crowdsec", crowdsec_body(server))

    response = client.post(f"{BASE}/crowdsec/test", headers=headers(csrf_token))

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["checks"] == [
        {
            "connection": "lapi",
            "ok": True,
            "message": "CrowdSec's local API accepted the key.",
            "certificate_problem": False,
        }
    ]
    assert body["integration"]["status"] == "connected"
    assert body["integration"]["last_success_at"] is not None
    assert body["integration"]["last_error"] is None
    assert SECRET not in response.text
    calls = client.get(f"{BASE}/crowdsec/calls").json()["calls"]
    assert [(call["method"], call["path"], call["status_code"]) for call in calls] == [
        ("GET", "/v1/decisions", 200)
    ]
    assert calls[0]["connection"] == "lapi"
    event = session.scalars(select(AuditEvent).order_by(AuditEvent.id.desc())).first()
    assert event is not None
    assert (event.action, event.outcome) == (Action.INTEGRATION_TESTED, Outcome.SUCCESS)


def test_a_test_that_fails_says_why_and_marks_the_problem(
    client: TestClient, csrf_token: str, serve: Serve, session: Session
) -> None:
    server = serve(crowdsec_router)
    put(client, csrf_token, "crowdsec", crowdsec_body(server, key="not-the-key-at-all"))

    response = client.post(f"{BASE}/crowdsec/test", headers=headers(csrf_token))

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert "CrowdSec didn't accept the credentials" in body["checks"][0]["message"]
    assert body["integration"]["status"] == "problem"
    assert body["integration"]["last_error"] == body["checks"][0]["message"]
    # Nothing to do with a certificate, so nothing to review.
    assert body["checks"][0]["certificate_problem"] is False
    assert body["integration"]["connections"][0]["certificate_problem"] is False
    calls = client.get(f"{BASE}/crowdsec/calls", params={"failed": True}).json()["calls"]
    assert [(call["status_code"], call["error"]) for call in calls] == [(403, "Forbidden")]
    event = session.scalars(select(AuditEvent).order_by(AuditEvent.id.desc())).first()
    assert event is not None
    assert (event.action, event.outcome) == (Action.INTEGRATION_TESTED, Outcome.FAILURE)
    # Fixing it and testing again clears the problem.
    put(client, csrf_token, "crowdsec", crowdsec_body(server))
    assert client.post(f"{BASE}/crowdsec/test", headers=headers(csrf_token)).json()["ok"]
    assert client.get(f"{BASE}/crowdsec").json()["status"] == "connected"


def test_a_test_where_nothing_answers_says_so(
    client: TestClient, csrf_token: str, serve: Serve
) -> None:
    server = serve(crowdsec_router)
    put(client, csrf_token, "crowdsec", crowdsec_body(server))
    server.stop()

    body = client.post(f"{BASE}/crowdsec/test", headers=headers(csrf_token)).json()

    assert body["ok"] is False
    assert f"Couldn't connect to 127.0.0.1:{server.port}" in body["checks"][0]["message"]
    [call] = client.get(f"{BASE}/crowdsec/calls").json()["calls"]
    assert call["status_code"] is None
    assert call["error"] == body["checks"][0]["message"]


def test_a_secret_that_has_gone_is_reported_not_crashed_on(
    client: TestClient, csrf_token: str, serve: Serve, session: Session
) -> None:
    server = serve(crowdsec_router)
    put(client, csrf_token, "crowdsec", crowdsec_body(server))
    credential_store.remove(session, Kind.INTEGRATION, "crowdsec-lapi", "api_key")
    session.commit()

    body = client.post(f"{BASE}/crowdsec/test", headers=headers(csrf_token)).json()

    assert body["ok"] is False
    assert body["checks"][0]["message"] == (
        "Local API: API key is missing or can't be opened. Enter it again."
    )
    assert server.seen == []
    assert body["integration"]["status"] == "problem"


def test_a_connection_that_was_never_saved_is_reported_not_crashed_on(
    client: TestClient, csrf_token: str, serve: Serve, session: Session
) -> None:
    server = serve(lambda seen: Answer())
    now = datetime.now(UTC)
    session.add(
        IntegrationConnection(
            integration="wazuh",
            connection="indexer",
            base_url=server.url,
            tls_mode="system",
            options={"username": "reader"},
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()

    body = client.post(f"{BASE}/wazuh/test", headers=headers(csrf_token)).json()

    assert body["ok"] is False
    assert [check["message"] for check in body["checks"]] == [
        "The Manager API isn't set up.",
        "Indexer: Password is missing or can't be opened. Enter it again.",
    ]
    assert server.seen == []


def test_opnsense_over_tls_finds_the_services_and_remembers_them(
    client: TestClient, csrf_token: str, serve: Serve
) -> None:
    certificate = make_certificate()

    def router(seen: Seen) -> Answer:
        if seen.path == "/api/diagnostics/system/system_information":
            return Answer(body='{"versions": ["OPNsense 25.7"]}')
        if seen.path == "/api/ids/service/status":
            return Answer(body='{"status": "running"}')
        return Answer(status=404)

    server = serve(router, certificate)
    api = {
        "url": server.url,
        "tls_mode": "pinned",
        "tls_fingerprint": certificate.fingerprint,
        "secrets": {"api_key": "key-123456", "api_secret": "secret-123456"},
        "disabled_modules": ["crowdsec"],
    }
    response = put(client, csrf_token, "opnsense", {"connections": {"api": api}})
    assert response.status_code == 200

    body = client.post(f"{BASE}/opnsense/test", headers=headers(csrf_token)).json()

    assert body["ok"] is True
    assert body["checks"][0]["message"] == (
        "OPNsense answered: OPNsense 25.7. Services found: Suricata (running)."
    )
    integration = body["integration"]
    assert integration["status"] == "connected"
    assert [(item["key"], item["state"]) for item in integration["services"]] == [
        ("firewall", "running"),
        ("suricata", "running"),
    ]
    modules = {item["key"]: item for item in integration["connections"][0]["modules"]}
    assert modules["suricata"]["state"] == "running"
    assert modules["kea"]["state"] == "not_installed"
    assert modules["crowdsec"] == {
        **modules["crowdsec"],
        "state": "not_installed",
        "enabled": False,
    }
    assert client.get(BASE).json()[0]["services"] == integration["services"]
    # The API log has the request for each, from the first to the last.
    calls = client.get(f"{BASE}/opnsense/calls", params={"limit": 200}).json()["calls"]
    assert calls[-1]["path"] == "/api/diagnostics/system/system_information"
    assert len(calls) == 11


def test_the_certificate_a_system_presents_can_be_looked_at(
    client: TestClient, csrf_token: str, serve: Serve
) -> None:
    certificate = make_certificate("fw.example")
    server = serve(lambda seen: Answer(), certificate)

    response = client.post(
        f"{BASE}/opnsense/certificate", json={"url": server.url}, headers=headers(csrf_token)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["fingerprint"] == certificate.fingerprint
    assert body["subject"] == "CN=fw.example"
    assert body["names"] == ["fw.example", "127.0.0.1"]
    assert body["not_before"] < body["not_after"]
    assert body["self_signed"] is True
    assert body["issuers"] == []
    # Chosen as a new connection is, it is not accepted, and it says why.
    assert body["accepted"] is False
    assert body["verdict"].startswith("The certificate isn't trusted: it vouches for itself")
    assert body["verdict"].endswith("trust it below.")
    assert server.seen == []


def certificate_of(
    client: TestClient, csrf_token: str, server: StubServer, *, key: str = "wazuh", **choice: object
) -> dict[str, object]:
    response = client.post(
        f"{BASE}/{key}/certificate",
        json={"url": server.url, **choice},
        headers=headers(csrf_token),
    )
    assert response.status_code == 200
    return response.json()


def test_the_certificate_found_is_judged_by_how_the_connection_is_set_to_check_it(
    client: TestClient, csrf_token: str, serve: Serve
) -> None:
    certificate = make_certificate("wazuh.example")
    server = serve(lambda seen: Answer(), certificate)

    pinned = certificate_of(
        client, csrf_token, server, tls_mode="pinned", tls_fingerprint=certificate.fingerprint
    )
    # A fingerprint is understood however it is written.
    typed = certificate_of(
        client,
        csrf_token,
        server,
        tls_mode="pinned",
        tls_fingerprint=certificate.fingerprint.replace(":", " ").lower(),
    )
    changed = certificate_of(
        client,
        csrf_token,
        server,
        tls_mode="pinned",
        tls_fingerprint=make_certificate().fingerprint,
    )
    nothing = certificate_of(
        client, csrf_token, server, tls_mode="pinned", tls_fingerprint="not one"
    )
    authority = certificate_of(
        client, csrf_token, server, tls_mode="ca", tls_ca_pem=certificate.pem
    )

    assert (pinned["accepted"], typed["accepted"]) == (True, True)
    assert pinned["verdict"] == "It is the certificate you trusted."
    assert changed["accepted"] is False
    assert str(changed["verdict"]).startswith("The certificate has changed")
    assert (nothing["accepted"], nothing["verdict"]) == (False, "No certificate is trusted yet.")
    assert authority["accepted"] is True


def test_the_certificates_sent_with_the_one_found_are_listed(
    client: TestClient, csrf_token: str, serve: Serve
) -> None:
    chain = make_chain()
    server = serve(lambda seen: Answer(), chain.full)

    body = certificate_of(client, csrf_token, server)

    assert body["self_signed"] is False
    assert [issuer["subject"] for issuer in body["issuers"]] == ["CN=Test Intermediate"]  # type: ignore[attr-defined]


def test_a_certificate_is_not_judged_by_a_way_of_checking_there_is_not(
    client: TestClient, csrf_token: str, serve: Serve
) -> None:
    server = serve(lambda seen: Answer(), make_certificate())

    response = client.post(
        f"{BASE}/wazuh/certificate",
        json={"url": server.url, "tls_mode": "anything"},
        headers=headers(csrf_token),
    )

    assert response.status_code == 422
    [problem] = response.json()["detail"]
    assert problem["loc"] == ["body", "tls_mode"]


def test_a_test_that_fails_over_the_certificate_says_so_and_it_can_be_trusted_and_tested_again(
    client: TestClient, csrf_token: str, serve: Serve
) -> None:
    certificate = make_certificate()
    server = serve(crowdsec_router, certificate)
    body = crowdsec_body(server)

    put(client, csrf_token, "crowdsec", body)
    failed = client.post(f"{BASE}/crowdsec/test", headers=headers(csrf_token)).json()

    assert failed["ok"] is False
    assert failed["checks"][0]["certificate_problem"] is True
    assert failed["integration"]["connections"][0]["certificate_problem"] is True
    # Reading the integration again says so too, as a page that is opened later does.
    again = client.get(f"{BASE}/crowdsec").json()
    assert again["connections"][0]["certificate_problem"] is True

    found = certificate_of(client, csrf_token, server, key="crowdsec")
    assert found["accepted"] is False
    put(
        client,
        csrf_token,
        "crowdsec",
        crowdsec_body(server, tls_mode="pinned", tls_fingerprint=found["fingerprint"]),
    )
    passed = client.post(f"{BASE}/crowdsec/test", headers=headers(csrf_token)).json()

    assert passed["ok"] is True
    assert passed["checks"][0]["certificate_problem"] is False


def test_a_pinned_certificate_that_changes_fails_the_test_and_asks_to_be_trusted_again(
    client: TestClient, csrf_token: str, serve: Serve
) -> None:
    server = serve(crowdsec_router, make_certificate())
    body = crowdsec_body(server, tls_mode="pinned", tls_fingerprint=make_certificate().fingerprint)
    put(client, csrf_token, "crowdsec", body)

    failed = client.post(f"{BASE}/crowdsec/test", headers=headers(csrf_token)).json()

    assert failed["ok"] is False
    assert failed["checks"][0]["message"].startswith("The certificate has changed")
    assert failed["checks"][0]["certificate_problem"] is True
    assert server.seen == []


@pytest.mark.parametrize(
    ("url", "message"),
    [
        ("http://192.168.1.1", "only offered over https://"),
        ("nonsense", "Start the address with https://"),
        ("https://203.0.113.5", "isn't a private network address"),
    ],
)
def test_a_certificate_is_only_looked_up_for_a_proper_address(
    client: TestClient, csrf_token: str, url: str, message: str
) -> None:
    client.app.state.address_policy = netguard.HOME_NETWORK  # type: ignore[attr-defined]

    response = client.post(
        f"{BASE}/opnsense/certificate", json={"url": url}, headers=headers(csrf_token)
    )

    assert response.status_code == 422
    [problem] = response.json()["detail"]
    assert problem["loc"] == ["body", "url"]
    assert message in problem["msg"]


def test_a_certificate_lookup_that_fails_says_why(
    client: TestClient, csrf_token: str, serve: Serve
) -> None:
    server = serve(lambda seen: Answer())

    response = client.post(
        f"{BASE}/opnsense/certificate",
        json={"url": server.url.replace("http", "https")},
        headers=headers(csrf_token),
    )

    assert response.status_code == 422
    assert "Couldn't make a secure connection" in response.json()["detail"][0]["msg"]


def test_a_service_on_the_internet_has_no_certificate_to_look_up(
    client: TestClient, csrf_token: str
) -> None:
    response = client.post(
        f"{BASE}/virustotal/certificate",
        json={"url": "https://www.virustotal.com"},
        headers=headers(csrf_token),
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": (
            "There is no certificate to look up for VirusTotal. Its certificate is checked by the "
            "certificates this computer trusts."
        )
    }


def test_a_failed_test_on_the_internet_never_offers_a_certificate_to_review(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    now = datetime.now(UTC)
    message = "The certificate has changed: this system now presents something else."
    session.add_all(
        [
            IntegrationConnection(
                integration="virustotal",
                connection="api",
                base_url="https://www.virustotal.com",
                tls_mode="system",
                options={"tier": "free"},
                last_error=message,
                created_at=now,
                updated_at=now,
            ),
            IntegrationConnection(
                integration="crowdsec",
                connection="lapi",
                base_url="http://192.168.1.4:8080",
                tls_mode="system",
                options={},
                last_error=message,
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    session.commit()

    internet = client.get(f"{BASE}/virustotal").json()["connections"][0]
    home = client.get(f"{BASE}/crowdsec").json()["connections"][0]

    assert internet["last_error"] == message
    assert internet["certificate_problem"] is False
    assert home["certificate_problem"] is True


NTOPNG_TOKEN = "an-ntopng-token-for-tests"


def ntopng_draft(server: StubServer, **changes: object) -> dict[str, object]:
    return {
        "url": server.url,
        "options": {"auth": "token", "interface_id": 0},
        "secrets": {"token": NTOPNG_TOKEN},
        **changes,
    }


def look_up(client: TestClient, token: str, body: object, field: str = "interface_id"):
    return client.post(
        f"{BASE}/ntopng/connections/api/lookup/{field}", json=body, headers=headers(token)
    )


def test_ntopng_lists_its_interfaces_for_the_address_and_token_typed_so_far(
    client: TestClient, csrf_token: str, serve: Serve, session: Session
) -> None:
    from e2e.stand_ins import ntopng

    server = serve(ntopng(NTOPNG_TOKEN))

    response = look_up(client, csrf_token, ntopng_draft(server))

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["message"] == "ntopng lists 2 interfaces."
    assert [(entry["value"], entry["label"], entry["quiet"]) for entry in body["entries"]] == [
        ("0", "eth0", False),
        ("1", "LAN (eth1)", True),
    ]
    assert "live packet capture" in body["entries"][1]["detail"]
    assert NTOPNG_TOKEN not in response.text
    # Nothing was saved, and the requests are in the API log.
    assert client.get(f"{BASE}/ntopng").json()["status"] == "not_connected"
    assert session.scalars(select(IntegrationConnection)).all() == []
    calls = client.get(f"{BASE}/ntopng/calls").json()["calls"]
    assert {call["path"] for call in calls} == {
        "/lua/rest/v2/get/ntopng/interfaces.lua",
        "/lua/rest/v2/get/interface/data.lua",
    }


def test_a_token_left_blank_is_the_one_kept(
    client: TestClient, csrf_token: str, serve: Serve
) -> None:
    from e2e.stand_ins import ntopng

    server = serve(ntopng(NTOPNG_TOKEN))
    saved = put(client, csrf_token, "ntopng", {"connections": {"api": ntopng_draft(server)}})
    assert saved.status_code == 200

    response = look_up(client, csrf_token, ntopng_draft(server, secrets={}))

    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_a_login_ntopng_refuses_is_said_in_the_answer_not_as_an_error(
    client: TestClient, csrf_token: str, serve: Serve
) -> None:
    from e2e.stand_ins import ntopng

    server = serve(ntopng("some-other-token"))

    response = look_up(client, csrf_token, ntopng_draft(server))

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert "ntopng" in body["message"]
    assert body["entries"] == []


def test_a_lookup_before_the_connection_is_filled_in_says_what_to_fix_first(
    client: TestClient, csrf_token: str, serve: Serve
) -> None:
    server = serve(lambda seen: Answer())

    nothing_typed = look_up(client, csrf_token, ntopng_draft(server, secrets={}))
    far_away = look_up(client, csrf_token, ntopng_draft(server, url="http://8.8.8.8"))

    assert nothing_typed.status_code == 422
    assert (
        nothing_typed.json()["detail"]
        == "Fill in the connection first. Authentication token: Enter a value."
    )
    assert far_away.status_code == 422
    assert far_away.json()["detail"].startswith("Fill in the connection first. Address: 8.8.8.8")
    assert server.seen == []


def test_a_lookup_whose_kept_secret_cannot_be_opened_says_so(
    client: TestClient, csrf_token: str, serve: Serve, settings: Settings
) -> None:
    from pydantic import SecretStr

    from e2e.stand_ins import ntopng

    server = serve(ntopng(NTOPNG_TOKEN))
    put(client, csrf_token, "ntopng", {"connections": {"api": ntopng_draft(server)}})
    other = settings.model_copy(
        update={"secret_key": SecretStr("a different key altogether, 32+ bytes")}
    )
    client.app.dependency_overrides[get_settings] = lambda: other  # type: ignore[attr-defined]

    response = look_up(client, csrf_token, ntopng_draft(server, secrets={}))

    assert response.status_code == 422
    assert "missing or can't be opened" in response.json()["detail"]


@pytest.mark.parametrize(
    "path",
    [
        "/ntopng/connections/api/lookup/username",
        "/ntopng/connections/other/lookup/interface_id",
        "/opnsense/connections/api/lookup/interface_id",
        "/nowhere/connections/api/lookup/interface_id",
    ],
)
def test_there_is_only_a_lookup_where_one_is_defined(
    client: TestClient, csrf_token: str, serve: Serve, path: str
) -> None:
    server = serve(lambda seen: Answer())

    response = client.post(f"{BASE}{path}", json=ntopng_draft(server), headers=headers(csrf_token))

    assert response.status_code == 404


def test_a_lookup_needs_the_security_token_and_someone_signed_in(
    client: TestClient, csrf_token: str, serve: Serve
) -> None:
    server = serve(lambda seen: Answer())
    path = f"{BASE}/ntopng/connections/api/lookup/interface_id"

    assert client.post(path, json=ntopng_draft(server)).status_code == 403
    assert (
        client.post(
            path, json=ntopng_draft(server), headers={**headers(csrf_token), "Origin": OTHER_ORIGIN}
        ).status_code
        == 403
    )


def test_a_lookup_is_only_for_someone_signed_in(client: TestClient, account: User) -> None:
    response = client.post(f"{BASE}/ntopng/connections/api/lookup/interface_id", json={})

    assert response.status_code == 401


def add_calls(session: Session) -> list[int]:
    start = datetime(2099, 1, 1, tzinfo=UTC)
    rows = [
        ApiCall(
            occurred_at=start + timedelta(minutes=index),
            integration="ntopng",
            connection="api",
            method=method,
            path=f"/call/{index}",
            status_code=status,
            duration_ms=index,
            error=error,
        )
        for index, (method, status, error) in enumerate(
            [("GET", 200, None), ("POST", 500, "Internal Server Error"), ("GET", None, "refused")]
        )
    ]
    session.add_all(rows)
    session.commit()
    return [row.id for row in rows]


def test_the_api_log_is_listed_newest_first_and_can_be_filtered(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    first, second, third = add_calls(session)

    def listed(**query: object) -> list[int]:
        response = client.get(f"{BASE}/ntopng/calls", params=query)  # type: ignore[arg-type]
        assert response.status_code == 200
        return [call["id"] for call in response.json()["calls"]]

    assert listed() == [third, second, first]
    assert listed(method="POST") == [second]
    assert listed(failed=True) == [third, second]
    assert listed(failed=False) == [first]
    assert listed(connection="api", since="2099-01-01T00:01:00Z") == [third, second]
    assert listed(until="2099-01-01T00:01:00Z") == [first]
    assert listed(connection="other") == []
    call = client.get(f"{BASE}/ntopng/calls", params={"limit": 1}).json()
    assert call["next_before"] == third
    assert set(call["calls"][0]) == {
        "id",
        "occurred_at",
        "connection",
        "method",
        "path",
        "status_code",
        "duration_ms",
        "error",
    }
    older = client.get(f"{BASE}/ntopng/calls", params={"limit": 1, "before": third}).json()
    assert [item["id"] for item in older["calls"]] == [second]


@pytest.mark.parametrize("query", [{"limit": 0}, {"limit": 201}, {"before": 0}, {"since": "soon"}])
def test_a_bad_api_log_query_is_refused(
    client: TestClient, csrf_token: str, query: dict[str, object]
) -> None:
    assert client.get(f"{BASE}/ntopng/calls", params=query).status_code == 422  # type: ignore[arg-type]


def test_the_policy_and_recorder_come_from_the_app() -> None:
    from app.api import integrations
    from app.integrations.apilog import ApiLogRecorder
    from app.main import create_app

    app = create_app()

    assert app.state.address_policy is netguard.HOME_NETWORK
    assert isinstance(integrations.api_log_recorder(), ApiLogRecorder)


def test_an_ollama_may_be_on_the_computer_unless_that_is_the_container() -> None:
    from app.config import Settings
    from app.main import create_app

    bare = create_app(Settings(in_container=False))
    boxed = create_app(Settings(in_container=True))

    assert bare.state.local_ai_policy is netguard.OLLAMA_ON_THIS_COMPUTER
    assert boxed.state.local_ai_policy is netguard.OLLAMA_IN_CONTAINER
    # Integrations never are allowed to be on the machine itself.
    assert bare.state.address_policy is boxed.state.address_policy is netguard.HOME_NETWORK


VT_URL = f"{BASE}/virustotal"


@pytest.fixture
def virustotal_key(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """A VirusTotal connection that was tested before, whose key opens."""
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
    session.add(
        IntegrationConnection(
            integration="virustotal",
            connection="api",
            base_url="https://www.virustotal.com",
            tls_mode="system",
            options={"tier": "free"},
            last_success_at=utcnow() - timedelta(days=1),
        )
    )
    session.commit()


def answer_by_virustotal(monkeypatch: pytest.MonkeyPatch, answer: object) -> list[object]:
    """Makes VirusTotal answer with the answer given, or raise it. Returns the requests made."""
    asked: list[object] = []

    async def look_up(*args: object) -> object:
        asked.append(args)
        if isinstance(answer, BaseException):
            raise answer
        return answer

    monkeypatch.setattr(virustotal, "look_up", look_up)
    return asked


def test_testing_virustotal_while_the_daily_quota_holds_sends_nothing(
    client: TestClient,
    csrf_token: str,
    virustotal_key: None,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session.add(
        IntelLookup(provider="virustotal", kind="ip", requested_at=utcnow(), outcome=store.LIMITED)
    )
    session.commit()
    asked = answer_by_virustotal(monkeypatch, virustotal.Unknown())

    response = client.post(f"{VT_URL}/test", headers=headers(csrf_token))

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["checks"][0]["message"].startswith("VirusTotal's daily limit is reached")
    assert body["integration"]["status"] == "connected"
    assert body["integration"]["last_error"] is None
    assert body["integration"]["pause"]["daily"] is True
    assert asked == []


def test_testing_virustotal_with_a_key_it_accepts_keeps_the_test_as_a_lookup(
    client: TestClient,
    csrf_token: str,
    virustotal_key: None,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = answer_by_virustotal(monkeypatch, virustotal.Unknown())

    response = client.post(f"{VT_URL}/test", headers=headers(csrf_token))

    assert response.status_code == 200
    body = response.json()
    assert body["checks"][0]["message"] == (
        "VirusTotal accepted the key. It is set to the free access level."
    )
    assert body["integration"]["status"] == "connected"
    assert len(asked) == 1
    [lookup] = session.scalars(select(IntelLookup)).all()
    assert (lookup.kind, lookup.outcome, lookup.address, lookup.subject) == (
        "test",
        store.UNKNOWN,
        None,
        "8.8.8.8",
    )
    [kept] = session.scalars(select(IntelSubject)).all()
    assert (kept.kind, kept.subject, kept.outcome) == ("ip", "8.8.8.8", store.UNKNOWN)


def test_testing_virustotal_asks_even_when_its_address_was_answered_lately(
    client: TestClient,
    csrf_token: str,
    virustotal_key: None,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A search would be answered from what was kept. A test checks the key, so it is sent.
    answered = subjects.of_address(ip_address("8.8.8.8"))
    store.keep(session, "virustotal", answered, virustotal.Unknown(), utcnow())
    session.commit()
    asked = answer_by_virustotal(monkeypatch, virustotal.Unknown())

    response = client.post(f"{VT_URL}/test", headers=headers(csrf_token))

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert len(asked) == 1
    assert len(session.scalars(select(IntelSubject)).all()) == 1


def test_testing_virustotal_with_a_key_it_refuses_fails_and_says_why(
    client: TestClient,
    csrf_token: str,
    virustotal_key: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answer_by_virustotal(
        monkeypatch,
        virustotal.Failed(
            "VirusTotal didn't accept the key. Copy it again from your VirusTotal account."
        ),
    )

    response = client.post(f"{VT_URL}/test", headers=headers(csrf_token))

    body = response.json()
    assert body["ok"] is False
    assert body["integration"]["status"] == "problem"
    assert body["integration"]["last_error"].startswith("VirusTotal didn't accept the key.")


def test_testing_virustotal_when_it_asks_to_slow_down_passes_and_keeps_the_pause(
    client: TestClient,
    csrf_token: str,
    virustotal_key: None,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answer_by_virustotal(monkeypatch, virustotal.Throttled(until=utcnow() + timedelta(minutes=1)))

    response = client.post(f"{VT_URL}/test", headers=headers(csrf_token))

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["checks"][0]["message"] == connection.THROTTLED
    assert body["integration"]["status"] == "connected"
    assert body["integration"]["last_error"] is None
    assert body["integration"]["last_success_at"] is not None
    assert body["integration"]["pause"]["daily"] is False
    [lookup] = session.scalars(select(IntelLookup)).all()
    assert lookup.outcome == store.THROTTLED


def test_testing_virustotal_soon_after_a_lookup_waits_and_sends_nothing(
    client: TestClient,
    csrf_token: str,
    virustotal_key: None,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session.add(
        IntelLookup(
            provider="virustotal",
            kind="ip",
            address=ip_address("93.184.216.34"),
            requested_at=utcnow() - timedelta(seconds=5),
            outcome=store.REPORTED,
        )
    )
    session.commit()
    asked = answer_by_virustotal(monkeypatch, virustotal.Unknown())

    response = client.post(f"{VT_URL}/test", headers=headers(csrf_token))

    assert response.status_code == 429
    assert asked == []


def test_saving_and_testing_again_while_a_limit_holds_the_test_keeps_the_connection_tested(
    client: TestClient,
    csrf_token: str,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = {
        "connections": {
            "api": {"url": "https://www.virustotal.com", "options": {"tier": "free"}},
        }
    }
    first = {
        "connections": {
            "api": {**body["connections"]["api"], "secrets": {"api_key": "vt-key-123456"}},
        }
    }
    answer_by_virustotal(monkeypatch, virustotal.Throttled(until=utcnow() + timedelta(minutes=1)))

    # The sandbox may not reach the internet, and no address is looked up by this test.
    def reachable(*_: object, **__: object) -> None:
        return None

    monkeypatch.setattr(netguard, "check_reachable", reachable)
    assert put(client, csrf_token, "virustotal", first).json()["status"] == "untested"
    tested = client.post(f"{VT_URL}/test", headers=headers(csrf_token))
    assert tested.json()["integration"]["status"] == "connected"

    # VirusTotal has just asked for fewer requests, so a second test has to wait. Saving what is
    # already saved doesn't take back that the key was tested.
    saved = put(client, csrf_token, "virustotal", body)
    waiting = client.post(f"{VT_URL}/test", headers=headers(csrf_token))

    assert saved.json()["status"] == "connected"
    assert waiting.status_code == 429
    assert client.get(VT_URL).json()["status"] == "connected"


def test_the_list_shows_the_daily_quota_that_holds_virustotal_and_nothing_else(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    session.add(
        IntelLookup(provider="virustotal", kind="ip", requested_at=utcnow(), outcome=store.LIMITED)
    )
    session.commit()

    items = client.get(BASE).json()

    [pause] = [item["pause"] for item in items if item["key"] == "virustotal"]
    assert pause["daily"] is True
    assert datetime.fromisoformat(pause["until"]) == virustotal.next_reset(utcnow())
    assert all(item["pause"] is None for item in items if item["key"] != "virustotal")


def test_testing_virustotal_within_a_minute_of_too_many_requests_waits_and_sends_nothing(
    client: TestClient,
    csrf_token: str,
    virustotal_key: None,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session.add(
        IntelLookup(
            provider="virustotal",
            kind="ip",
            requested_at=utcnow() - timedelta(seconds=5),
            outcome=store.THROTTLED,
        )
    )
    session.commit()
    asked = answer_by_virustotal(monkeypatch, virustotal.Unknown())

    response = client.post(f"{VT_URL}/test", headers=headers(csrf_token))

    assert response.status_code == 429
    assert response.json()["detail"].startswith(
        "The limits on this connection hold the test. Try again in "
    )
    assert asked == []
