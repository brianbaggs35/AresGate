"""Changing the app secret key: everything sealed with the old one is sealed again with the new.

Anything else AresGate seals with ``vault`` has to be added to ``rotate``, or a new key would
leave it unreadable. ``tests/test_rotation.py`` fails when a table gains a sealed column that
isn't here.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config import Settings
from app.security import credential_store, two_factor


@dataclass(frozen=True)
class Rotated:
    credentials: int
    authenticator_keys: int
    recovery_codes_removed: int


def rotate(db: Session, old: Settings, new: Settings) -> Rotated:
    """Opens everything with the old key and seals it again with the new one, in the caller's
    transaction, so it all changes or none of it does. Raises ``VaultError`` naming what can't
    be opened with the old key. The caller commits."""
    return Rotated(
        credentials=credential_store.reseal_all(db, old, new),
        authenticator_keys=two_factor.reseal_keys(db, old, new),
        recovery_codes_removed=two_factor.discard_recovery_codes(db),
    )
