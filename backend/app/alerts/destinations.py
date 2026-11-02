"""The places alerts are sent: keeping them, opening their addresses and recording how sending to
them went. A destination's address is a secret, sealed in the credential store (see
``app.security.credential_store``) under ``destination-<id>``; the row in the database holds only
what can be shown without it."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.alerts import discord
from app.alerts.discord import InvalidWebhook, Sent, Webhook
from app.config import Settings
from app.integrations.service import Status
from app.models import AlertDestination
from app.security import credential_store
from app.security.credential_store import Kind
from app.security.vault import VaultError

# Enough for every channel a home needs, and few enough that the list stays one to read.
MAX_DESTINATIONS = 10
FIELD = "webhook_url"


class Unusable(Exception):
    """The address of a destination is gone or can't be opened, so nothing can be sent to it. The
    message says what to do."""


class NameTaken(ValueError):
    """Another destination has the name."""


def _credential(destination_id: int) -> str:
    return f"destination-{destination_id}"


def listing(db: Session) -> list[AlertDestination]:
    """Every destination, in the order they were added."""
    return list(db.scalars(select(AlertDestination).order_by(AlertDestination.id)))


def count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(AlertDestination)) or 0


def with_address(db: Session) -> set[int]:
    """The destinations whose address is kept. (A destination without one is one whose secret was
    deleted behind its back, which the page says.)"""
    names = {row.name for row in credential_store.entries(db) if row.kind == Kind.DESTINATION.value}
    return {destination.id for destination in listing(db) if _credential(destination.id) in names}


def check_name(db: Session, name: str, *, except_id: int | None = None) -> None:
    """Raises ``NameTaken`` if another destination has the name, whatever its letter case."""
    query = select(AlertDestination.id).where(func.lower(AlertDestination.name) == name.lower())
    if except_id is not None:
        query = query.where(AlertDestination.id != except_id)
    if db.scalar(query) is not None:
        raise NameTaken(f"There's already a destination called {name}.")


def create(
    db: Session, settings: Settings, name: str, address: str, now: datetime
) -> AlertDestination:
    """Keeps a new destination and seals its address. Raises ``InvalidWebhook`` or ``NameTaken``.
    The caller commits."""
    webhook = discord.parse(address)
    check_name(db, name)
    row = AlertDestination(
        kind="discord", name=name, enabled=True, hint=webhook.hint, created_at=now, updated_at=now
    )
    db.add(row)
    db.flush()
    credential_store.store(
        db, settings, Kind.DESTINATION, _credential(row.id), FIELD, webhook.url, now
    )
    return row


def replace_address(
    db: Session, settings: Settings, row: AlertDestination, address: str, now: datetime
) -> None:
    """Seals a new address in place of the old, and forgets how sending to the old one went.
    Raises ``InvalidWebhook``. The caller commits."""
    webhook = discord.parse(address)
    credential_store.store(
        db, settings, Kind.DESTINATION, _credential(row.id), FIELD, webhook.url, now
    )
    row.hint = webhook.hint
    row.updated_at = now
    row.last_attempt_at = None
    row.last_success_at = None
    row.last_error = None


def forget(db: Session, row: AlertDestination) -> None:
    """Deletes a destination and its address. The caller commits."""
    credential_store.remove(db, Kind.DESTINATION, _credential(row.id), FIELD)
    db.delete(row)


def open_webhook(db: Session, settings: Settings, row: AlertDestination) -> Webhook:
    """The destination's address in the clear, for the code that sends and nothing else. The
    address is checked again here, because the secret store takes anything. Raises ``Unusable``."""
    try:
        address = credential_store.reveal(
            db, settings, Kind.DESTINATION, _credential(row.id), FIELD
        )
    except VaultError:
        address = None
    if address is None:
        raise Unusable("The webhook address is missing or can't be opened. Enter it again.")
    try:
        return discord.parse(address)
    except InvalidWebhook:
        raise Unusable(
            "The saved webhook address isn't a Discord address any more. Enter it again."
        ) from None


def status_of(row: AlertDestination, *, has_address: bool) -> Status:
    """What the page shows for it: no address, not tried yet, working, or the last try failed."""
    if not has_address:
        return Status.NOT_CONNECTED
    if row.last_attempt_at is None:
        return Status.UNTESTED
    return Status.PROBLEM if row.last_error else Status.CONNECTED


def record_attempt(row: AlertDestination, sent: Sent | str, now: datetime) -> None:
    """Keeps how the last message went: what Discord answered, or why it couldn't be sent."""
    row.last_attempt_at = now
    if isinstance(sent, str):
        row.last_error = sent[:500]
    elif sent.ok:
        row.last_success_at = now
        row.last_error = None
    else:
        row.last_error = (sent.problem or "The message didn't get through.")[:500]
