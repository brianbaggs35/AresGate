"""The code that proves whoever sets AresGate up can read its log.

A fresh install has no account, so whoever reaches the page first could claim it. Instead the
container prints a one-time code in its log when it starts, and creating the account needs it.
Only a hash is kept. A new code is made on every start until the account exists, and the code
stops working once it does.
"""

import hashlib
import hmac
import secrets

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_sessionmaker
from app.models import SystemInfo
from app.security.accounts import any_user_exists

KEY = "setup_code_hash"
# No 0, 1, I or O, which are easily mistaken for each other.
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_GROUPS = 3
_GROUP_LENGTH = 4


def generate() -> str:
    """A new code such as ``K7QD-3MWX-9HPA``: 60 bits, too many to guess."""
    groups = (
        "".join(secrets.choice(ALPHABET) for _ in range(_GROUP_LENGTH)) for _ in range(_GROUPS)
    )
    return "-".join(groups)


def _digest(code: str) -> str:
    """Hashes a code however it was typed: in lowercase, with spaces, or without the dashes."""
    letters = "".join(character for character in code.upper() if character in ALPHABET)
    return hashlib.sha256(letters.encode()).hexdigest()


def store(db: Session, code: str) -> None:
    """Makes a code the one that works, replacing any earlier one. The caller commits."""
    row = db.get(SystemInfo, KEY)
    if row is None:
        db.add(SystemInfo(key=KEY, value=_digest(code)))
    else:
        row.value = _digest(code)


def issue(db: Session) -> str:
    """Makes a new code and returns it. The caller commits."""
    code = generate()
    store(db, code)
    return code


def lock(db: Session) -> str | None:
    """The stored hash of the code, with its row locked until the transaction ends so only
    one request can use the code. None if there is no code."""
    return db.scalar(
        select(SystemInfo.value)
        .where(SystemInfo.key == KEY)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def matches(stored_hash: str, code: str) -> bool:
    return hmac.compare_digest(stored_hash, _digest(code))


def consume(db: Session) -> None:
    """Removes the code once it has been used. The caller commits."""
    db.execute(delete(SystemInfo).where(SystemInfo.key == KEY))


def banner(code: str, origin: str) -> str:
    rule = "=" * 64
    return "\n".join(
        [
            rule,
            " AresGate is ready to be set up.",
            f" Open {origin} and enter this setup code:",
            "",
            f"     {code}",
            "",
            " The code changes each time AresGate starts, and stops working once",
            " the account exists.",
            rule,
        ]
    )


def announce() -> None:
    """Prints a new setup code in the log if the install has no account yet. The container
    runs this after its migrations, before the API starts."""
    with get_sessionmaker()() as db:
        if any_user_exists(db):
            return
        code = issue(db)
        db.commit()
    print(banner(code, get_settings().public_origin), flush=True)
