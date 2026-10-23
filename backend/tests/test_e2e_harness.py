"""The end-to-end tests' harness: the baseline, cleaning the database and making records."""

import base64
from collections.abc import Iterator
from pathlib import Path

import coverage
import pytest
from coverage.data import CoverageData
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config as config_module
from app.config import Settings
from app.db import get_session
from app.integrations import netguard
from app.models import SystemInfo, User
from app.security import passwords, setup_code
from e2e import factories
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
        "credentials": 0,
        "integration_api_calls": 0,
        "integration_connections": 0,
        "login_throttles": 0,
        "passkey_challenges": 0,
        "passkeys": 0,
        "recovery_codes": 0,
        "system_info": len(BASELINE_SYSTEM_INFO),
        "totp_credentials": 0,
        "user_sessions": 0,
        "users": 1,
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
            "users",
            "system_info",
            "login_throttles",
            "integration_connections",
            "integration_api_calls",
            "credentials",
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
