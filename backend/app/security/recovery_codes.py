"""Codes for signing in once when the authenticator app is lost.

An account gets ten when it turns on an authenticator app, shown once. Each works one time. Only
a keyed hash of each is kept (see ``vault.keyed_hash``), so reading the database doesn't give
them away or let anyone work them out by guessing offline, and a wrong guess at the sign-in page
is counted like a wrong password.
"""

import secrets
from uuid import UUID

from app.config import Settings
from app.security import setup_code, vault

COUNT = 10
_GROUPS = 3
_GROUP_LENGTH = 4
LENGTH = _GROUPS * _GROUP_LENGTH
_PURPOSE = "recovery-code"


def generate() -> str:
    """A new code such as ``K7QD-3MWX-9HPA``: 60 bits, too many to guess before the account
    locks."""
    groups = (
        "".join(secrets.choice(setup_code.ALPHABET) for _ in range(_GROUP_LENGTH))
        for _ in range(_GROUPS)
    )
    return "-".join(groups)


def normalize(code: str) -> str:
    """The letters and digits of a code, however it was typed: in lowercase, with spaces, or
    without the dashes."""
    return "".join(character for character in code.upper() if character in setup_code.ALPHABET)


def looks_like_code(code: str) -> bool:
    return len(normalize(code)) == LENGTH


def hash_code(settings: Settings, user_id: UUID, code: str) -> str:
    """What is kept of a code. It includes the account, so two accounts that happen to get the
    same code don't share a hash."""
    return vault.keyed_hash(settings, _PURPOSE, f"{user_id}:{normalize(code)}")
