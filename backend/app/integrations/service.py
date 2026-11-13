"""Connecting, testing and disconnecting integrations.

A connection's settings are a row in ``integration_connections``, and its secrets are in the
credential store. Saving checks everything first and changes nothing unless all of it is
acceptable, so a typing mistake never leaves half a connection behind.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import audit
from app.config import Settings
from app.integrations import netguard, probes, registry
from app.integrations.client import ApiClient, Recorder, Target
from app.integrations.netguard import AddressPolicy, Origin, Refused
from app.integrations.probes import Verdict
from app.integrations.registry import (
    ConnectionDef,
    FieldKind,
    IntegrationDef,
    ModuleState,
    SettingsError,
)
from app.models import CollectorHealth, IntegrationConnection
from app.security import credential_store
from app.security.credential_store import Kind
from app.security.vault import VaultError

TLS_MODES = ("system", "ca", "pinned")


class Status(StrEnum):
    NOT_CONNECTED = "not_connected"
    # Saved, but not tested since it was last changed.
    UNTESTED = "untested"
    CONNECTED = "connected"
    # The last attempt failed.
    PROBLEM = "problem"


@dataclass(frozen=True)
class Submission:
    """What was filled in for one connection. A secret left out keeps the one already kept."""

    url: str
    tls_mode: str
    tls_ca_pem: str | None
    tls_fingerprint: str | None
    options: Mapping[str, str | int | None]
    secrets: Mapping[str, str]
    # Modules to leave alone, by key.
    disabled_modules: Sequence[str] = ()


@dataclass(frozen=True)
class _Prepared:
    """A connection's submission, checked and ready to keep."""

    connection: ConnectionDef
    origin: Origin
    tls_mode: str
    tls_ca_pem: str | None
    tls_fingerprint: str | None
    options: dict[str, str | int]
    disabled_modules: list[str]
    new_secrets: dict[str, str]
    # Secrets kept for a way of signing in that is no longer chosen.
    stale_secrets: list[str]


class Incomplete(Exception):
    """A connection that can't be used as it is, such as one whose secret was removed."""


def rows_for(db: Session, integration: str) -> dict[str, IntegrationConnection]:
    """The saved connections of an integration, by connection key."""
    query = select(IntegrationConnection).where(IntegrationConnection.integration == integration)
    return {row.connection: row for row in db.scalars(query)}


def secrets_set(db: Session, integration: str, connection: str) -> list[str]:
    """Which of a connection's secrets are kept, by field. Never their values."""
    name = registry.credential_name(integration, connection)
    return [
        row.field
        for row in credential_store.entries(db)
        if row.kind == Kind.INTEGRATION and row.name == name
    ]


def connection_status(row: IntegrationConnection | None) -> Status:
    if row is None:
        return Status.NOT_CONNECTED
    if row.last_attempt_at is None:
        return Status.UNTESTED
    return Status.PROBLEM if row.last_error else Status.CONNECTED


def integration_status(rows: Mapping[str, IntegrationConnection]) -> Status:
    """The worst of its connections' statuses: it only counts as connected if all are."""
    statuses = {connection_status(row) for row in rows.values()}
    for status in (Status.PROBLEM, Status.UNTESTED):
        if status in statuses:
            return status
    return Status.CONNECTED if statuses else Status.NOT_CONNECTED


def last_success(rows: Mapping[str, IntegrationConnection]) -> datetime | None:
    times = [row.last_success_at for row in rows.values() if row.last_success_at]
    return max(times, default=None)


def _tls_settings(
    submission: Submission, secure: bool, internet: bool
) -> tuple[str, str | None, str | None, dict[str, str]]:
    """The certificate settings to keep: the mode, the certificate authority and the fingerprint,
    and what is wrong with them. A plain http address has no certificate to check, and a service
    on the internet is checked by the certificates this computer trusts, as any site is, so
    whatever was filled in is dropped for either."""
    if not secure or internet:
        return "system", None, None, {}
    problems: dict[str, str] = {}
    mode, ca_pem, fingerprint = submission.tls_mode, None, None
    if mode == "ca":
        try:
            ca_pem = netguard.clean_ca_pem(submission.tls_ca_pem or "")
        except ValueError as error:
            problems["tls_ca_pem"] = str(error)
    elif mode == "pinned":
        fingerprint = netguard.normalize_fingerprint(submission.tls_fingerprint or "")
        if fingerprint is None:
            problems["tls_fingerprint"] = (
                "Enter a SHA-256 fingerprint: 64 hexadecimal digits, with or without colons."
            )
    elif mode != "system":
        problems["tls_mode"] = "Choose how to check the certificate."
    return mode, ca_pem, fingerprint, problems


def _secrets(
    db: Session,
    definition: IntegrationDef,
    connection: ConnectionDef,
    options: Mapping[str, str | int],
    given: Mapping[str, str],
) -> tuple[dict[str, str], list[str], dict[str, str]]:
    """The secrets to store, the ones kept for a way of signing in no longer chosen, and what is
    missing. Leaving a secret blank keeps the one already kept."""
    kept = set(secrets_set(db, definition.key, connection.key))
    active = registry.active_fields(connection, options)
    new: dict[str, str] = {}
    problems: dict[str, str] = {}
    for item in active:
        if item.kind is not FieldKind.SECRET:
            continue
        value = given.get(item.key, "").strip("\r\n\t")
        if value.strip():
            new[item.key] = value
        elif item.key not in kept:
            problems[item.key] = "Enter a value."
    wanted = {item.key for item in active}
    return new, sorted(kept - wanted), problems


def policy_for(connection: ConnectionDef, home: AddressPolicy) -> AddressPolicy:
    """The address policy a connection is checked with: for one on the internet, the policy of that
    one service, which reaches nothing but its own address, so that it is never looked for on the
    home network; the home network's for the rest."""
    if not connection.internet:
        return home
    return netguard.internet_service(netguard.parse_origin(connection.address, allow_http=False))


def _reached_with(target: Target, home: AddressPolicy) -> AddressPolicy:
    """The policy for a connection that is ready to use, found from its definition."""
    definition = registry.INTEGRATIONS[target.integration]
    connection = definition.connection(target.connection)
    return home if connection is None else policy_for(connection, home)


def _prepare(
    db: Session,
    policy: AddressPolicy,
    definition: IntegrationDef,
    connection: ConnectionDef,
    submission: Submission,
) -> tuple[_Prepared | None, dict[str, str]]:
    problems: dict[str, str] = {}
    origin: Origin | None = None
    try:
        # A fixed address is the only one the connection may use, whatever was typed in its place.
        address = connection.address or submission.url
        origin = netguard.parse_origin(address, allow_http=connection.allow_http)
        netguard.check_reachable(policy_for(connection, policy), origin)
    except Refused as refusal:
        problems["url"] = str(refusal)
    mode, ca_pem, fingerprint, tls_problems = _tls_settings(
        submission,
        secure=origin is None or origin.scheme == "https",
        internet=connection.internet,
    )
    problems.update(tls_problems)
    options: dict[str, str | int] | None = None
    try:
        options = registry.clean_options(connection, submission.options)
    except SettingsError as error:
        problems.update(error.problems)
    known = {module.key for module in connection.modules}
    if not set(submission.disabled_modules) <= known:
        problems["disabled_modules"] = "That isn't one of its services."
    new_secrets: dict[str, str] = {}
    stale: list[str] = []
    if options is not None:
        # Which secrets apply depends on the options, so they're only looked at once those are fine.
        new_secrets, stale, secret_problems = _secrets(
            db, definition, connection, options, submission.secrets
        )
        problems.update(secret_problems)
    if problems or origin is None or options is None:
        return None, problems
    disabled = sorted(set(submission.disabled_modules))
    return (
        _Prepared(
            connection, origin, mode, ca_pem, fingerprint, options, disabled, new_secrets, stale
        ),
        problems,
    )


def save(
    db: Session,
    settings: Settings,
    policy: AddressPolicy,
    definition: IntegrationDef,
    submitted: Mapping[str, Submission],
    now: datetime,
) -> None:
    """Keeps the settings and secrets of all of an integration's connections, or raises
    ``SettingsError`` (keyed ``<connection>.<field>``) and keeps none. The caller commits."""
    problems = {
        key: "There is no such connection."
        for key in submitted
        if definition.connection(key) is None
    }
    prepared: list[_Prepared] = []
    unused: list[ConnectionDef] = []
    for connection in definition.connections:
        submission = submitted.get(connection.key)
        if submission is None:
            if connection.optional:
                unused.append(connection)
            else:
                problems[connection.key] = "Fill in this connection."
            continue
        ready, found = _prepare(db, policy, definition, connection, submission)
        problems.update({f"{connection.key}.{field}": text for field, text in found.items()})
        if ready:
            prepared.append(ready)
    if problems:
        raise SettingsError(problems)
    saved = rows_for(db, definition.key)
    for item in prepared:
        _write(db, settings, definition, item, saved.get(item.connection.key), now)
    for connection in unused:
        _forget(db, definition, connection)


def _write(
    db: Session,
    settings: Settings,
    definition: IntegrationDef,
    item: _Prepared,
    row: IntegrationConnection | None,
    now: datetime,
) -> None:
    if row is None:
        row = IntegrationConnection(
            integration=definition.key, connection=item.connection.key, created_at=now
        )
        db.add(row)
    # What the last attempt found was about the old settings, so it only stands for as long as
    # they are the ones being saved. A new row has no attempt to keep.
    same = (
        row.last_attempt_at is not None
        and not item.new_secrets
        and not item.stale_secrets
        and (row.base_url, row.tls_mode, row.tls_ca_pem, row.tls_fingerprint)
        == (item.origin.url, item.tls_mode, item.tls_ca_pem, item.tls_fingerprint)
        and row.options == item.options
        and row.disabled_modules == item.disabled_modules
    )
    row.base_url = item.origin.url
    row.tls_mode = item.tls_mode
    row.tls_ca_pem = item.tls_ca_pem
    row.tls_fingerprint = item.tls_fingerprint
    row.options = item.options
    row.disabled_modules = item.disabled_modules
    if not same:
        row.module_states = {}
        row.last_attempt_at = None
        row.last_error = None
    row.updated_at = now
    name = registry.credential_name(definition.key, item.connection.key)
    for field, value in item.new_secrets.items():
        credential_store.store(db, settings, Kind.INTEGRATION, name, field, value, now)
    for field in item.stale_secrets:
        credential_store.remove(db, Kind.INTEGRATION, name, field)


def _forget(db: Session, definition: IntegrationDef, connection: ConnectionDef) -> bool:
    """Forgets one connection's settings and secrets. False if there were none."""
    found = (
        db.connection()
        .execute(
            delete(IntegrationConnection).where(
                IntegrationConnection.integration == definition.key,
                IntegrationConnection.connection == connection.key,
            )
        )
        .rowcount
        > 0
    )
    name = registry.credential_name(definition.key, connection.key)
    for field in secrets_set(db, definition.key, connection.key):
        found |= credential_store.remove(db, Kind.INTEGRATION, name, field)
    # What its collectors had reported goes with it, in the same transaction, so the status page
    # and the dashboard stop counting them as soon as the connection is gone.
    db.connection().execute(
        delete(CollectorHealth).where(
            CollectorHealth.integration == definition.key,
            CollectorHealth.connection == connection.key,
        )
    )
    return found


def disconnect(db: Session, definition: IntegrationDef) -> bool:
    """Forgets an integration's settings and secrets. The API log keeps its entries until they
    are old enough to go. False if there was nothing to forget. The caller commits."""
    found = False
    for connection in definition.connections:
        # Every connection is forgotten, so this must not stop at the first one it finds.
        found |= _forget(db, definition, connection)
    return found


def _open_secrets(
    db: Session,
    settings: Settings,
    definition: IntegrationDef,
    connection: ConnectionDef,
    options: Mapping[str, str | int],
    typed: Mapping[str, str],
) -> dict[str, str]:
    """The secrets a connection needs for the way of signing in that the options choose: the ones
    just typed, and otherwise the ones kept. Raises ``Incomplete`` if one is gone or can't be
    opened."""
    name = registry.credential_name(definition.key, connection.key)
    secrets: dict[str, str] = {}
    for item in registry.active_fields(connection, options):
        if item.kind is not FieldKind.SECRET:
            continue
        if item.key in typed:
            secrets[item.key] = typed[item.key]
            continue
        try:
            value = credential_store.reveal(db, settings, Kind.INTEGRATION, name, item.key)
        except VaultError:
            value = None
        if value is None:
            raise Incomplete(
                f"{connection.label}: {item.label} is missing or can't be opened. Enter it again."
            )
        secrets[item.key] = value
    return secrets


def load_target(
    db: Session,
    settings: Settings,
    definition: IntegrationDef,
    connection: ConnectionDef,
    row: IntegrationConnection,
) -> Target:
    """A saved connection with its secrets opened, for the code that makes requests to it.
    Raises ``Incomplete`` if a secret it needs is gone or can't be opened."""
    secrets = _open_secrets(db, settings, definition, connection, row.options, {})
    return Target(
        integration=definition.key,
        connection=connection.key,
        origin=netguard.parse_origin(row.base_url, allow_http=connection.allow_http),
        tls_mode=row.tls_mode,
        tls_ca_pem=row.tls_ca_pem,
        tls_fingerprint=row.tls_fingerprint,
        options=row.options,
        secrets=secrets,
    )


def draft_target(
    db: Session,
    settings: Settings,
    policy: AddressPolicy,
    definition: IntegrationDef,
    connection: ConnectionDef,
    submission: Submission,
) -> Target:
    """A connection as it is being filled in, before anything is saved, for asking the system
    something (such as which interfaces it has) with the address and sign-in typed so far. A
    secret left blank is the one kept. Raises ``SettingsError``, keyed by field, if what is
    filled in can't be used, and ``Incomplete`` if a kept secret can't be opened."""
    ready, problems = _prepare(db, policy, definition, connection, submission)
    if ready is None:
        raise SettingsError(problems)
    return Target(
        integration=definition.key,
        connection=connection.key,
        origin=ready.origin,
        tls_mode=ready.tls_mode,
        tls_ca_pem=ready.tls_ca_pem,
        tls_fingerprint=ready.tls_fingerprint,
        options=ready.options,
        secrets=_open_secrets(
            db, settings, definition, connection, ready.options, ready.new_secrets
        ),
    )


async def check(target: Target, recorder: Recorder, policy: AddressPolicy) -> Verdict:
    """Tests a connection: what the integration's probe made of it."""
    probe = probes.PROBES[(target.integration, target.connection)]
    async with ApiClient(target, recorder, _reached_with(target, policy)) as client:
        return await probes.run(probe, client, target)


async def look_up(
    lookup: probes.Lookuper, target: Target, recorder: Recorder, policy: AddressPolicy
) -> probes.Lookup:
    """Asks a connection what it lists (a lookup for one of its fields)."""
    async with ApiClient(target, recorder, _reached_with(target, policy)) as client:
        return await probes.look_up(lookup, client, target)


def record_attempt(row: IntegrationConnection, verdict: Verdict, now: datetime) -> list[str]:
    """Keeps how an attempt went. A success clears the last failure's reason. A held connection
    isn't tested now, so its last success stays as it was, but its failure is cleared.

    The first time a connection works, the modules it found installed but not running are switched
    off (the keys of those are returned), so that AresGate doesn't read what isn't there to read.
    That is done once, when connecting: what is switched on or off after that is the owner's."""
    row.last_attempt_at = now
    switched_off: list[str] = []
    if verdict.modules is not None:
        row.module_states = {key: state.value for key, state in verdict.modules.items()}
    if verdict.ok:
        if not verdict.held:
            if verdict.modules is not None and row.last_success_at is None:
                switched_off = sorted(
                    key
                    for key, state in verdict.modules.items()
                    if state is ModuleState.STOPPED and key not in row.disabled_modules
                )
                row.disabled_modules = sorted({*row.disabled_modules, *switched_off})
            row.last_success_at = now
        row.last_error = None
    else:
        row.last_error = audit.clean(verdict.message, 500)
    return switched_off
