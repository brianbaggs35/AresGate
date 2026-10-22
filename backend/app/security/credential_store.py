"""The credentials AresGate keeps for the things it talks to, such as a firewall's API key or an
AI provider's.

Each is sealed with the app secret key (see ``vault``) before it reaches the database, so a copy
of the database on its own reveals none of them. Integrations and AI providers each have a key
of their own, and each secret names the row it belongs to, so one can't be copied onto another
row and opened as something else.

Secrets only go in. The API stores, replaces and deletes them and says which are set, but no
route returns one: only the code that talks to the integration calls ``reveal``.
"""

import re
from datetime import datetime
from enum import StrEnum

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import StoredCredential
from app.security import vault
from app.security.vault import VaultError

# Lowercase letters, digits, dashes and underscores. Nothing here can contain the "/" that
# separates the parts of what a secret belongs to.
NAME_PATTERN = r"^[a-z0-9][a-z0-9_-]{0,62}$"
_NAME = re.compile(NAME_PATTERN)


class Kind(StrEnum):
    INTEGRATION = "integration"
    AI_PROVIDER = "ai_provider"


_PURPOSES = {
    Kind.INTEGRATION: "integration-credential",
    Kind.AI_PROVIDER: "ai-provider-credential",
}


class InvalidName(ValueError):
    """A name or field that isn't a short lowercase word."""


def _belongs_to(kind: Kind, name: str, field: str) -> str:
    return f"{kind.value}/{name}/{field}"


def _check(name: str, field: str) -> None:
    if not (_NAME.fullmatch(name) and _NAME.fullmatch(field)):
        raise InvalidName(f"{name!r} and {field!r} must be lowercase words (a-z, 0-9, - and _).")


def _find(
    db: Session, kind: Kind, name: str, field: str, *, lock: bool = False
) -> StoredCredential | None:
    query = select(StoredCredential).where(
        StoredCredential.kind == kind.value,
        StoredCredential.name == name,
        StoredCredential.field == field,
    )
    return db.execute(query.with_for_update() if lock else query).scalar_one_or_none()


def store(
    db: Session, settings: Settings, kind: Kind, name: str, field: str, value: str, now: datetime
) -> StoredCredential:
    """Keeps a secret, replacing the one already there. The caller commits."""
    _check(name, field)
    sealed = vault.seal(settings, _PURPOSES[kind], value.encode(), _belongs_to(kind, name, field))
    row = _find(db, kind, name, field, lock=True)
    if row is None:
        row = StoredCredential(
            kind=kind.value, name=name, field=field, value_sealed=sealed, created_at=now
        )
        db.add(row)
    else:
        row.value_sealed = sealed
    row.updated_at = now
    return row


def reveal(db: Session, settings: Settings, kind: Kind, name: str, field: str) -> str | None:
    """A secret in the clear, or None if none is kept. For the code that connects to the
    integration, which has to present it, and never for anything that answers a request."""
    _check(name, field)
    row = _find(db, kind, name, field)
    if row is None:
        return None
    return vault.unseal(
        settings, _PURPOSES[kind], row.value_sealed, _belongs_to(kind, name, field)
    ).decode()


def entries(db: Session) -> list[StoredCredential]:
    """Which secrets are kept, without the secrets: every row, by kind, name and field."""
    return list(
        db.scalars(
            select(StoredCredential).order_by(
                StoredCredential.kind, StoredCredential.name, StoredCredential.field
            )
        )
    )


def remove(db: Session, kind: Kind, name: str, field: str) -> bool:
    """Forgets a secret. False if none was kept. The caller commits."""
    _check(name, field)
    removed = db.connection().execute(
        delete(StoredCredential).where(
            StoredCredential.kind == kind.value,
            StoredCredential.name == name,
            StoredCredential.field == field,
        )
    )
    return removed.rowcount > 0


def reseal_all(db: Session, old: Settings, new: Settings) -> int:
    """Seals every secret again with a new app secret key, and returns how many there were.
    Raises ``VaultError`` naming the one that can't be opened with the old key, which leaves
    the others as they were. The caller commits."""
    rows = entries(db)
    for row in rows:
        kind = Kind(row.kind)
        belongs_to = _belongs_to(kind, row.name, row.field)
        try:
            value = vault.unseal(old, _PURPOSES[kind], row.value_sealed, belongs_to)
        except VaultError as error:
            raise VaultError(f"The {row.kind} secret {row.name}/{row.field}: {error}") from error
        row.value_sealed = vault.seal(new, _PURPOSES[kind], value, belongs_to)
    return len(rows)
