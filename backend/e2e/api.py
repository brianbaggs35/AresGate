"""Endpoints the Playwright tests call to set up each test, under /api/__test__.

They put the database back to a known state, make extra records and hand over the API's code
coverage. Only ``e2e.main`` mounts them.
"""

from datetime import datetime, timedelta
from typing import Annotated, Literal

import coverage
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import delete
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import SettingsDep
from app.collectors.health import WORKER
from app.collectors.scheduler import Scheduler
from app.db import get_session
from app.integrations.apilog import ApiLogRecorder
from app.models import WorkerBeat, utcnow
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


def collector_scheduler(request: Request, settings: SettingsDep, db: Db) -> Scheduler:
    """A scheduler on the same database as the request, and allowed the addresses the stand-ins
    have (the product's own is not)."""
    new_session = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    return Scheduler(
        settings, new_session, ApiLogRecorder(new_session), request.app.state.address_policy
    )


@router.post("/collectors/run", status_code=status.HTTP_204_NO_CONTENT)
async def run_collectors(scheduler: Annotated[Scheduler, Depends(collector_scheduler)]) -> None:
    """Runs every collector once, now, and answers when they have all finished. The worker does
    nothing of its own in the tests, so a test decides when collecting happens."""
    await scheduler.run_once()


class WorkerStatus(BaseModel):
    # Running reported in just now, stopped last did a while ago, and absent never has.
    state: Literal["running", "stopped", "absent"]


@router.put("/collectors/worker", status_code=status.HTTP_204_NO_CONTENT)
def set_worker_status(body: WorkerStatus, db: Db) -> None:
    """Makes the worker look like it is running, has stopped or has never reported in."""
    db.execute(delete(WorkerBeat))
    if body.state != "absent":
        now = utcnow()
        seen = now if body.state == "running" else now - timedelta(minutes=10)
        db.add(WorkerBeat(name=WORKER, started_at=now - timedelta(hours=1), beat_at=seen))
    db.commit()


@router.get("/coverage")
def api_coverage(measurement: Measurement) -> CoverageReport:
    """The API's coverage so far, as an HTML report and an LCOV file."""
    if measurement is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The API isn't running under coverage.")
    return report(measurement)
