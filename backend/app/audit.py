"""The audit log: an append-only record of what happened to the install's security. Anything
that signs someone in, changes how they can, or changes what AresGate holds adds an event here,
and the web app lists them."""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Connection, delete, select, text
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import AuditEvent, utcnow

DEFAULT_PAGE = 50
MAX_PAGE = 200

Detail = Mapping[str, str | int | bool]

# Control characters, which would let a client's own words forge a line in the log or break it,
# and the Unicode line and paragraph separators. A NUL is also more than the database accepts.
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]")


class Outcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"


class Action(StrEnum):
    """What can happen. A feature that adds events adds its actions here."""

    SETUP_COMPLETED = "setup.completed"
    SETUP_CODE_REJECTED = "setup.code_rejected"
    LOGIN_SUCCEEDED = "auth.login_succeeded"
    LOGIN_FAILED = "auth.login_failed"
    LOGOUT = "auth.logout"
    TWO_FACTOR_ENABLED = "auth.two_factor_enabled"
    TWO_FACTOR_DISABLED = "auth.two_factor_disabled"
    TWO_FACTOR_FAILED = "auth.two_factor_failed"
    RECOVERY_CODES_CREATED = "auth.recovery_codes_created"
    PASSKEY_ADDED = "auth.passkey_added"
    PASSKEY_REMOVED = "auth.passkey_removed"
    CREDENTIAL_STORED = "credential.stored"
    CREDENTIAL_DELETED = "credential.deleted"
    KEY_ROTATED = "system.secret_key_rotated"
    EVENTS_PURGED = "audit.events_purged"


def clean(value: str | None, limit: int) -> str | None:
    """Text from a client, made safe to keep: control characters become spaces, and it's cut to
    fit. Nothing left means nothing to keep."""
    if value is None:
        return None
    return _CONTROL.sub(" ", value).strip()[:limit] or None


def record(
    db: Session,
    action: Action,
    outcome: Outcome,
    *,
    user_id: UUID | None = None,
    username: str | None = None,
    address: str | None = None,
    user_agent: str | None = None,
    detail: Detail | None = None,
    now: datetime | None = None,
) -> AuditEvent:
    """Adds an event. The caller commits, so it's kept or dropped together with the change it
    describes. ``detail`` is for a few facts, and never for a secret."""
    event = AuditEvent(
        occurred_at=now or utcnow(),
        action=action.value,
        outcome=outcome.value,
        user_id=user_id,
        username=clean(username, 64),
        client_address=clean(address, 64),
        user_agent=clean(user_agent, 256),
        detail=dict(detail) if detail else None,
    )
    db.add(event)
    return event


@dataclass(frozen=True)
class Page:
    events: list[AuditEvent]
    # Pass this as ``before`` to get the page of older events that follows, if there is one.
    next_before: int | None


def list_events(
    db: Session,
    *,
    actions: Sequence[str] = (),
    outcome: Outcome | None = None,
    username: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    before: int | None = None,
    limit: int = DEFAULT_PAGE,
) -> Page:
    """Events, newest first. Each filter narrows the list, and ``before`` pages through it."""
    query = select(AuditEvent).order_by(AuditEvent.id.desc()).limit(limit + 1)
    if actions:
        query = query.where(AuditEvent.action.in_(actions))
    if outcome is not None:
        query = query.where(AuditEvent.outcome == outcome.value)
    if username is not None:
        query = query.where(AuditEvent.username == username)
    if since is not None:
        query = query.where(AuditEvent.occurred_at >= since)
    if until is not None:
        query = query.where(AuditEvent.occurred_at < until)
    if before is not None:
        query = query.where(AuditEvent.id < before)
    rows = list(db.scalars(query))
    if len(rows) <= limit:
        return Page(rows, None)
    # The extra row only shows there's more; the next page starts below the last one kept.
    kept = rows[:limit]
    return Page(kept, kept[-1].id)


def allow_deletes(db: Session | Connection) -> None:
    """Lets the rest of this transaction delete events, which the database refuses otherwise.
    Only the retention purge and the tests' cleanup do."""
    db.execute(text("SELECT set_config('aresgate.audit_purge', 'on', true)"))


def purge_expired(db: Session, settings: Settings, now: datetime) -> int:
    """Deletes events older than the retention period, and records that it did. Commits."""
    cutoff = now - timedelta(days=settings.audit_retention_days)
    allow_deletes(db)
    deleted = (
        db.connection().execute(delete(AuditEvent).where(AuditEvent.occurred_at < cutoff)).rowcount
    )
    if deleted:
        record(
            db,
            Action.EVENTS_PURGED,
            Outcome.SUCCESS,
            detail={"deleted": deleted, "older_than_days": settings.audit_retention_days},
            now=now,
        )
    db.commit()
    return deleted
