"""The places alerts are sent: keeping them, opening their addresses and recording how sending to
them went. A destination's address is a secret, sealed in the credential store (see
``app.security.credential_store``) under ``destination-<id>``; the row in the database holds only
what can be shown without it."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.alerts import discord, mail
from app.alerts.discord import InvalidWebhook, Sent, Webhook
from app.config import Settings
from app.integrations.service import Status
from app.models import AlertDestination, SmtpSettings
from app.security import credential_store
from app.security.credential_store import Kind
from app.security.vault import VaultError

# Enough for every channel a home needs, and few enough that the list stays one to read.
MAX_DESTINATIONS = 10
FIELD = "webhook_url"
# Where the mail server's password is kept in the credential store.
SMTP_CREDENTIAL = "server"
SMTP_FIELD = "password"


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
    """The destinations that can be sent to: a Discord one whose webhook address is kept (one
    without is one whose secret was deleted behind its back, which the page says), and an email
    one while the mail server is set up."""
    names = {row.name for row in credential_store.entries(db) if row.kind == Kind.DESTINATION.value}
    mailing = smtp(db) is not None
    return {
        destination.id
        for destination in listing(db)
        if (destination.kind == "email" and mailing) or _credential(destination.id) in names
    }


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
        kind="discord",
        name=name,
        enabled=True,
        # What it is for: a message means that a real attack is going on. Looser rules are a
        # choice of the owner's.
        mode="threats",
        hint=webhook.hint,
        created_at=now,
        updated_at=now,
        listening_since=now,
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
    forget_attempts(row)


def forget(db: Session, row: AlertDestination) -> None:
    """Deletes a destination and its address. The caller commits."""
    credential_store.remove(db, Kind.DESTINATION, _credential(row.id), FIELD)
    db.delete(row)


def create_email(db: Session, name: str, recipient: str, now: datetime) -> AlertDestination:
    """Keeps a new email destination. Raises ``mail.InvalidSettings`` or ``NameTaken``. The caller
    commits."""
    address = mail.check_address(recipient, "recipient")
    check_name(db, name)
    row = AlertDestination(
        kind="email",
        name=name,
        enabled=True,
        mode="threats",
        recipient=address,
        created_at=now,
        updated_at=now,
        listening_since=now,
    )
    db.add(row)
    db.flush()
    return row


def replace_recipient(row: AlertDestination, recipient: str, now: datetime) -> None:
    """Sends an email destination to another address, and forgets how sending to the old one went.
    Raises ``mail.InvalidSettings``. The caller commits."""
    row.recipient = mail.check_address(recipient, "recipient")
    row.updated_at = now
    forget_attempts(row)


def forget_attempts(row: AlertDestination) -> None:
    """Forgets how sending went, and lets a destination that was refused be tried again."""
    row.last_attempt_at = None
    row.last_success_at = None
    row.last_error = None
    row.refused = False


def smtp(db: Session) -> SmtpSettings | None:
    """The mail server that email destinations send through, or None until it is set up."""
    return db.get(SmtpSettings, 1)


def smtp_password_kept(db: Session) -> bool:
    return any(
        row.kind == Kind.SMTP.value and row.name == SMTP_CREDENTIAL
        for row in credential_store.entries(db)
    )


def save_smtp(
    db: Session,
    settings: Settings,
    *,
    host: str,
    port: int,
    security: str,
    username: str | None,
    sender: str,
    password: str | None,
    clear_password: bool,
    now: datetime,
) -> SmtpSettings:
    """Keeps the mail server's settings. A password given is sealed in place of the one kept; with
    none given the kept one stays, unless ``clear_password`` says to forget it. Every email
    destination is let try again, since what stopped it may have been these settings. Raises
    ``mail.InvalidSettings``. The caller commits."""
    given = mail.check_password(password) if password else None
    keeping = (smtp_password_kept(db) and not clear_password) or given is not None
    host, username, sender = mail.check_server(
        host, port, security, username, sender, has_password=keeping
    )
    row = smtp(db)
    if row is None:
        row = SmtpSettings(
            id=1, host=host, port=port, security=security, sender=sender, updated_at=now
        )
        db.add(row)
    row.host, row.port, row.security, row.username, row.sender = (
        host,
        port,
        security,
        username,
        sender,
    )
    row.updated_at = now
    if given is not None:
        credential_store.store(db, settings, Kind.SMTP, SMTP_CREDENTIAL, SMTP_FIELD, given, now)
    elif not keeping:
        credential_store.remove(db, Kind.SMTP, SMTP_CREDENTIAL, SMTP_FIELD)
    for destination in listing(db):
        if destination.kind == "email":
            forget_attempts(destination)
    db.flush()
    return row


def forget_smtp(db: Session) -> bool:
    """Forgets the mail server's settings and password. Email destinations stay, and wait for a
    server. False if none was set. The caller commits."""
    row = smtp(db)
    credential_store.remove(db, Kind.SMTP, SMTP_CREDENTIAL, SMTP_FIELD)
    if row is None:
        return False
    db.delete(row)
    return True


def open_mailbox(db: Session, settings: Settings, row: AlertDestination) -> mail.Mailbox:
    """Where an email destination's messages go, with the mail server's password in the clear, for
    the code that sends and nothing else. Raises ``Unusable``."""
    server = smtp(db)
    if server is None or not row.recipient:
        raise Unusable("The mail server isn't set up. Enter its settings under the destinations.")
    try:
        password = credential_store.reveal(db, settings, Kind.SMTP, SMTP_CREDENTIAL, SMTP_FIELD)
    except VaultError:
        raise Unusable(
            "The mail server's password can't be opened. Enter it again in the mail server's "
            "settings."
        ) from None
    return mail.Mailbox(
        mail.Server(
            host=server.host,
            port=server.port,
            security=server.security,
            username=server.username,
            password=password,
            sender=server.sender,
        ),
        row.recipient,
    )


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
        row.refused = False
    else:
        row.last_error = (sent.problem or "The message didn't get through.")[:500]
