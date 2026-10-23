"""Signed-in browsers.

The cookie holds a random token that means nothing by itself; the database keeps only its
hash, so reading the database doesn't let anyone sign in. A sign-in ends after it has sat idle
for ``session_idle_minutes``, or ``session_max_hours`` after it began, whichever comes first.
"""

import hashlib
import secrets
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.audit import clean
from app.config import Settings
from app.models import User, UserSession

COOKIE_NAME = "__Host-aresgate_session"
# Seeing a sign-in again only updates its record this often, not on every request.
TOUCH_EVERY = timedelta(seconds=60)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def expires_at(row: UserSession, settings: Settings) -> datetime:
    """When the sign-in ends if nothing more happens: the idle limit or the absolute one."""
    idle_limit = row.last_seen_at + timedelta(minutes=settings.session_idle_minutes)
    return min(idle_limit, row.expires_at)


def start(
    db: Session,
    user: User,
    settings: Settings,
    now: datetime,
    *,
    address: str | None = None,
    user_agent: str | None = None,
) -> tuple[UserSession, str]:
    """Signs the user in. Returns the session and the token for its cookie, which is the only
    time the token exists. The caller commits."""
    token = secrets.token_urlsafe(32)
    row = UserSession(
        token_hash=_hash(token),
        user=user,
        csrf_token=secrets.token_urlsafe(32),
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(hours=settings.session_max_hours),
        address=clean(address, 64),
        user_agent=clean(user_agent, 256),
    )
    db.add(row)
    return row, token


def find(db: Session, token: str, settings: Settings, now: datetime) -> UserSession | None:
    """The live session a cookie's token belongs to, noting that it was just used. An ended
    one is removed."""
    row = db.scalar(select(UserSession).where(UserSession.token_hash == _hash(token)))
    if row is None:
        return None
    if now >= expires_at(row, settings):
        db.delete(row)
        db.commit()
        return None
    if now - row.last_seen_at >= TOUCH_EVERY:
        row.last_seen_at = now
        db.commit()
    return row


def end(db: Session, row: UserSession) -> None:
    db.delete(row)
    db.commit()


def live_for(db: Session, user: User, settings: Settings, now: datetime) -> list[UserSession]:
    """The user's sign-ins that are still good, the one used most recently first."""
    idle_limit = now - timedelta(minutes=settings.session_idle_minutes)
    return list(
        db.scalars(
            select(UserSession)
            .where(
                UserSession.user_id == user.id,
                UserSession.expires_at > now,
                UserSession.last_seen_at > idle_limit,
            )
            .order_by(UserSession.last_seen_at.desc())
        )
    )


def end_one(db: Session, user: User, session_id: UUID) -> UserSession | None:
    """Ends one of the user's sign-ins, or returns None when there's no such one. The caller
    commits."""
    row = db.scalar(
        select(UserSession).where(UserSession.id == session_id, UserSession.user_id == user.id)
    )
    if row is not None:
        db.delete(row)
    return row


def end_all_but(db: Session, user: User, keep: UserSession) -> int:
    """Ends every one of the user's sign-ins except one, and says how many there were. The
    caller commits."""
    return (
        db.connection()
        .execute(
            delete(UserSession).where(UserSession.user_id == user.id, UserSession.id != keep.id)
        )
        .rowcount
    )


def purge_ended(db: Session, settings: Settings, now: datetime) -> None:
    """Removes sign-ins nobody came back to. The caller commits."""
    idle_limit = now - timedelta(minutes=settings.session_idle_minutes)
    db.execute(
        delete(UserSession).where(
            or_(UserSession.expires_at <= now, UserSession.last_seen_at <= idle_limit)
        )
    )
