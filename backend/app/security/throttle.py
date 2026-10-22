"""Slows down guessing, the same way for passwords and for the setup code.

Failed attempts are counted per account and per address. The fifth wrong attempt locks the
account or address for a minute, and every wrong attempt after that doubles the wait, up to an
hour. While it's locked even the right password is refused, so a guesser learns nothing from
how quickly they're let back in. A count is forgotten after a day without a failure.

Locking the account means anyone who can reach the sign-in page can keep its owner out by
guessing wrongly. On a home network that is the lesser risk; the longest wait is an hour.
"""

import hashlib
from datetime import datetime, timedelta
from enum import StrEnum

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import LoginThrottle

ATTEMPTS_BEFORE_LOCKOUT = 5
FIRST_LOCKOUT = timedelta(minutes=1)
LONGEST_LOCKOUT = timedelta(hours=1)
FORGET_AFTER = timedelta(hours=24)
# Doubling a minute six times already passes the hour, so the count needs to go no further.
_MOST_DOUBLINGS = 6


class Scope(StrEnum):
    ACCOUNT = "account"
    ADDRESS = "address"
    SETUP = "setup"


def _row_key(scope: Scope, value: str) -> tuple[str, str]:
    return scope.value, hashlib.sha256(value.encode()).hexdigest()


def remaining_lockout(db: Session, scope: Scope, value: str, now: datetime) -> timedelta | None:
    """How much longer the account or address is locked, or None if it isn't."""
    scope_name, key_hash = _row_key(scope, value)
    locked_until = db.scalar(
        select(LoginThrottle.locked_until).where(
            LoginThrottle.scope == scope_name, LoginThrottle.key_hash == key_hash
        )
    )
    if locked_until is None or locked_until <= now:
        return None
    return locked_until - now


def record_failure(db: Session, scope: Scope, value: str, now: datetime) -> None:
    """Counts a failed attempt, locking after too many. The caller commits."""
    scope_name, key_hash = _row_key(scope, value)
    db.execute(delete(LoginThrottle).where(LoginThrottle.last_failure_at < now - FORGET_AFTER))
    db.execute(
        insert(LoginThrottle)
        .values(scope=scope_name, key_hash=key_hash, failures=0, last_failure_at=now)
        .on_conflict_do_nothing()
    )
    # Locked for update, so two attempts at once are both counted.
    row = db.execute(
        select(LoginThrottle)
        .where(LoginThrottle.scope == scope_name, LoginThrottle.key_hash == key_hash)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one()
    row.failures += 1
    row.last_failure_at = now
    if row.failures >= ATTEMPTS_BEFORE_LOCKOUT:
        doublings = min(row.failures - ATTEMPTS_BEFORE_LOCKOUT, _MOST_DOUBLINGS)
        row.locked_until = now + min(FIRST_LOCKOUT * 2**doublings, LONGEST_LOCKOUT)


def clear(db: Session, scope: Scope, value: str) -> None:
    """Forgets the failures, after a success. The caller commits."""
    scope_name, key_hash = _row_key(scope, value)
    db.execute(
        delete(LoginThrottle).where(
            LoginThrottle.scope == scope_name, LoginThrottle.key_hash == key_hash
        )
    )
