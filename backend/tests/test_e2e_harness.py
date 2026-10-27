"""The end-to-end tests' harness: the baseline, cleaning the database and making records."""

import base64
import socket
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

import coverage
import httpx2
import pytest
from coverage.data import CoverageData
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import config as config_module
from app.collectors import health
from app.collectors.health import WORKER, WorkerState
from app.config import Settings
from app.db import get_session
from app.integrations import netguard, registry, service
from app.integrations.service import Submission
from app.models import CollectorHealth, Event, SystemInfo, User, WorkerBeat, utcnow
from app.security import passwords, setup_code
from e2e import factories
from e2e.api import STAND_INS
from e2e.baseline import (
    BASELINE_ACCOUNT,
    BASELINE_SYSTEM_INFO,
    BASELINE_TIME,
    FRESH_INSTALL_SETUP_CODE,
)
from e2e.coverage_report import current_measurement
from e2e.main import create_e2e_app
from tests.helpers import ORIGIN


@pytest.fixture
def harness(settings: Settings, session: Session) -> FastAPI:
    def request_session() -> Iterator[Session]:
        try:
            yield session
        finally:
            session.rollback()

    app = create_e2e_app(settings)
    app.dependency_overrides[get_session] = request_session
    return app


@pytest.fixture
def e2e(harness: FastAPI) -> Iterator[TestClient]:
    with TestClient(harness, base_url=ORIGIN, headers={"Origin": ORIGIN}) as client:
        yield client


def system_info(session: Session) -> dict[str, str]:
    return {row.key: row.value for row in session.scalars(select(SystemInfo))}


def usernames(session: Session) -> list[str]:
    return [user.username for user in session.scalars(select(User))]


@pytest.mark.parametrize("environment", ["production", "development"])
def test_the_harness_refuses_to_run_outside_a_test_server(
    settings: Settings, environment: str
) -> None:
    elsewhere = settings.model_copy(update={"environment": environment})
    with pytest.raises(RuntimeError, match="ARESGATE_ENVIRONMENT=test"):
        create_e2e_app(elsewhere)


def test_the_harness_lets_integrations_run_on_the_same_machine(harness: FastAPI) -> None:
    assert harness.state.address_policy is netguard.HOME_NETWORK_AND_LOOPBACK


def test_the_harness_takes_its_settings_from_the_environment(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("e2e.main.get_settings", lambda: settings)

    with TestClient(create_e2e_app(), base_url=ORIGIN) as client:
        assert client.get("/api/__test__/baseline").status_code == 200


def test_the_production_app_has_no_harness(client: TestClient) -> None:
    for path in ("baseline", "fixtures", "coverage"):
        assert client.get(f"/api/__test__/{path}").status_code == 404
    assert client.post("/api/__test__/database/clean").status_code == 404


def test_the_baseline_describes_what_it_loads(e2e: TestClient, session: Session) -> None:
    described = e2e.get("/api/__test__/baseline").json()
    e2e.post("/api/__test__/database/clean")

    assert described == {
        "system_info": BASELINE_SYSTEM_INFO,
        "account": {
            "username": BASELINE_ACCOUNT.username,
            "password": BASELINE_ACCOUNT.password,
        },
        "fresh_install_setup_code": FRESH_INSTALL_SETUP_CODE,
    }
    assert system_info(session) == BASELINE_SYSTEM_INFO
    assert {row.updated_at for row in session.scalars(select(SystemInfo))} == {BASELINE_TIME}


def test_the_baseline_account_can_sign_in(e2e: TestClient, session: Session) -> None:
    e2e.post("/api/__test__/database/clean")

    response = e2e.post(
        "/api/auth/login",
        json={"username": BASELINE_ACCOUNT.username, "password": BASELINE_ACCOUNT.password},
    )

    assert response.status_code == 200
    assert usernames(session) == [BASELINE_ACCOUNT.username]


def test_the_account_is_hashed_once_however_many_times_the_baseline_loads(
    e2e: TestClient, session: Session
) -> None:
    e2e.post("/api/__test__/database/clean")
    first = session.scalars(select(User)).one().password_hash
    e2e.post("/api/__test__/database/clean")

    assert session.scalars(select(User)).one().password_hash == first


def test_the_fixtures_are_listed_with_what_they_hold(e2e: TestClient) -> None:
    listed = e2e.get("/api/__test__/fixtures").json()

    assert [fixture["name"] for fixture in listed] == ["baseline", "fresh-install"]
    assert all(fixture["description"] for fixture in listed)


def test_the_row_counts_say_what_each_table_holds(e2e: TestClient, session: Session) -> None:
    e2e.post("/api/__test__/database/clean")
    expected = {
        "ai_providers": 0,
        "ai_settings": 0,
        "audit_events": 0,
        "collector_health": 0,
        "credentials": 0,
        "device_addresses": 0,
        "devices": 0,
        "event_retention": 0,
        "events": 0,
        "incident_signals": 0,
        "incidents": 0,
        "integration_api_calls": 0,
        "integration_connections": 0,
        "login_throttles": 0,
        "metric_retention": 0,
        "metric_samples": 0,
        "metric_series": 0,
        "passkey_challenges": 0,
        "passkeys": 0,
        "recovery_codes": 0,
        "saved_searches": 0,
        "system_info": len(BASELINE_SYSTEM_INFO),
        "totp_credentials": 0,
        "user_sessions": 0,
        "users": 1,
        "verdict_rules": 0,
        "worker_beats": 0,
    }
    assert e2e.get("/api/__test__/database/counts").json() == expected

    factories.system_info(session)
    session.commit()

    counts = e2e.get("/api/__test__/database/counts").json()
    assert counts == {**expected, "system_info": len(BASELINE_SYSTEM_INFO) + 1}


def test_cleaning_replaces_everything_with_the_baseline(e2e: TestClient, session: Session) -> None:
    factories.system_info(session, key="left-behind")
    session.commit()

    response = e2e.post("/api/__test__/database/clean")

    assert response.status_code == 200
    assert response.json() == {
        "fixture": "baseline",
        "tables_emptied": [
            "user_sessions",
            "totp_credentials",
            "recovery_codes",
            "passkeys",
            "passkey_challenges",
            "metric_samples",
            "incident_signals",
            "device_addresses",
            "ai_settings",
            "worker_beats",
            "verdict_rules",
            "users",
            "system_info",
            "saved_searches",
            "metric_series",
            "metric_retention",
            "login_throttles",
            "integration_connections",
            "integration_api_calls",
            "incidents",
            "events",
            "event_retention",
            "devices",
            "credentials",
            "collector_health",
            "audit_events",
            "ai_providers",
        ],
    }
    assert system_info(session) == BASELINE_SYSTEM_INFO


def test_the_fresh_install_has_no_account_and_waits_for_its_setup_code(
    e2e: TestClient, session: Session
) -> None:
    e2e.post("/api/__test__/database/clean")

    response = e2e.post("/api/__test__/fixtures/fresh-install")

    assert response.json()["fixture"] == "fresh-install"
    assert usernames(session) == []
    assert set(system_info(session)) == {setup_code.KEY}
    assert e2e.get("/api/setup/status").json() == {"setup_required": True}


def test_the_fresh_install_can_be_set_up_with_its_known_code(
    e2e: TestClient, session: Session
) -> None:
    e2e.post("/api/__test__/fixtures/fresh-install")

    response = e2e.post(
        "/api/setup",
        json={
            "code": FRESH_INSTALL_SETUP_CODE,
            "username": "admin1",
            "password": "an e2e passphrase for owners",
        },
    )

    assert response.status_code == 201
    assert usernames(session) == ["admin1"]


def test_a_fixture_that_does_not_exist_is_refused(e2e: TestClient) -> None:
    assert e2e.post("/api/__test__/fixtures/nonsense").status_code == 422


def test_a_factory_fills_in_what_it_is_not_given(e2e: TestClient, session: Session) -> None:
    first = e2e.post("/api/__test__/factories/system-info", json={})
    second = e2e.post("/api/__test__/factories/system-info", json={})

    assert first.status_code == second.status_code == 201
    assert first.json()["value"] == factories.DEFAULT_VALUE
    assert first.json()["key"] != second.json()["key"]
    assert set(system_info(session)) == {first.json()["key"], second.json()["key"]}


def test_a_factory_keeps_what_it_is_given(e2e: TestClient, session: Session) -> None:
    response = e2e.post(
        "/api/__test__/factories/system-info", json={"key": "chosen", "value": "kept"}
    )

    assert response.json()["key"] == "chosen"
    assert response.json()["value"] == "kept"
    assert system_info(session) == {"chosen": "kept"}


def test_coverage_is_the_measurement_the_api_runs_under() -> None:
    assert current_measurement() is coverage.Coverage.current()


def test_coverage_needs_the_api_to_run_under_it(e2e: TestClient, harness: FastAPI) -> None:
    harness.dependency_overrides[current_measurement] = lambda: None

    response = e2e.get("/api/__test__/coverage")

    assert response.status_code == 404
    assert "coverage" in response.json()["detail"]


def test_coverage_comes_back_as_an_html_report_and_lcov(
    e2e: TestClient, harness: FastAPI, tmp_path: Path
) -> None:
    # Coverage data for part of one module, as if the API had run it.
    data_file = tmp_path / ".coverage"
    data = CoverageData(basename=str(data_file))
    data.add_lines({str(Path(config_module.__file__).resolve()): [1, 3, 4, 8, 9]})
    data.write()
    measurement = coverage.Coverage(data_file=str(data_file), config_file=False)
    measurement.load()
    harness.dependency_overrides[current_measurement] = lambda: measurement

    response = e2e.get("/api/__test__/coverage")

    assert response.status_code == 200
    report = response.json()
    files = {entry["path"]: base64.b64decode(entry["content"]) for entry in report["files"]}
    assert "html/index.html" in files
    assert b"config.py" in files["lcov.info"]
    assert 0 < report["percent_covered"] < 100


def test_an_account_can_be_made_to_order(e2e: TestClient, session: Session) -> None:
    chosen = e2e.post(
        "/api/__test__/factories/account", json={"username": "Chosen", "password": "kept as given"}
    )
    invented = e2e.post("/api/__test__/factories/account", json={})

    assert chosen.status_code == invented.status_code == 201
    assert chosen.json() == {"username": "chosen", "password": "kept as given"}
    assert invented.json()["username"].startswith("factory-")
    assert invented.json()["password"] == factories.DEFAULT_PASSWORD
    assert sorted(usernames(session)) == sorted(["chosen", invented.json()["username"]])
    stored = session.scalars(select(User).where(User.username == "chosen")).one()
    assert passwords.verify_password("kept as given", stored.password_hash)


@pytest.fixture
def stand_ins() -> Iterator[None]:
    yield
    STAND_INS.stop_all()


def reachable(url: str) -> bool:
    try:
        with socket.create_connection((urlsplit(url).hostname or "", urlsplit(url).port or 0), 2):
            return True
    except OSError:
        return False


@pytest.mark.usefixtures("stand_ins")
def test_a_stand_in_can_be_started_for_a_test_to_connect_to(e2e: TestClient) -> None:
    plain = e2e.post("/api/__test__/stand-ins", json={"kind": "ntopng", "token": "a-token"})
    secure = e2e.post(
        "/api/__test__/stand-ins",
        json={
            "kind": "opnsense",
            "api_key": "a-key",
            "api_secret": "a-secret",
            "services": ["suricata"],
        },
    )

    assert plain.status_code == secure.status_code == 201
    assert plain.json()["kind"] == "ntopng"
    assert plain.json()["url"].startswith("http://127.0.0.1:")
    assert plain.json()["fingerprint"] is None
    assert secure.json()["url"].startswith("https://127.0.0.1:")
    assert secure.json()["fingerprint"].count(":") == 31
    assert reachable(plain.json()["url"])
    assert reachable(secure.json()["url"])


@pytest.mark.usefixtures("stand_ins")
def test_the_collectors_read_the_alerts_and_agents_of_the_wazuh_stand_in(
    e2e: TestClient, session: Session, settings: Settings
) -> None:
    started = e2e.post(
        "/api/__test__/stand-ins",
        json={"kind": "wazuh", "username": "u", "password": "p"},
    ).json()
    connection = Submission(
        url=started["url"],
        tls_mode="pinned",
        tls_ca_pem=None,
        tls_fingerprint=started["fingerprint"],
        options={"username": "u"},
        secrets={"password": "p"},
    )
    service.save(
        session,
        settings,
        netguard.HOME_NETWORK_AND_LOOPBACK,
        registry.INTEGRATIONS["wazuh"],
        {"manager": connection, "indexer": connection},
        utcnow(),
    )
    session.commit()

    for _ in range(2):
        assert e2e.post("/api/__test__/collectors/run").status_code == 204

    session.expire_all()
    records = {
        (item.collector, item.connection): item for item in session.scalars(select(CollectorHealth))
    }
    assert sorted(records) == [
        ("connection-check", "indexer"),
        ("connection-check", "manager"),
        ("wazuh-agents", "manager"),
        ("wazuh-alerts", "indexer"),
    ]
    assert {item.consecutive_failures for item in records.values()} == {0}
    # The second run found the alerts and the agent that stopped stored already.
    assert records["wazuh-alerts", "indexer"].last_items == 0
    assert records["wazuh-agents", "manager"].last_items == 0
    counts = e2e.get("/api/__test__/database/counts").json()
    # Four alerts of the last half hour and the one agent that stopped reporting.
    assert counts["events"] == 5
    # The four states of the agents, counted twice.
    assert (counts["metric_series"], counts["metric_samples"]) == (4, 8)


@pytest.mark.usefixtures("stand_ins")
def test_the_collectors_read_the_hosts_interface_and_alerts_of_the_ntopng_stand_in(
    e2e: TestClient, session: Session, settings: Settings
) -> None:
    started = e2e.post("/api/__test__/stand-ins", json={"kind": "ntopng", "token": "t"}).json()
    service.save(
        session,
        settings,
        netguard.HOME_NETWORK_AND_LOOPBACK,
        registry.INTEGRATIONS["ntopng"],
        {
            "api": Submission(
                url=started["url"],
                tls_mode="system",
                tls_ca_pem=None,
                tls_fingerprint=None,
                options={"auth": "token", "interface_id": 0},
                secrets={"token": "t"},
            )
        },
        utcnow(),
    )
    session.commit()

    for _ in range(2):
        assert e2e.post("/api/__test__/collectors/run").status_code == 204

    session.expire_all()
    records = {item.collector: item for item in session.scalars(select(CollectorHealth))}
    assert sorted(records) == [
        "connection-check",
        "ntopng-alerts",
        "ntopng-hosts",
        "ntopng-interface",
    ]
    assert {item.consecutive_failures for item in records.values()} == {0}
    # The second run read the same alerts and found them stored already; it listed the three
    # local hosts again and measured the interface again.
    assert {key: item.last_items for key, item in records.items() if key != "connection-check"} == {
        "ntopng-alerts": 0,
        "ntopng-hosts": 3,
        "ntopng-interface": 12,
    }
    counts = e2e.get("/api/__test__/database/counts").json()
    # Two flow alerts and two host alerts of the last half hour, and none of the older one.
    assert counts["events"] == 4
    # Five readings of each of three hosts and twelve of the interface, taken twice.
    assert (counts["metric_series"], counts["metric_samples"]) == (27, 54)
    # The two hosts in the broadcast domain.
    assert counts["devices"] == 2


@pytest.mark.usefixtures("stand_ins")
def test_a_stand_in_of_a_kind_that_does_not_exist_is_refused(e2e: TestClient) -> None:
    response = e2e.post("/api/__test__/stand-ins", json={"kind": "nothing"})

    assert response.status_code == 422


@pytest.mark.usefixtures("stand_ins")
def test_the_stand_ins_can_be_stopped(e2e: TestClient) -> None:
    started = e2e.post("/api/__test__/stand-ins", json={"kind": "crowdsec", "api_key": "k"}).json()

    response = e2e.delete("/api/__test__/stand-ins")

    assert response.status_code == 204
    assert not reachable(started["url"])


@pytest.mark.usefixtures("stand_ins")
@pytest.mark.parametrize("reset", ["/database/clean", "/fixtures/fresh-install"])
def test_putting_the_database_back_stops_the_stand_ins_too(e2e: TestClient, reset: str) -> None:
    started = e2e.post("/api/__test__/stand-ins", json={"kind": "crowdsec", "api_key": "k"}).json()
    assert reachable(started["url"])

    e2e.post(f"/api/__test__{reset}")

    assert not reachable(started["url"])


@pytest.mark.usefixtures("stand_ins")
@pytest.mark.parametrize("reset", ["clean", "stop"])
def test_an_ai_stand_in_takes_the_place_of_the_provider_until_it_is_stopped(
    e2e: TestClient, harness: FastAPI, reset: str
) -> None:
    started = e2e.post(
        "/api/__test__/stand-ins",
        json={
            "kind": "anthropic",
            "api_key": "k",
            "models": ["claude-haiku-5-5"],
            "provider": "anthropic",
        },
    )

    assert started.status_code == 201
    assert harness.state.ai_origins == {"anthropic": started.json()["url"]}
    assert reachable(started.json()["url"])

    if reset == "clean":
        e2e.post("/api/__test__/database/clean")
    else:
        e2e.delete("/api/__test__/stand-ins")

    assert harness.state.ai_origins == {}
    assert not reachable(started.json()["url"])


@pytest.mark.usefixtures("stand_ins")
def test_an_ai_stand_in_that_is_not_for_a_provider_changes_nothing_about_where_they_are(
    e2e: TestClient, harness: FastAPI
) -> None:
    started = e2e.post(
        "/api/__test__/stand-ins", json={"kind": "ollama", "models": ["llama3.2:3b"]}
    )

    assert started.status_code == 201
    assert harness.state.ai_origins == {}


@pytest.mark.usefixtures("stand_ins")
def test_an_ollama_stand_in_answers_402_for_the_models_that_need_a_paid_plan(
    e2e: TestClient,
) -> None:
    started = e2e.post(
        "/api/__test__/stand-ins",
        json={"kind": "ollama", "models": ["free:1b", "big:675b"], "paid": ["big:675b"]},
    ).json()

    def ask(model: str) -> int:
        return httpx2.post(f"{started['url']}/api/chat", json={"model": model}).status_code

    assert ask("big:675b") == 402
    assert ask("free:1b") == 200


def test_the_production_app_cannot_start_a_stand_in(client: TestClient) -> None:
    started = client.post("/api/__test__/stand-ins", json={"kind": "ntopng"})
    stopped = client.delete("/api/__test__/stand-ins")

    assert started.status_code == 404
    assert stopped.status_code == 404


# ---- Collectors ------------------------------------------------------------------------------


def worker_status(e2e: TestClient, state: str) -> int:
    return e2e.put("/api/__test__/collectors/worker", json={"state": state}).status_code


def test_the_worker_can_be_made_to_look_running_stopped_or_absent(
    e2e: TestClient, session: Session
) -> None:
    def beat() -> WorkerBeat | None:
        session.expire_all()
        return session.get(WorkerBeat, WORKER)

    assert worker_status(e2e, "running") == 204
    running = beat()
    assert running is not None
    assert health.worker_state(running, utcnow(), enabled=True) == WorkerState.RUNNING

    assert worker_status(e2e, "stopped") == 204
    stopped = beat()
    assert stopped is not None
    assert health.worker_state(stopped, utcnow(), enabled=True) == WorkerState.STOPPED

    assert worker_status(e2e, "absent") == 204
    assert beat() is None


def test_a_worker_status_has_to_be_one_the_harness_knows(e2e: TestClient) -> None:
    assert worker_status(e2e, "sideways") == 422


@pytest.mark.usefixtures("stand_ins")
def test_the_collectors_run_when_asked_against_the_stand_ins(
    e2e: TestClient, session: Session, settings: Settings
) -> None:
    started = e2e.post("/api/__test__/stand-ins", json={"kind": "crowdsec", "api_key": "k"}).json()
    service.save(
        session,
        settings,
        netguard.HOME_NETWORK_AND_LOOPBACK,
        registry.INTEGRATIONS["crowdsec"],
        {
            "lapi": Submission(
                url=started["url"],
                tls_mode="system",
                tls_ca_pem=None,
                tls_fingerprint=None,
                options={},
                secrets={"api_key": "k"},
            )
        },
        utcnow(),
    )
    session.commit()

    response = e2e.post("/api/__test__/collectors/run")

    assert response.status_code == 204
    session.expire_all()
    records = session.scalars(select(CollectorHealth).order_by(CollectorHealth.collector)).all()
    assert [(item.collector, item.integration, item.consecutive_failures) for item in records] == [
        ("connection-check", "crowdsec", 0),
        ("crowdsec-decisions", "crowdsec", 0),
    ]
    assert all(item.last_success_at is not None for item in records)
    # The bans made here, and not the one from the community blocklist.
    assert session.scalar(select(func.count()).select_from(Event)) == 4


@pytest.mark.usefixtures("stand_ins")
def test_the_collectors_read_the_log_alerts_metrics_and_devices_of_the_opnsense_stand_in(
    e2e: TestClient, session: Session, settings: Settings
) -> None:
    started = e2e.post(
        "/api/__test__/stand-ins",
        json={
            "kind": "opnsense",
            "api_key": "k",
            "api_secret": "s",
            "services": ["suricata", "dnsmasq", "kea"],
        },
    ).json()
    service.save(
        session,
        settings,
        netguard.HOME_NETWORK_AND_LOOPBACK,
        registry.INTEGRATIONS["opnsense"],
        {
            "api": Submission(
                url=started["url"],
                tls_mode="pinned",
                tls_ca_pem=None,
                tls_fingerprint=started["fingerprint"],
                options={},
                secrets={"api_key": "k", "api_secret": "s"},
            )
        },
        utcnow(),
    )
    session.commit()

    for _ in range(2):
        assert e2e.post("/api/__test__/collectors/run").status_code == 204

    session.expire_all()
    records = {item.collector: item for item in session.scalars(select(CollectorHealth))}
    assert sorted(records) == [
        "connection-check",
        "opnsense-arp-table",
        "opnsense-cpu-usage",
        "opnsense-dnsmasq-leases",
        "opnsense-firewall-log",
        "opnsense-gateway-status",
        "opnsense-interface-traffic",
        "opnsense-kea-leases",
        "opnsense-suricata-alerts",
        "opnsense-system-health",
    ]
    assert {item.consecutive_failures for item in records.values()} == {0}
    # The second run read the same lines and alerts and found them stored already.
    assert records["opnsense-firewall-log"].last_items == 0
    assert records["opnsense-suricata-alerts"].last_items == 0
    # Each run measures again, so what it read is new, and lists the devices again.
    assert {
        key: item.last_items for key, item in records.items() if key.startswith("opnsense-")
    } == {
        "opnsense-arp-table": 3,
        "opnsense-cpu-usage": 1,
        "opnsense-dnsmasq-leases": 2,
        "opnsense-firewall-log": 0,
        "opnsense-kea-leases": 1,
        "opnsense-gateway-status": 4,
        "opnsense-interface-traffic": 14,
        "opnsense-suricata-alerts": 0,
        "opnsense-system-health": 9,
    }
    counts = e2e.get("/api/__test__/database/counts").json()
    # Three lines of the firewall's log and two alerts.
    assert counts["events"] == 5
    # 28 things measured, twice.
    assert (counts["metric_series"], counts["metric_samples"]) == (28, 56)
    # Three devices in the ARP table, two with leases from Dnsmasq (one of them the laptop that is
    # in the table too) and one from Kea, each with one address.
    assert (counts["devices"], counts["device_addresses"]) == (5, 5)


def test_what_the_dashboard_shows_can_be_made_to_order(e2e: TestClient) -> None:
    e2e.post("/api/__test__/database/clean")
    made = e2e.post(
        "/api/__test__/factories/activity",
        json={
            "alerts": {"critical": 1, "medium": 2},
            "blocked": {"203.0.113.9": 3, "198.51.100.7": 1},
            "traffic": {"igc0": 80},
            "devices": 2,
            "collectors": ["ok", "problem"],
        },
    )

    assert made.status_code == 201
    # Two readings of two counters, every five minutes for three hours.
    assert made.json() == {"alerts": 3, "blocked": 4, "samples": 74, "devices": 2, "collectors": 2}
    signed_in = e2e.post(
        "/api/auth/login",
        json={"username": BASELINE_ACCOUNT.username, "password": BASELINE_ACCOUNT.password},
    )
    assert signed_in.status_code == 200
    shown = e2e.get("/api/dashboard").json()
    assert shown["alerts"]["total"] == 3
    assert shown["alerts"]["highest"] == "critical"
    assert [item["severity"] for item in shown["recent_alerts"]] == ["critical", "medium", "medium"]
    assert shown["blocked"]["top_sources"] == [
        {"address": "203.0.113.9", "count": 3},
        {"address": "198.51.100.7", "count": 1},
    ]
    assert shown["devices"] == {"total": 2, "new": 2}
    [interface] = shown["traffic"]
    speeds = [speed for speed in interface["received"] if speed is not None]
    assert interface["interface"] == "igc0"
    assert speeds
    assert all(speed == pytest.approx(80_000_000) for speed in speeds)
    listed = e2e.get("/api/collectors").json()["collectors"]
    assert [item["state"] for item in listed] == ["ok", "problem"]
    assert all(item["integration"] == "opnsense" for item in listed)


@pytest.mark.parametrize("state", ["waiting", "ok", "problem", "late"])
def test_a_collector_can_be_made_to_be_in_any_state(e2e: TestClient, state: str) -> None:
    e2e.post("/api/__test__/database/clean")
    e2e.post("/api/__test__/factories/activity", json={"collectors": [state]})
    e2e.post(
        "/api/auth/login",
        json={"username": BASELINE_ACCOUNT.username, "password": BASELINE_ACCOUNT.password},
    )

    [listed] = e2e.get("/api/collectors").json()["collectors"]

    assert listed["state"] == state


def test_an_empty_request_stores_nothing(e2e: TestClient) -> None:
    made = e2e.post("/api/__test__/factories/activity", json={})

    assert made.json() == {"alerts": 0, "blocked": 0, "samples": 0, "devices": 0, "collectors": 0}


def sign_in(e2e: TestClient) -> None:
    signed_in = e2e.post(
        "/api/auth/login",
        json={"username": BASELINE_ACCOUNT.username, "password": BASELINE_ACCOUNT.password},
    )
    assert signed_in.status_code == 200


def test_incidents_can_be_made_to_order(e2e: TestClient) -> None:
    e2e.post("/api/__test__/database/clean")
    made = e2e.post(
        "/api/__test__/factories/incidents",
        json={
            "incidents": [
                {
                    "severity": "critical",
                    "programs": ["wazuh", "opnsense"],
                    "signals": 4,
                    "ban": True,
                    "minutes_ago": 5,
                    "device_name": "nas",
                },
                {"address": "8.8.4.4", "severity": "low", "minutes_ago": 90, "status": "resolved"},
                {"severity": "medium", "status": "investigating", "device": "192.168.1.30"},
            ]
        },
    )

    # Four alerts and a ban, one, and one.
    assert made.status_code == 201
    assert made.json() == {"signals": 7, "incidents": 3}
    sign_in(e2e)
    listed = e2e.get("/api/incidents", params={"limit": 10}).json()
    assert listed["total"] == 3
    assert listed["counts"] == {"open": 1, "investigating": 1, "resolved": 1, "dismissed": 0}
    by_subject = {item["subject"]: item for item in listed["items"]}
    assert set(by_subject) == {"93.184.216.34", "8.8.4.4", "1.1.1.1"}
    attack = by_subject["93.184.216.34"]
    assert (attack["severity"], attack["signal_count"], attack["banned"]) == ("critical", 5, True)
    assert [source["key"] for source in attack["sources"]] == ["crowdsec", "opnsense", "wazuh"]
    assert by_subject["8.8.4.4"]["status"] == "resolved"
    assert by_subject["1.1.1.1"]["status"] == "investigating"
    detail = e2e.get(f"/api/incidents/{attack['id']}").json()
    assert [device["hostname"] for device in detail["devices"]] == ["nas"]
    assert len(detail["signals"]) == 5


def test_incidents_can_be_made_with_what_was_done_about_them(e2e: TestClient) -> None:
    e2e.post("/api/__test__/database/clean")
    made = e2e.post(
        "/api/__test__/factories/incidents",
        json={
            "incidents": [
                {
                    "address": "8.8.4.4",
                    "ban": True,
                    "ban_left": "3h59m12s",
                    "blocks": 2,
                    "blocks_after_ban": 3,
                    "dropped": 1,
                    "minutes_ago": 30,
                },
                {"address": "1.1.1.1", "ban": True, "ban_left": "", "minutes_ago": 30},
                {"address": "9.9.9.9", "ban": True, "ban_left": "5m", "minutes_ago": 300},
            ]
        },
    )

    assert made.status_code == 201
    sign_in(e2e)
    by_subject = {
        item["subject"]: item["response"] for item in e2e.get("/api/incidents").json()["items"]
    }
    banned = by_subject["8.8.4.4"]
    assert banned["state"] == "banned"
    assert (banned["blocked"], banned["blocked_since_ban"], banned["dropped"]) == (5, 3, 1)
    assert banned["bans"][0]["scenario"] == "crowdsecurity/ssh-bf"
    assert banned["bans"][0]["origin"] == "CrowdSec's own detection"
    # Without the time left, the ban is taken to hold; a short one has run out long ago.
    assert by_subject["1.1.1.1"]["state"] == "banned"
    assert by_subject["1.1.1.1"]["bans"][0]["ends_at"] is None
    assert by_subject["9.9.9.9"]["state"] == "ban_ended"


def test_a_bot_sweeping_from_a_block_in_waves_is_one_incident(e2e: TestClient) -> None:
    e2e.post("/api/__test__/database/clean")
    made = e2e.post(
        "/api/__test__/factories/incidents",
        json={
            "incidents": [
                {
                    "address": "8.8.4.10",
                    "scan": True,
                    "signals": 6,
                    "neighbours": 2,
                    "waves": 2,
                    "ports": [22, 80, 443],
                },
                # More bursts than signals can't be made: there are as many as there are signals.
                {"address": "1.1.1.1", "signals": 2, "waves": 5},
            ]
        },
    )

    assert made.status_code == 201
    assert made.json() == {"signals": 8, "incidents": 2}
    sign_in(e2e)
    listed = e2e.get("/api/incidents", params={"limit": 10}).json()["items"]
    sweep, pair = sorted(listed, key=lambda item: item["subject"], reverse=True)
    assert (sweep["subject"], sweep["signal_count"], sweep["neighbours"]) == ("8.8.4.10", 6, 2)
    assert (sweep["activities"], sweep["waves"], sweep["port_count"]) == (["scan"], 2, 3)
    assert (pair["subject"], pair["signal_count"], pair["waves"]) == ("1.1.1.1", 2, 2)
    detail = e2e.get(f"/api/incidents/{sweep['id']}").json()
    assert detail["ports"] == [22, 80, 443]
    assert detail["grouping"][0].startswith("Signals from 3 addresses of 8.8.4.0/24")


def test_events_can_be_made_to_order_for_the_logs(e2e: TestClient) -> None:
    e2e.post("/api/__test__/database/clean")
    made = e2e.post(
        "/api/__test__/factories/events",
        json={
            "events": [
                {
                    "source": "wazuh",
                    "kind": "alert",
                    "severity": "high",
                    "summary": "sshd: authentication failed",
                    "signature": "Brute force on ssh",
                    "src_address": "93.184.216.34",
                    "src_port": 41000,
                    "dst_address": "192.168.1.20",
                    "dst_port": 22,
                    "protocol": "tcp",
                    "seconds_ago": 120,
                    "raw": {"rule": {"id": "5710"}},
                },
                {"summary": "Blocked tcp", "repeat": 3, "every_seconds": 10, "seconds_ago": 5},
            ]
        },
    )

    assert made.status_code == 201
    assert made.json() == {"events": 4}
    sign_in(e2e)
    page = e2e.get("/api/logs").json()
    assert [item["summary"] for item in page["items"]] == [
        "Blocked tcp",
        "Blocked tcp",
        "Blocked tcp",
        "sshd: authentication failed",
    ]
    attack = page["items"][-1]
    assert (attack["source"], attack["connection"], attack["severity"]) == (
        "wazuh",
        "indexer",
        "high",
    )
    assert e2e.get(f"/api/logs/{attack['cursor']}").json()["raw"] == {"rule": {"id": "5710"}}
    # The three of a run are as far apart as asked, the last of them as long ago as asked.
    times = [datetime.fromisoformat(item["at"]) for item in page["items"][:3]]
    assert (times[0] - times[1]).total_seconds() == 10
    assert (times[1] - times[2]).total_seconds() == 10
    assert page["summary"]["matched"] == 4


def test_verdicts_can_be_given_and_judge_the_incidents_there_are(e2e: TestClient) -> None:
    e2e.post("/api/__test__/database/clean")
    e2e.post(
        "/api/__test__/factories/incidents",
        json={"incidents": [{"address": "8.8.8.8"}, {"address": "1.1.1.1"}]},
    )

    made = e2e.post(
        "/api/__test__/factories/verdicts",
        json={
            "verdicts": [
                {"verdict": "not_suspicious", "address": "8.8.8.8", "note": "my scanner"},
                {"verdict": "threat", "source": "wazuh", "signature": "Brute force on ssh"},
            ]
        },
    )

    assert made.status_code == 201
    assert made.json() == {"verdicts": 2}
    sign_in(e2e)
    listed = e2e.get("/api/incidents").json()["items"]
    assert {item["subject"]: item["verdict"] for item in listed} == {
        "8.8.8.8": "threat",
        "1.1.1.1": "threat",
    }
    rules = e2e.get("/api/verdicts").json()["items"]
    assert [(rule["verdict"], rule["note"], rule["hits"]) for rule in rules] == [
        ("threat", None, 2),
        ("not_suspicious", "my scanner", 0),
    ]


def test_an_empty_list_of_incidents_stores_nothing(e2e: TestClient) -> None:
    made = e2e.post("/api/__test__/factories/incidents", json={"incidents": []})

    assert made.json() == {"signals": 0, "incidents": 0}


@pytest.mark.parametrize(
    "incident",
    [
        {"signals": 0},
        {"signals": 51},
        {"severity": "scary"},
        {"status": "ignored"},
        {"neighbours": 21},
        {"waves": 0},
        {"waves": 11},
        {"ports": [0]},
        {"ports": [65_536]},
        {"ports": list(range(1, 52))},
    ],
)
def test_an_incident_that_cannot_be_made_is_refused(
    e2e: TestClient, incident: dict[str, object]
) -> None:
    made = e2e.post("/api/__test__/factories/incidents", json={"incidents": [incident]})

    assert made.status_code == 422
