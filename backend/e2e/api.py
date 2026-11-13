"""Endpoints the Playwright tests call to set up each test, under /api/__test__.

They put the database back to a known state, make extra records and hand over the API's code
coverage. Only ``e2e.main`` mounts them.
"""

import json
from datetime import datetime, timedelta
from typing import Annotated, Any, Literal

import coverage
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import delete
from sqlalchemy.orm import Session, sessionmaker

from app.agents import run as agents
from app.ai.gateway import Context
from app.alerts import notify
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
    request.app.state.alert_origin = None
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


class RepeatedRequest(BaseModel):
    """An alert that a program keeps reporting."""

    source: str = Field(max_length=32)
    signature: str = Field(max_length=256)
    severity: Literal["info", "low", "medium", "high", "critical"] = "medium"
    count: int = Field(ge=1, le=500)


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
    # Alerts that a program keeps reporting, which the dashboard says make the noise.
    repeated: list[RepeatedRequest] = Field(default=[], max_length=20)


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
        repeated=[
            factories.Repeated(
                item.source, item.signature, Severity[item.severity.upper()], item.count
            )
            for item in body.repeated
        ],
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
    ban_left: str = Field(default="3h59m12s", max_length=40)
    blocks: int = Field(default=0, ge=0, le=100)
    blocks_after_ban: int = Field(default=0, ge=0, le=100)
    dropped: int = Field(default=0, ge=0, le=50)
    minutes_ago: int = Field(default=10, ge=0, le=60 * 20)
    device: str = "192.168.1.20"
    device_name: str | None = None
    status: factories.IncidentStatusName = "open"
    idle_days: int = Field(default=0, ge=0, le=365)
    neighbours: int = Field(default=0, ge=0, le=20)
    waves: int = Field(default=1, ge=1, le=10)
    ports: list[Annotated[int, Field(ge=1, le=65_535)]] = Field(default=[], max_length=50)
    scan: bool = False
    exploit: bool = False
    compromise: bool = False
    twin: str | None = Field(default=None, max_length=32)
    # Whether the device sent the signals to the address, as a camera calls its cloud.
    outbound: bool = False
    # Whether each program gives what it knows besides the basics.
    detailed: bool = False
    # Whether the firewall's record also holds what was said on the wire (needs `detailed`).
    wire: bool = False
    # A CVE the alerts name.
    cve: str | None = Field(default=None, pattern=r"^CVE-\d{4}-\d{4,7}$")


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
                ban_left=item.ban_left,
                blocks=item.blocks,
                blocks_after_ban=item.blocks_after_ban,
                dropped=item.dropped,
                minutes_ago=item.minutes_ago,
                device=item.device,
                device_name=item.device_name,
                outbound=item.outbound,
                status=item.status,
                idle_days=item.idle_days,
                neighbours=item.neighbours,
                waves=min(item.waves, item.signals),
                ports=item.ports,
                scan=item.scan,
                exploit=item.exploit,
                compromise=item.compromise,
                twin=item.twin,
                detailed=item.detailed,
                wire=item.wire,
                cve=item.cve,
            )
            for item in body.incidents
        ],
    )
    db.commit()
    return IncidentsRecord(**stored._asdict())


class EventRequest(BaseModel):
    """One event, or a run of them, as a program would have reported it. All of it is optional."""

    source: str = Field(default="opnsense", max_length=32)
    connection: str | None = Field(default=None, max_length=32)
    kind: str = Field(default="firewall", max_length=32)
    severity: Literal["info", "low", "medium", "high", "critical"] = "info"
    summary: str = Field(default="Blocked tcp", max_length=500)
    signature: str | None = Field(default=None, max_length=256)
    src_address: str | None = None
    src_port: int | None = Field(default=None, ge=0, le=65_535)
    dst_address: str | None = None
    dst_port: int | None = Field(default=None, ge=0, le=65_535)
    protocol: str | None = Field(default=None, max_length=16)
    iface: str | None = Field(default=None, max_length=64)
    seconds_ago: int = Field(default=60, ge=0, le=60 * 60 * 24 * 20)
    raw: dict[str, Any] | None = None
    repeat: int = Field(default=1, ge=1, le=500)
    every_seconds: int = Field(default=30, ge=1, le=60 * 60 * 24)


class EventsRequest(BaseModel):
    events: list[EventRequest]


class EventsRecord(BaseModel):
    events: int


@router.post("/factories/events", status_code=status.HTTP_201_CREATED)
def make_events(body: EventsRequest, db: Db, settings: SettingsDep) -> EventsRecord:
    """Stores events as of now, as the programs would have reported them, for the Logs page to
    show. They are not filed into incidents."""
    stored = factories.events(
        db,
        settings,
        utcnow(),
        [
            factories.EventSpec(
                source=item.source,
                connection=item.connection,
                kind=item.kind,
                severity=Severity[item.severity.upper()],
                summary=item.summary,
                signature=item.signature,
                src_address=item.src_address,
                src_port=item.src_port,
                dst_address=item.dst_address,
                dst_port=item.dst_port,
                protocol=item.protocol,
                iface=item.iface,
                seconds_ago=item.seconds_ago,
                raw=item.raw,
                repeat=item.repeat,
                every_seconds=item.every_seconds,
            )
            for item in body.events
        ],
    )
    db.commit()
    return EventsRecord(events=stored)


class VerdictRequest(BaseModel):
    """One verdict, as the owner would give it: what it says and at least one thing it is about."""

    verdict: Literal["not_suspicious", "low_priority", "threat"]
    address: str | None = None
    destination: str | None = None
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


class DecisionRequest(BaseModel):
    """One decision of the AI about an incident that is there, and where its review stands."""

    address: str = Field(max_length=64)
    subject: Literal["incident", "family"] = "family"
    ai_class: Literal["compromise", "attack", "probe", "noise", "unclear"] = "probe"
    confidence: int = Field(default=90, ge=0, le=100)
    review: Literal["pending", "auto", "agreed", "disagreed"] = "pending"
    headline: str = Field(default="Routine scanning from the internet.", max_length=160)


class DecisionsRequest(BaseModel):
    decisions: list[DecisionRequest]


class DecisionsRecord(BaseModel):
    decisions: int


@router.post("/factories/decisions", status_code=status.HTTP_201_CREATED)
def make_decisions(body: DecisionsRequest, db: Db) -> DecisionsRecord:
    """Records what an AI decided of incidents that are there, for the Review page to show."""
    made = factories.decisions(
        db, utcnow(), [factories.DecisionSpec(**item.model_dump()) for item in body.decisions]
    )
    db.commit()
    return DecisionsRecord(decisions=made)


class ReviewSettingsRequest(BaseModel):
    mode: Literal["all", "uncertain", "auto"] = "all"
    auto_from: int = Field(default=85, ge=50, le=100)
    learn: bool = True


@router.post("/factories/review-settings", status_code=status.HTTP_201_CREATED)
def make_review_settings(body: ReviewSettingsRequest, db: Db) -> ReviewSettingsRequest:
    """Sets how much of what the AI decides waits for the owner."""
    factories.review_settings(db, body.mode, body.auto_from, body.learn)
    db.commit()
    return body


class AiCallRequest(BaseModel):
    """One request to an AI provider. All of it is optional: it is made up where left out."""

    purpose: str = Field(default="triage", max_length=24)
    about: str | None = Field(default=None, max_length=120)
    provider: str = Field(default="anthropic", max_length=32)
    model: str = Field(default="claude-haiku-5-5", max_length=128)
    ok: bool = True
    input_tokens: int = Field(default=1200, ge=0, le=10_000_000)
    output_tokens: int = Field(default=300, ge=0, le=10_000_000)
    cached_tokens: int = Field(default=0, ge=0, le=10_000_000)
    cost_micros: int | None = Field(default=1_500, ge=0, le=10_000_000_000)
    hours_ago: int = Field(default=1, ge=0, le=24 * 100)
    error: str | None = Field(default=None, max_length=500)
    repeat: int = Field(default=1, ge=1, le=200)


class AiCallsRequest(BaseModel):
    calls: list[AiCallRequest]


class AiCallsRecord(BaseModel):
    calls: int


@router.post("/factories/ai-calls", status_code=status.HTTP_201_CREATED)
def make_ai_calls(body: AiCallsRequest, db: Db) -> AiCallsRecord:
    """Records some requests to AI providers as of now, for the usage page to show."""
    made = factories.ai_calls(
        db, utcnow(), [factories.CallSpec(**item.model_dump()) for item in body.calls]
    )
    db.commit()
    return AiCallsRecord(calls=made)


class FeedRequest(BaseModel):
    """One feed, as discovery would have found it, and where it is placed."""

    integration: str = Field(default="opnsense", max_length=32)
    native_name: str = Field(default="", max_length=64)
    connection: str | None = Field(default=None, max_length=32)
    label: str = Field(default="", max_length=120)
    detail: str = Field(default="", max_length=200)
    interface: str | None = Field(default=None, max_length=40)
    role: str = Field(default="other", max_length=16)
    ignored: bool = False


class FeedsRequest(BaseModel):
    feeds: list[FeedRequest]


class FeedsRecord(BaseModel):
    feeds: int


@router.post("/factories/feeds", status_code=status.HTTP_201_CREATED)
def make_feeds(body: FeedsRequest, db: Db) -> FeedsRecord:
    """Makes feeds, and the interfaces they are placed on, for the Interfaces page to show."""
    made = factories.feeds(db, [factories.FeedSpec(**item.model_dump()) for item in body.feeds])
    db.commit()
    return FeedsRecord(feeds=made)


class ListedRequest(BaseModel):
    """One way a device was listed, and how long ago."""

    source: str = Field(default="opnsense", max_length=32)
    via: str = Field(default="arp", max_length=16)
    minutes_ago: float = Field(default=1, ge=0, le=60 * 24 * 365)
    own: bool = False


class DeviceRequest(BaseModel):
    """A device, as the integrations that list it left it."""

    hostname: str | None = Field(default=None, max_length=253)
    mac: str | None = Field(default=None, max_length=17)
    vendor: str | None = Field(default=None, max_length=128)
    addresses: list[str] = Field(default_factory=list[str], max_length=8)
    earlier: list[str] = Field(default_factory=list[str], max_length=8)
    listed: list[ListedRequest] = Field(default_factory=lambda: [ListedRequest()])
    first_seen_hours: float = Field(default=24 * 30, ge=0, le=24 * 365 * 5)


class HostRequest(BaseModel):
    """A machine with no hardware address, such as a Wazuh agent."""

    key: str = Field(min_length=1, max_length=128)
    hostname: str | None = Field(default=None, max_length=253)
    address: str | None = Field(default=None, max_length=64)
    state: str = Field(default="active", max_length=32)
    online: bool = True
    minutes_ago: float = Field(default=0, ge=0, le=60 * 24 * 365)
    source: str = Field(default="wazuh", max_length=32)
    connection: str = Field(default="manager", max_length=32)
    via: str = Field(default="agent", max_length=16)


class AssetsRequest(BaseModel):
    devices: list[DeviceRequest] = Field(default_factory=list[DeviceRequest], max_length=200)
    hosts: list[HostRequest] = Field(default_factory=list[HostRequest], max_length=50)


class AssetsRecord(BaseModel):
    devices: int
    hosts: int


def _device_spec(item: DeviceRequest) -> factories.AssetSpec:
    return factories.AssetSpec(
        hostname=item.hostname,
        mac=item.mac,
        vendor=item.vendor,
        addresses=tuple(item.addresses),
        earlier=tuple(item.earlier),
        listed=tuple(factories.Listed(**each.model_dump()) for each in item.listed),
        first_seen_hours=item.first_seen_hours,
    )


@router.post("/factories/assets", status_code=status.HTTP_201_CREATED)
def make_assets(body: AssetsRequest, db: Db) -> AssetsRecord:
    """Stores devices and machines as the integrations that list them leave them, for the Assets
    page to show."""
    made = factories.assets(
        db,
        utcnow(),
        [_device_spec(item) for item in body.devices],
        [factories.HostSpec(**item.model_dump()) for item in body.hosts],
    )
    db.commit()
    return AssetsRecord(devices=made.devices, hosts=made.hosts)


class TrafficHostRequest(BaseModel):
    """What ntopng read of one host: the bytes it sent and received, an hour apart, oldest first."""

    host: str = Field(min_length=1, max_length=64)
    sent: list[float] = Field(default_factory=list[float], max_length=24 * 7)
    received: list[float] = Field(default_factory=list[float], max_length=24 * 7)


class TrafficRequest(BaseModel):
    hosts: list[TrafficHostRequest] = Field(default_factory=list[TrafficHostRequest], max_length=50)


class TrafficRecord(BaseModel):
    readings: int


@router.post("/factories/traffic", status_code=status.HTTP_201_CREATED)
def make_traffic(body: TrafficRequest, db: Db, settings: SettingsDep) -> TrafficRecord:
    """Stores what ntopng read of hosts, for an asset's page to chart the traffic of."""
    stored = factories.traffic(
        db,
        settings,
        utcnow(),
        [
            factories.TrafficSpec(host=item.host, sent=item.sent, received=item.received)
            for item in body.hosts
        ],
    )
    db.commit()
    return TrafficRecord(readings=stored)


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
    # Discord: the `id/token` of the one webhook it knows. Alerts are sent to it instead of to
    # Discord while it runs.
    webhook: str = ""
    # ntopng only: it numbers its interfaces the way one on an OPNsense firewall does (WAN 1, LAN 2,
    # the loopback 3, a VPN 6), not from 0.
    firewall: bool = False


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
        webhook=body.webhook,
        firewall=body.firewall,
    )
    if body.provider is not None:
        request.app.state.ai_origins[body.provider] = running.url
    if body.kind == "discord":
        request.app.state.alert_origin = running.url
    return StandInRecord(
        id=running.id, kind=running.kind, url=running.url, fingerprint=running.fingerprint
    )


class StandInRequestSeen(BaseModel):
    method: str
    path: str
    user_agent: str
    # The message that was posted, if it was JSON.
    body: Any


@router.get("/stand-ins/{stand_in_id}/requests")
def stand_in_requests(stand_in_id: str) -> list[StandInRequestSeen]:
    """What a stand-in was asked, oldest first, for a test to check what AresGate sent."""
    seen: list[StandInRequestSeen] = []
    for request in STAND_INS.requests(stand_in_id):
        try:
            body = json.loads(request.body) if request.body else None
        except ValueError:
            body = None
        seen.append(
            StandInRequestSeen(
                method=request.method,
                path=request.path,
                user_agent=request.headers.get("user-agent", ""),
                body=body,
            )
        )
    return seen


@router.delete("/stand-ins", status_code=status.HTTP_204_NO_CONTENT)
def stop_stand_ins(request: Request) -> None:
    """Stops every stand-in."""
    STAND_INS.stop_all()
    request.app.state.ai_origins.clear()
    request.app.state.alert_origin = None


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


class NotifierReport(BaseModel):
    sent: int
    retrying: int
    failed: int


@router.post("/notifier/run")
async def run_notifier(request: Request, settings: SettingsDep, db: Db) -> NotifierReport:
    """Tells the destinations of the incidents there are, now, once, and answers how it went. The
    worker does nothing of its own in the tests, so a test decides when alerts are sent. Discord is
    the stand-in the test started, if it started one."""
    new_session = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    report = await notify.notify_once(
        settings,
        new_session,
        ApiLogRecorder(new_session),
        request.app.state.alert_policy,
        request.app.state.alert_origin,
        pace=0,
    )
    return NotifierReport(sent=report.sent, retrying=report.retrying, failed=report.failed)


class AgentsRun(BaseModel):
    # Devices to say answered, as "address:port". Nothing is connected to where a test sets this,
    # so no test of the network ever depends on what is open on the machine it runs on.
    open: list[str] = Field(default_factory=list[str], max_length=100)


class AgentsReport(BaseModel):
    ran: int


@router.post("/agents/run")
async def run_agents(
    body: AgentsRun, request: Request, settings: SettingsDep, db: Db
) -> AgentsReport:
    """Starts the agents' runs that are due, runs everything that waits, now, once, and answers how
    many it ran. The worker does nothing of its own in the tests, so a test decides when an agent
    runs. Providers are the stand-ins the test started, if it started any."""
    new_session = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    state = request.app.state
    context = Context(
        settings=settings,
        recorder=ApiLogRecorder(new_session),
        hosted=state.ai_policy,
        local=state.local_ai_policy,
        origins=state.ai_origins,
    )
    answering = set(body.open)
    probing = agents.Probing(
        policy=state.address_policy,
        connect=lambda address, port, _timeout: f"{address}:{port}" in answering,
    )
    return AgentsReport(ran=await agents.run_once(new_session, context, probing))


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
