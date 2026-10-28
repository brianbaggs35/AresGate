"""The integrations: what can be connected, connecting and disconnecting them, testing a
connection and reading the log of the requests made to it. Secrets only go in: no route here
returns one, and a failed request doesn't quote what was sent."""

from datetime import datetime
from typing import Annotated, cast

import anyio.from_thread
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response, status
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy.orm import Session

from app.api.deps import Db, SettingsDep, SignedIn, record_audit, signed_in
from app.audit import Action, Outcome
from app.db import get_sessionmaker
from app.integrations import apilog, netguard, probes, registry, service
from app.integrations.apilog import DEFAULT_PAGE, MAX_PAGE, ApiLogRecorder
from app.integrations.client import Recorder
from app.integrations.netguard import AddressPolicy
from app.integrations.registry import (
    ConnectionDef,
    Entry,
    IntegrationDef,
    ModuleState,
    SettingsError,
)
from app.integrations.service import Status, Submission
from app.models import IntegrationConnection, utcnow
from app.security.credential_store import NAME_PATTERN

# Everything here is for someone who is signed in.
router = APIRouter(prefix="/integrations", tags=["integrations"], dependencies=[Depends(signed_in)])

Key = Annotated[str, Path(pattern=NAME_PATTERN, description="An integration, such as opnsense.")]


def address_policy(request: Request) -> AddressPolicy:
    """Which addresses integrations may be at. The app sets it when it is made."""
    return cast("AddressPolicy", request.app.state.address_policy)


def api_log_recorder() -> Recorder:
    """Where the requests made to integrations are logged."""
    return ApiLogRecorder(get_sessionmaker())


PolicyDep = Annotated[AddressPolicy, Depends(address_policy)]
RecorderDep = Annotated[Recorder, Depends(api_log_recorder)]


class ModuleOut(BaseModel):
    """A service that runs on the system, and whether AresGate reads it."""

    key: str
    label: str
    summary: str
    # None until the connection has been tested.
    state: ModuleState | None
    enabled: bool


class ServiceOut(BaseModel):
    """A service that was found, for the integration's card."""

    key: str
    label: str
    state: ModuleState


class ConnectionOut(BaseModel):
    """One connection of an integration: what it takes, and what it is set to."""

    definition: ConnectionDef
    url: str | None
    tls_mode: str
    tls_ca_pem: str | None
    tls_fingerprint: str | None
    options: dict[str, str | int]
    modules: list[ModuleOut]
    # Which secrets are kept. Their values are never returned.
    secrets_set: list[str]
    status: Status
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    last_error: str | None


class IntegrationSummary(BaseModel):
    key: str
    name: str
    provides: str
    icon: str
    status: Status
    last_success_at: datetime | None
    services: list[ServiceOut]


class IntegrationOut(IntegrationSummary):
    docs_url: str
    setup: tuple[str, ...]
    last_error: str | None
    connections: list[ConnectionOut]


class ConnectionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(max_length=1024)
    tls_mode: str = Field(default="system", max_length=16)
    tls_ca_pem: str | None = Field(default=None, max_length=65536)
    tls_fingerprint: str | None = Field(default=None, max_length=256)
    options: dict[str, str | int | None] = Field(default_factory=dict, max_length=20)
    # Services not to read, by key.
    disabled_modules: list[str] = Field(default_factory=list, max_length=40)
    # A secret left out, or blank, keeps the one already kept.
    secrets: dict[str, Annotated[SecretStr, Field(max_length=4096)]] = Field(
        default_factory=dict, max_length=20
    )


class IntegrationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connections: dict[str, ConnectionIn] = Field(max_length=10)


class Check(BaseModel):
    connection: str
    ok: bool
    message: str


class CheckReport(BaseModel):
    """How a test went, and the integration as it is now."""

    ok: bool
    checks: list[Check]
    integration: IntegrationOut


class LookupOut(BaseModel):
    """What a system listed when it was asked for a field's choices (such as ntopng's
    interfaces), or why it couldn't say."""

    ok: bool
    message: str
    entries: list[Entry]


class CertificateRequest(BaseModel):
    url: str = Field(max_length=1024)


class CertificateOut(BaseModel):
    fingerprint: str
    subject: str
    issuer: str
    not_before: datetime
    not_after: datetime
    names: list[str]


class CallOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    occurred_at: datetime
    connection: str
    method: str
    path: str
    status_code: int | None
    duration_ms: int
    error: str | None


class CallPage(BaseModel):
    calls: list[CallOut]
    # Pass it back as ``before`` for the next page of older calls. Missing on the last page.
    next_before: int | None


def _definition(key: str) -> IntegrationDef:
    definition = registry.INTEGRATIONS.get(key)
    if definition is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There is no such integration.")
    return definition


def _invalid(*location: str, message: str) -> dict[str, object]:
    """One problem in the shape of FastAPI's own, so the web app reads both the same way."""
    return {"type": "value_error", "loc": ["body", *location], "msg": message}


def _modules(definition: ConnectionDef, row: IntegrationConnection | None) -> list[ModuleOut]:
    states = row.module_states if row else {}
    disabled: set[str] = set(row.disabled_modules) if row else set()
    return [
        ModuleOut(
            key=module.key,
            label=module.label,
            summary=module.summary,
            state=ModuleState(states[module.key]) if module.key in states else None,
            enabled=module.key not in disabled,
        )
        for module in definition.modules
    ]


def _services(
    definition: IntegrationDef, rows: dict[str, IntegrationConnection]
) -> list[ServiceOut]:
    return [
        ServiceOut(key=module.key, label=module.label, state=module.state)
        for connection in definition.connections
        for module in _modules(connection, rows.get(connection.key))
        if module.state and module.state.present and module.enabled
    ]


def _connection_out(
    db: Session, integration: str, definition: ConnectionDef, row: IntegrationConnection | None
) -> ConnectionOut:
    return ConnectionOut(
        definition=definition,
        url=row.base_url if row else None,
        tls_mode=row.tls_mode if row else "system",
        tls_ca_pem=row.tls_ca_pem if row else None,
        tls_fingerprint=row.tls_fingerprint if row else None,
        options=dict(row.options) if row else {},
        modules=_modules(definition, row),
        secrets_set=service.secrets_set(db, integration, definition.key),
        status=service.connection_status(row),
        last_attempt_at=row.last_attempt_at if row else None,
        last_success_at=row.last_success_at if row else None,
        last_error=row.last_error if row else None,
    )


def _integration_out(db: Session, definition: IntegrationDef) -> IntegrationOut:
    rows = service.rows_for(db, definition.key)
    problems = [row.last_error for row in rows.values() if row.last_error]
    return IntegrationOut(
        key=definition.key,
        name=definition.name,
        provides=definition.provides,
        icon=definition.icon,
        status=service.integration_status(rows),
        last_success_at=service.last_success(rows),
        services=_services(definition, rows),
        docs_url=definition.docs_url,
        setup=definition.setup,
        last_error=problems[0] if problems else None,
        connections=[
            _connection_out(db, definition.key, item, rows.get(item.key))
            for item in definition.connections
        ],
    )


@router.get("")
def list_integrations(db: Db) -> list[IntegrationSummary]:
    """Every integration there is, with whether it is connected."""
    summaries: list[IntegrationSummary] = []
    for definition in registry.INTEGRATIONS.values():
        rows = service.rows_for(db, definition.key)
        summaries.append(
            IntegrationSummary(
                key=definition.key,
                name=definition.name,
                provides=definition.provides,
                icon=definition.icon,
                status=service.integration_status(rows),
                last_success_at=service.last_success(rows),
                services=_services(definition, rows),
            )
        )
    return summaries


@router.get("/{key}")
def get_integration(key: Key, db: Db) -> IntegrationOut:
    """One integration: what it needs to connect, and how it is set up now."""
    return _integration_out(db, _definition(key))


@router.put("/{key}")
def connect_integration(
    key: Key,
    body: IntegrationIn,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
    settings: SettingsDep,
    policy: PolicyDep,
) -> IntegrationOut:
    """Saves how to reach an integration, replacing what was saved, and keeps its secrets. It
    isn't tested yet: ``POST /{key}/test`` does that."""
    definition = _definition(key)
    submitted = {
        name: Submission(
            url=item.url,
            tls_mode=item.tls_mode,
            tls_ca_pem=item.tls_ca_pem,
            tls_fingerprint=item.tls_fingerprint,
            options=item.options,
            secrets={field: value.get_secret_value() for field, value in item.secrets.items()},
            disabled_modules=item.disabled_modules,
        )
        for name, item in body.connections.items()
    }
    try:
        service.save(db, settings, policy, definition, submitted, utcnow())
    except SettingsError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            [
                _invalid("connections", *name.split("."), message=text)
                for name, text in error.problems.items()
            ],
        ) from error
    record_audit(
        db,
        request,
        Action.INTEGRATION_CONNECTED,
        Outcome.SUCCESS,
        user=auth.user,
        detail={"integration": key},
    )
    db.commit()
    return _integration_out(db, definition)


@router.delete("/{key}", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_integration(
    key: Key, auth: Annotated[SignedIn, Depends(signed_in)], request: Request, db: Db
) -> Response:
    """Forgets how to reach an integration and its secrets. The API log keeps its entries until
    they are old enough to go."""
    if not service.disconnect(db, _definition(key)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "It isn't connected.")
    record_audit(
        db,
        request,
        Action.INTEGRATION_DISCONNECTED,
        Outcome.SUCCESS,
        user=auth.user,
        detail={"integration": key},
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{key}/test")
def test_integration(
    key: Key,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
    settings: SettingsDep,
    policy: PolicyDep,
    recorder: RecorderDep,
) -> CheckReport:
    """Tests each connection of an integration with one harmless read, and keeps how it went."""
    definition = _definition(key)
    rows = service.rows_for(db, key)
    if not rows:
        raise HTTPException(status.HTTP_409_CONFLICT, "Connect it first.")
    checks: list[Check] = []
    for connection in definition.connections:
        row = rows.get(connection.key)
        if row is None and connection.optional:
            continue
        try:
            if row is None:
                raise service.Incomplete(f"The {connection.label} isn't set up.")
            target = service.load_target(db, settings, definition, connection, row)
            verdict = anyio.from_thread.run(service.check, target, recorder, policy)
        except service.Incomplete as incomplete:
            verdict = service.Verdict(False, str(incomplete))
        if row:
            service.record_attempt(row, verdict, utcnow())
        checks.append(Check(connection=connection.key, ok=verdict.ok, message=verdict.message))
    ok = all(check.ok for check in checks)
    record_audit(
        db,
        request,
        Action.INTEGRATION_TESTED,
        Outcome.SUCCESS if ok else Outcome.FAILURE,
        user=auth.user,
        detail={"integration": key},
    )
    db.commit()
    return CheckReport(ok=ok, checks=checks, integration=_integration_out(db, definition))


# What a setting is called when a lookup can't be made for want of it.
_WHERE = {
    "url": "Address",
    "tls_mode": "Certificate",
    "tls_ca_pem": "Certificate",
    "tls_fingerprint": "Certificate",
    "disabled_modules": "Services",
}


def _fix_first(connection: ConnectionDef, error: SettingsError) -> str:
    """What is wrong with the settings filled in so far, in one sentence for a lookup."""
    labels = {item.key: item.label for item in connection.fields}
    parts = [
        f"{_WHERE.get(name) or labels.get(name) or name}: {text}"
        for name, text in error.problems.items()
    ]
    return f"Fill in the connection first. {' '.join(parts)}"


@router.post("/{key}/connections/{connection}/lookup/{field}")
def look_up_field(
    key: Key,
    connection: Annotated[str, Path(pattern=NAME_PATTERN)],
    field: Annotated[str, Path(pattern=NAME_PATTERN)],
    body: ConnectionIn,
    db: Db,
    settings: SettingsDep,
    policy: PolicyDep,
    recorder: RecorderDep,
) -> LookupOut:
    """Asks the system for the choices of a field, such as the interfaces ntopng has, with the
    address and sign-in as they are filled in (a secret left blank is the one kept). Nothing is
    saved."""
    definition = _definition(key)
    found = definition.connection(connection)
    lookup = probes.LOOKUPS.get((key, connection, field))
    if found is None or lookup is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There is nothing to look up there.")
    submission = Submission(
        url=body.url,
        tls_mode=body.tls_mode,
        tls_ca_pem=body.tls_ca_pem,
        tls_fingerprint=body.tls_fingerprint,
        options=body.options,
        secrets={name: value.get_secret_value() for name, value in body.secrets.items()},
        disabled_modules=body.disabled_modules,
    )
    try:
        target = service.draft_target(db, settings, policy, definition, found, submission)
    except SettingsError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, _fix_first(found, error)
        ) from error
    except service.Incomplete as incomplete:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(incomplete)) from incomplete
    result = anyio.from_thread.run(service.look_up, lookup, target, recorder, policy)
    return LookupOut(ok=result.ok, message=result.message, entries=list(result.entries))


@router.post("/{key}/certificate")
def look_up_certificate(key: Key, body: CertificateRequest, policy: PolicyDep) -> CertificateOut:
    """The certificate the system at an address presents, so that it can be compared with what
    that system shows for itself and then trusted. Nothing is sent to it but the connection."""
    _definition(key)
    try:
        origin = netguard.parse_origin(body.url, allow_http=False)
        netguard.check_reachable(policy, origin)
        found = anyio.from_thread.run(netguard.look_up_certificate, policy, origin)
    except netguard.Refused as refusal:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, [_invalid("url", message=str(refusal))]
        ) from refusal
    return CertificateOut(
        fingerprint=found.fingerprint,
        subject=found.subject,
        issuer=found.issuer,
        not_before=found.not_before,
        not_after=found.not_after,
        names=found.names,
    )


@router.get("/{key}/calls")
def list_calls(
    key: Key,
    db: Db,
    connection: Annotated[str | None, Query(max_length=32)] = None,
    method: Annotated[str | None, Query(max_length=8)] = None,
    failed: Annotated[
        bool | None, Query(description="Only the failed ones, or only the rest.")
    ] = None,
    since: Annotated[AwareDatetime | None, Query(description="From this time on.")] = None,
    until: Annotated[AwareDatetime | None, Query(description="Before this time.")] = None,
    before: Annotated[int | None, Query(ge=1, description="Older than this call id.")] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = DEFAULT_PAGE,
) -> CallPage:
    """The requests made to an integration, newest first."""
    _definition(key)
    page = apilog.list_calls(
        db,
        key,
        connection=connection,
        method=method,
        failed=failed,
        since=since,
        until=until,
        before=before,
        limit=limit,
    )
    return CallPage(
        calls=[CallOut.model_validate(call) for call in page.calls], next_before=page.next_before
    )
