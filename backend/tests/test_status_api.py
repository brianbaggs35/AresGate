from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import __version__, status
from app.config import Settings, get_settings
from app.integrations import netguard
from app.models import IntegrationConnection, User, utcnow

BASE = "/api/status"


def connection(
    session: Session, integration: str, key: str, *, last_error: str | None = None, tested: bool
) -> IntegrationConnection:
    row = IntegrationConnection(
        integration=integration,
        connection=key,
        base_url="https://192.168.1.2:5000",
        tls_mode="system",
        options={},
        disabled_modules=[],
    )
    if tested:
        row.last_attempt_at = utcnow()
        row.last_error = last_error
        row.last_success_at = None if last_error else utcnow()
    session.add(row)
    session.commit()
    return row


def get(client: TestClient) -> dict[str, Any]:
    response = client.get(BASE)
    assert response.status_code == 200
    return response.json()


def test_it_is_only_for_someone_signed_in(client: TestClient, account: User) -> None:
    response = client.get(BASE)

    assert response.status_code == 401
    assert response.json() == {"detail": "You're not signed in."}


def test_it_says_what_is_running(client: TestClient, csrf_token: str) -> None:
    body = get(client)

    assert set(body) == {"aresgate", "stack", "container", "parts", "diagnostics"}
    aresgate = body["aresgate"]
    assert aresgate["version"] == __version__
    assert aresgate["environment"] == "test"
    assert aresgate["commit"] is None
    assert aresgate["built_at"] is None
    assert 0 <= aresgate["uptime_seconds"] < 60
    started = datetime.fromisoformat(aresgate["started_at"])
    assert timedelta(0) <= utcnow() - started < timedelta(minutes=1)


def test_a_release_says_which_commit_and_when_it_was_built(
    app: FastAPI, client: TestClient, csrf_token: str, settings: Settings
) -> None:
    built = datetime(2026, 10, 22, 8, 30, tzinfo=UTC)
    app.dependency_overrides[get_settings] = lambda: settings.model_copy(
        update={"release": "1.2.3", "commit": "0123456789abcdef0123", "built_at": built}
    )

    aresgate = get(client)["aresgate"]

    assert aresgate["version"] == "1.2.3"
    assert aresgate["commit"] == "0123456789abcdef0123"
    assert datetime.fromisoformat(aresgate["built_at"]) == built


def test_it_says_which_programs_it_runs_on(client: TestClient, csrf_token: str) -> None:
    stack = get(client)["stack"]

    assert stack["python"].startswith("3.")
    assert stack["database"]["status"] == "ok"
    assert stack["database"]["migration_head"] == status.migration_head()
    assert stack["database"]["max_connections"] > 0
    # No nginx or certificate is serving where the tests run.
    assert stack["nginx"] is None
    assert stack["certificate"] is None


def test_it_reads_nginxs_version_from_the_packages(
    client: TestClient, csrf_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:

    def packaged_version(name: str) -> str | None:
        return "1.29.1" if name == "nginx-mainline" else None

    monkeypatch.setattr(status, "packaged_version", packaged_version)

    assert get(client)["stack"]["nginx"] == "1.29.1"


def test_it_describes_the_certificate_nginx_serves(
    client: TestClient, csrf_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = utcnow()
    seen: list[tuple[str, int, str]] = []

    def look_up(host: str, port: int, name: str) -> netguard.CertificateInfo:
        seen.append((host, port, name))
        return netguard.CertificateInfo(
            fingerprint="AA",
            subject="CN=aresgate.test",
            issuer="CN=R11,O=Let's Encrypt",
            not_before=now - timedelta(days=60),
            not_after=now + timedelta(days=29, hours=12),
            names=["aresgate.test"],
        )

    monkeypatch.setattr(netguard, "look_up_served_certificate", look_up)

    certificate = get(client)["stack"]["certificate"]

    assert certificate["subject"] == "CN=aresgate.test"
    assert certificate["issuer"] == "CN=R11,O=Let's Encrypt"
    assert certificate["names"] == ["aresgate.test"]
    assert certificate["days_left"] == 29
    assert certificate["self_signed"] is False
    assert seen == [("127.0.0.1", status.NGINX_TLS_PORT, "aresgate.test")]


def test_it_measures_the_container(client: TestClient, csrf_token: str) -> None:
    container = get(client)["container"]

    assert container["cpus"] > 0
    assert len(container["load"]) == 3
    assert container["disk"]["used_bytes"] <= container["disk"]["total_bytes"]
    assert container["memory"]["used_bytes"] > 0
    clock = datetime.fromisoformat(container["server_time"])
    assert abs(utcnow() - clock) < timedelta(minutes=1)


def test_it_lists_every_integration_even_with_none_connected(
    client: TestClient, csrf_token: str
) -> None:
    parts = get(client)["parts"]

    assert [part["key"] for part in parts] == ["opnsense", "ntopng", "wazuh", "crowdsec"]
    for part in parts:
        assert part["group"] == "integration"
        assert part["state"] == "off"
        assert part["detail"] == "Not connected."
        assert part["last_success_at"] is None


def test_it_says_how_each_integration_is_doing(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    connection(session, "ntopng", "api", tested=True)
    connection(session, "crowdsec", "lapi", tested=True, last_error="CrowdSec refused the key.")
    connection(session, "wazuh", "manager", tested=False)

    parts = {part["key"]: part for part in get(client)["parts"]}

    assert parts["ntopng"]["state"] == "ok"
    assert parts["ntopng"]["detail"] is None
    assert parts["ntopng"]["last_success_at"] is not None
    assert parts["crowdsec"]["state"] == "problem"
    assert parts["crowdsec"]["detail"] == "CrowdSec refused the key."
    assert parts["wazuh"]["state"] == "unknown"
    assert parts["wazuh"]["detail"] == "Saved, but not tested yet."
    assert parts["opnsense"]["state"] == "off"


def test_it_holds_no_secret_and_no_address_in_the_text_for_a_bug_report(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    connection(
        session,
        "crowdsec",
        "lapi",
        tested=True,
        last_error="Couldn't reach https://192.168.1.2:8080 (opnsense.home.arpa).",
    )

    body = get(client)
    text = str(body["diagnostics"])

    assert text.startswith("AresGate diagnostics\n")
    assert f"Version: {__version__}" in text
    assert "Environment: test" in text
    assert "- CrowdSec: problem (Couldn't reach [address] ([address]).)" in text
    assert "192.168.1.2" not in text
    assert "opnsense.home.arpa" not in text
    assert "aresgate.test" not in text
    # The page itself shows the same part in full to the person signed in.
    crowdsec = next(part for part in body["parts"] if part["key"] == "crowdsec")
    assert "192.168.1.2" in crowdsec["detail"]


def test_it_leaves_secrets_out_of_everything_it_says(
    client: TestClient, csrf_token: str, settings: Settings
) -> None:
    raw = client.get(BASE).text

    assert settings.secret_key is not None
    assert settings.secret_key.get_secret_value() not in raw
    assert "database_url" not in raw
    assert "postgresql" not in raw.replace('"PostgreSQL', "")


def test_the_diagnostics_name_the_commit_and_build_time_when_known(
    app: FastAPI, client: TestClient, csrf_token: str, settings: Settings
) -> None:
    app.dependency_overrides[get_settings] = lambda: settings.model_copy(
        update={
            "release": "1.2.3",
            "commit": "0123456789abcdef0123",
            "built_at": datetime(2026, 10, 22, 8, 30, tzinfo=UTC),
        }
    )

    text = str(get(client)["diagnostics"])

    assert "Version: 1.2.3 (commit 0123456789ab, built 2026-10-22 08:30 UTC)" in text
