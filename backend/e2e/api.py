"""Endpoints the Playwright tests call to set up each test, under /api/__test__.

They put the database back to a known state, make extra records and hand over the API's code
coverage. Only ``e2e.main`` mounts them.
"""

from datetime import datetime
from typing import Annotated

import coverage
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_session
from e2e import baseline, factories
from e2e.baseline import (
    BASELINE_ACCOUNT,
    BASELINE_SYSTEM_INFO,
    FIXTURES,
    FRESH_INSTALL_SETUP_CODE,
    FixtureName,
)
from e2e.coverage_report import CoverageReport, current_measurement, report
from e2e.stand_ins import Kind, StandIns

router = APIRouter(prefix="/__test__", tags=["test"])

# The stand-ins a test has started. Putting the database back to a known state stops them.
STAND_INS = StandIns()

Db = Annotated[Session, Depends(get_session)]
Measurement = Annotated[coverage.Coverage | None, Depends(current_measurement)]


class AccountLogin(BaseModel):
    username: str
    password: str


class Baseline(BaseModel):
    system_info: dict[str, str]
    # The account the baseline signs in with.
    account: AccountLogin
    # The setup code the fresh-install fixture waits with.
    fresh_install_setup_code: str


@router.get("/baseline")
def describe_baseline() -> Baseline:
    """What the baseline holds, without touching the database."""
    return Baseline(
        system_info=BASELINE_SYSTEM_INFO,
        account=AccountLogin(
            username=BASELINE_ACCOUNT.username, password=BASELINE_ACCOUNT.password
        ),
        fresh_install_setup_code=FRESH_INSTALL_SETUP_CODE,
    )


class FixtureInfo(BaseModel):
    name: FixtureName
    description: str


@router.get("/fixtures")
def list_fixtures() -> list[FixtureInfo]:
    return [FixtureInfo(name=name, description=item.description) for name, item in FIXTURES.items()]


class Loaded(BaseModel):
    fixture: FixtureName
    tables_emptied: list[str]


def _load(db: Session, name: FixtureName) -> Loaded:
    STAND_INS.stop_all()
    emptied = baseline.load(db, name)
    db.commit()
    return Loaded(fixture=name, tables_emptied=emptied)


@router.get("/database/counts")
def count_rows(db: Db) -> dict[str, int]:
    """How many rows each table holds, for a test to check what it did."""
    return baseline.counts(db)


@router.post("/database/clean")
def clean_database(db: Db) -> Loaded:
    """Empties every table, then loads the baseline."""
    return _load(db, "baseline")


@router.post("/fixtures/{name}")
def load_fixture(name: FixtureName, db: Db) -> Loaded:
    """Empties every table, then loads a named state (``GET /fixtures`` lists them)."""
    return _load(db, name)


class SystemInfoRequest(BaseModel):
    key: str | None = None
    value: str = factories.DEFAULT_VALUE


class SystemInfoRecord(BaseModel):
    key: str
    value: str
    updated_at: datetime


@router.post("/factories/system-info", status_code=status.HTTP_201_CREATED)
def make_system_info(body: SystemInfoRequest, db: Db) -> SystemInfoRecord:
    """Adds a ``system_info`` row; whatever the request leaves out is made up."""
    row = factories.system_info(db, key=body.key, value=body.value)
    record = SystemInfoRecord(key=row.key, value=row.value, updated_at=row.updated_at)
    db.commit()
    return record


class AccountRequest(BaseModel):
    username: str | None = None
    password: str = factories.DEFAULT_PASSWORD


@router.post("/factories/account", status_code=status.HTTP_201_CREATED)
def make_account(body: AccountRequest, db: Db) -> AccountLogin:
    """Adds an account; whatever the request leaves out is made up. Returns what to sign in with."""
    user = factories.account(db, username=body.username, password=body.password)
    login = AccountLogin(username=user.username, password=body.password)
    db.commit()
    return login


class StandInRequest(BaseModel):
    kind: Kind
    # What it accepts: ntopng a `token`, CrowdSec and Zenarmor an `api_key`, OPNsense an
    # `api_key` and `api_secret`.
    token: str = ""
    api_key: str = ""
    api_secret: str = ""
    # OPNsense only: the services (by key) that are installed and running on it.
    services: list[str] = []


class StandInRecord(BaseModel):
    id: str
    kind: Kind
    url: str
    # The SHA-256 fingerprint of its certificate, for the ones that have one.
    fingerprint: str | None


@router.post("/stand-ins", status_code=status.HTTP_201_CREATED)
def start_stand_in(body: StandInRequest) -> StandInRecord:
    """Starts a server on this machine that answers like an integration, for a test to connect to.
    It runs until the next time the database is put back to a known state."""
    running = STAND_INS.start(
        body.kind,
        token=body.token,
        api_key=body.api_key,
        api_secret=body.api_secret,
        services=body.services,
    )
    return StandInRecord(
        id=running.id, kind=running.kind, url=running.url, fingerprint=running.fingerprint
    )


@router.delete("/stand-ins", status_code=status.HTTP_204_NO_CONTENT)
def stop_stand_ins() -> None:
    """Stops every stand-in."""
    STAND_INS.stop_all()


@router.get("/coverage")
def api_coverage(measurement: Measurement) -> CoverageReport:
    """The API's coverage so far, as an HTML report and an LCOV file."""
    if measurement is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The API isn't running under coverage.")
    return report(measurement)
