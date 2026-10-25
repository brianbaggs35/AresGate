"""The end-to-end tests' harness: the baseline, cleaning the database and making records."""

import base64
import socket
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlsplit

import coverage
import pytest
from coverage.data import CoverageData
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config as config_module
from app.collectors import health
from app.collectors.health import WORKER, WorkerState
from app.config import Settings
from app.db import get_session
from app.integrations import netguard, registry, service
from app.integrations.service import Submission
from app.models import CollectorHealth, SystemInfo, User, WorkerBeat, utcnow
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
        "audit_events": 0,
        "collector_health": 0,
        "credentials": 0,
        "event_retention": 0,
        "events": 0,
        "integration_api_calls": 0,
        "integration_connections": 0,
        "login_throttles": 0,
        "metric_retention": 0,
        "metric_samples": 0,
        "metric_series": 0,
        "passkey_challenges": 0,
        "passkeys": 0,
        "recovery_codes": 0,
        "system_info": len(BASELINE_SYSTEM_INFO),
        "totp_credentials": 0,
        "user_sessions": 0,
        "users": 1,
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
            "worker_beats",
            "users",
            "system_info",
            "metric_series",
            "metric_retention",
            "login_throttles",
            "integration_connections",
            "integration_api_calls",
            "events",
            "event_retention",
            "credentials",
            "collector_health",
            "audit_events",
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
    [record] = session.scalars(select(CollectorHealth)).all()
    assert (record.collector, record.integration, record.consecutive_failures) == (
        "connection-check",
        "crowdsec",
        0,
    )
    assert record.last_success_at is not None


@pytest.mark.usefixtures("stand_ins")
def test_the_collectors_read_the_log_alerts_and_metrics_of_the_opnsense_stand_in(
    e2e: TestClient, session: Session, settings: Settings
) -> None:
    started = e2e.post(
        "/api/__test__/stand-ins",
        json={"kind": "opnsense", "api_key": "k", "api_secret": "s", "services": ["suricata"]},
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
        "opnsense-cpu-usage",
        "opnsense-firewall-log",
        "opnsense-gateway-status",
        "opnsense-interface-traffic",
        "opnsense-suricata-alerts",
        "opnsense-system-health",
    ]
    assert {item.consecutive_failures for item in records.values()} == {0}
    # The second run read the same lines and alerts and found them stored already.
    assert records["opnsense-firewall-log"].last_items == 0
    assert records["opnsense-suricata-alerts"].last_items == 0
    # Each run measures again, so what it read is new.
    assert {
        key: item.last_items for key, item in records.items() if key.startswith("opnsense-")
    } == {
        "opnsense-cpu-usage": 1,
        "opnsense-firewall-log": 0,
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
