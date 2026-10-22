from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import User, UserSession
from app.security import sessions

NOW = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)


def count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(UserSession)) or 0


def start(db: Session, user: User, settings: Settings) -> tuple[UserSession, str]:
    row, token = sessions.start(db, user, settings, NOW)
    db.commit()
    return row, token


def test_a_session_is_found_by_its_token(
    session: Session, settings: Settings, account: User
) -> None:
    row, token = start(session, account, settings)

    assert sessions.find(session, token, settings, NOW) == row
    assert row.user == account


def test_the_token_is_not_kept(session: Session, settings: Settings, account: User) -> None:
    row, token = start(session, account, settings)

    assert token not in (row.token_hash, row.csrf_token)
    assert len(row.token_hash) == 64
    assert row.csrf_token != token


def test_every_session_has_tokens_of_its_own(
    session: Session, settings: Settings, account: User
) -> None:
    first, first_token = start(session, account, settings)
    second, second_token = start(session, account, settings)

    assert first_token != second_token
    assert first.csrf_token != second.csrf_token


def test_a_made_up_token_finds_nothing(session: Session, settings: Settings, account: User) -> None:
    start(session, account, settings)

    assert sessions.find(session, "not-a-token", settings, NOW) is None


def test_a_session_ends_after_sitting_idle(
    session: Session, settings: Settings, account: User
) -> None:
    _, token = start(session, account, settings)
    idle = timedelta(minutes=settings.session_idle_minutes)

    assert sessions.find(session, token, settings, NOW + idle - timedelta(seconds=1))
    assert sessions.find(session, token, settings, NOW + 2 * idle) is None
    assert count(session) == 0


def test_using_a_session_keeps_it_going(
    session: Session, settings: Settings, account: User
) -> None:
    _, token = start(session, account, settings)
    idle = timedelta(minutes=settings.session_idle_minutes)

    soon = NOW + idle - timedelta(seconds=1)
    assert sessions.find(session, token, settings, soon)

    assert sessions.find(session, token, settings, soon + idle - timedelta(seconds=1))


def test_a_session_ends_at_its_absolute_limit_however_busy(
    session: Session, settings: Settings, account: User
) -> None:
    row, token = start(session, account, settings)
    limit = NOW + timedelta(hours=settings.session_max_hours)
    # Active up to a moment before the limit.
    row.last_seen_at = limit - timedelta(seconds=30)
    session.commit()

    assert sessions.find(session, token, settings, limit - timedelta(seconds=1))
    assert sessions.find(session, token, settings, limit) is None


def test_using_a_session_is_noted_only_once_a_minute(
    session: Session, settings: Settings, account: User
) -> None:
    row, token = start(session, account, settings)

    sessions.find(session, token, settings, NOW + sessions.TOUCH_EVERY - timedelta(seconds=1))
    assert row.last_seen_at == NOW

    later = NOW + sessions.TOUCH_EVERY
    sessions.find(session, token, settings, later)
    assert row.last_seen_at == later


def test_expiry_is_the_earlier_of_the_idle_and_absolute_limits(
    session: Session, settings: Settings, account: User
) -> None:
    row, _ = start(session, account, settings)
    assert sessions.expires_at(row, settings) == NOW + timedelta(
        minutes=settings.session_idle_minutes
    )

    row.last_seen_at = NOW + timedelta(hours=settings.session_max_hours)
    assert sessions.expires_at(row, settings) == row.expires_at


def test_a_session_can_be_ended(session: Session, settings: Settings, account: User) -> None:
    row, token = start(session, account, settings)

    sessions.end(session, row)

    assert sessions.find(session, token, settings, NOW) is None
    assert count(session) == 0


def test_ended_sessions_are_purged_and_live_ones_kept(
    session: Session, settings: Settings, account: User
) -> None:
    idle, expired, _ = (start(session, account, settings)[0] for _ in range(3))
    idle.last_seen_at = NOW - timedelta(minutes=settings.session_idle_minutes)
    expired.expires_at = NOW
    session.commit()

    sessions.purge_ended(session, settings, NOW)
    session.commit()

    assert count(session) == 1


def test_deleting_the_account_ends_its_sessions(
    session: Session, settings: Settings, account: User
) -> None:
    start(session, account, settings)

    session.delete(account)
    session.commit()

    assert count(session) == 0
