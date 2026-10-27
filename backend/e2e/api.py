"""Endpoints the Playwright tests call to set up each test, under /api/__test__.

They put the database back to a known state, make extra records and hand over the API's code
coverage. Only ``e2e.main`` mounts them.
"""

from datetime import datetime, timedelta
from typing import Annotated, Literal

import coverage
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import delete
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import SettingsDep
from app.collectors.health import WORKER
from app.collectors.scheduler import Scheduler
from app.db import get_session
from app.events.event import Severity
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


def _load(db: Session, name: FixtureName, request: Request) -> Loaded:
    STAND_INS.stop_all()
    request.app.state.ai_origins.clear()
    emptied = baseline.load(db, name)
    db.commit()
    return Loaded(fixture=name, tables_emptied=emptied)


@router.get("/database/counts")
def count_rows(db: Db) -> dict[str, int]:
    """How many rows each table holds, for a test to check what it did."""
    return baseline.counts(db)


@router.post("/database/clean")
def clean_database(db: Db, request: Request) -> Loaded:
    """Empties every table, then loads the baseline."""
    return _load(db, "baseline", request)


@router.post("/fixtures/{name}")
def load_fixture(name: FixtureName, db: Db, request: Request) -> Loaded:
    """Empties every table, then loads a named state (``GET /fixtures`` lists them)."""
    return _load(db, name, request)


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


class ActivityRequest(BaseModel):
    """What the dashboard has to show. All of it is optional: none at all is a quiet network."""

    # How many alerts of each severity, such as {"high": 2}.
    alerts: dict[Literal["info", "low", "medium", "high", "critical"], int] = {}
    # How many connections the firewall refused from each address.
    blocked: dict[str, int] = {}
    # A steady speed in megabits a second for each interface of the firewall.
    traffic: dict[str, float] = {}
    # How many devices were seen for the first time half an hour ago.
    devices: int = 0
    # A collector of the firewall in each of these states, to say how collecting is going.
    collectors: list[factories.CollectorState] = []


class ActivityRecord(BaseModel):
    alerts: int
    blocked: int
    samples: int
    devices: int
    collectors: int


@router.post("/factories/activity", status_code=status.HTTP_201_CREATED)
def make_activity(body: ActivityRequest, db: Db, settings: SettingsDep) -> ActivityRecord:
    """Stores alerts, refused connections, interface speeds and new devices as of now, for the
    dashboard to show."""
    stored = factories.activity(
        db,
        settings,
        utcnow(),
        alerts={Severity[name.upper()]: count for name, count in body.alerts.items()},
        blocked=body.blocked,
        traffic=body.traffic,
        devices=body.devices,
        collectors=body.collectors,
    )
    db.commit()
    return ActivityRecord(**stored._asdict())


class IncidentRequest(BaseModel):
    """One attack that programs saw. All of it is optional: it is made up where left out."""

    address: str | None = None
    severity: Literal["info", "low", "medium", "high", "critical"] = "high"
    programs: list[str] = ["wazuh"]
    signals: int = Field(default=1, ge=1, le=50)
    ban: bool = False
    minutes_ago: int = Field(default=10, ge=0, le=60 * 20)
    device: str = "192.168.1.20"
    device_name: str | None = None
    status: factories.IncidentStatusName = "open"


class IncidentsRequest(BaseModel):
    incidents: list[IncidentRequest]


class IncidentsRecord(BaseModel):
    signals: int
    incidents: int


@router.post("/factories/incidents", status_code=status.HTTP_201_CREATED)
def make_incidents(body: IncidentsRequest, db: Db, settings: SettingsDep) -> IncidentsRecord:
    """Stores the alerts of some attacks as of now and files them into incidents, as the worker
    would have, for the Incidents pages to show."""
    stored = factories.incidents(
        db,
        settings,
        utcnow(),
        [
            factories.IncidentSpec(
                address=item.address,
                severity=Severity[item.severity.upper()],
                programs=item.programs,
                signals=item.signals,
                ban=item.ban,
                minutes_ago=item.minutes_ago,
                device=item.device,
                device_name=item.device_name,
                status=item.status,
            )
            for item in body.incidents
        ],
    )
    db.commit()
    return IncidentsRecord(**stored._asdict())


class VerdictRequest(BaseModel):
    """One verdict, as the owner would give it: what it says and at least one thing it is about."""

    verdict: Literal["not_suspicious", "low_priority", "threat"]
    address: str | None = None
    source: str | None = None
    signature: str | None = None
    note: str | None = None


class VerdictsRequest(BaseModel):
    verdicts: list[VerdictRequest]


class VerdictsRecord(BaseModel):
    verdicts: int


@router.post("/factories/verdicts", status_code=status.HTTP_201_CREATED)
def make_verdicts(body: VerdictsRequest, db: Db) -> VerdictsRecord:
    """Gives some verdicts and judges the incidents there are by them."""
    given = factories.verdicts(
        db, [factories.VerdictSpec(**item.model_dump()) for item in body.verdicts]
    )
    db.commit()
    return VerdictsRecord(verdicts=given)


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
    # `api_key` and `api_secret`, Wazuh a `username` and `password`.
    token: str = ""
    api_key: str = ""
    api_secret: str = ""
    # OPNsense only: the services (by key) that are installed and running on it.
    services: list[str] = []
    # Wazuh: the user and password of its manager and its indexer.
    username: str = ""
    password: str = ""
    # An AI provider's stand-in (Anthropic and OpenAI take an `api_key`, an Ollama one only when
    # it is Ollama's cloud): the models it has, and, for a hosted provider, which one it stands
    # in for, so AresGate asks it instead of the real one.
    models: list[str] = []
    # An Ollama's models that need a paid plan: they are listed, and answer 402 Payment Required.
    paid: list[str] = []
    provider: Literal["anthropic", "openai", "ollama_cloud"] | None = None


class StandInRecord(BaseModel):
    id: str
    kind: Kind
    url: str
    # The SHA-256 fingerprint of its certificate, for the ones that have one.
    fingerprint: str | None


@router.post("/stand-ins", status_code=status.HTTP_201_CREATED)
def start_stand_in(body: StandInRequest, request: Request) -> StandInRecord:
    """Starts a server on this machine that answers like an integration, for a test to connect to.
    It runs until the next time the database is put back to a known state."""
    running = STAND_INS.start(
        body.kind,
        token=body.token,
        api_key=body.api_key,
        api_secret=body.api_secret,
        services=body.services,
        username=body.username,
        password=body.password,
        models=body.models,
        paid=body.paid,
    )
    if body.provider is not None:
        request.app.state.ai_origins[body.provider] = running.url
    return StandInRecord(
        id=running.id, kind=running.kind, url=running.url, fingerprint=running.fingerprint
    )


@router.delete("/stand-ins", status_code=status.HTTP_204_NO_CONTENT)
def stop_stand_ins(request: Request) -> None:
    """Stops every stand-in."""
    STAND_INS.stop_all()
    request.app.state.ai_origins.clear()


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
