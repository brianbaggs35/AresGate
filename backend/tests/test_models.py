from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import LoginThrottle, SystemInfo, User, UserSession, UTCDateTime, utcnow


def test_system_info_round_trips(session: Session) -> None:
    session.add(SystemInfo(key="installed", value="yes"))
    session.commit()
    row = session.get(SystemInfo, "installed")
    assert row is not None
    assert row.value == "yes"
    assert row.updated_at.tzinfo is UTC


def test_timestamps_come_back_in_utc(session: Session) -> None:
    halifax = timezone(timedelta(hours=-3))
    when = datetime(2026, 10, 22, 2, 30, tzinfo=halifax)
    session.add(SystemInfo(key="when", value="x", updated_at=when))
    session.commit()
    session.expire_all()
    row = session.get(SystemInfo, "when")
    assert row is not None
    assert row.updated_at == when
    assert row.updated_at.utcoffset() == timedelta(0)


def test_naive_timestamps_are_refused() -> None:
    column = UTCDateTime()
    naive = datetime(2026, 10, 22)  # no timezone, on purpose
    with pytest.raises(ValueError, match="timezone-aware"):
        column.process_bind_param(naive, None)  # type: ignore[arg-type]


def test_nothing_in_nothing_out() -> None:
    column = UTCDateTime()
    assert column.process_bind_param(None, None) is None  # type: ignore[arg-type]
    assert column.process_result_value(None, None) is None  # type: ignore[arg-type]


def test_utcnow_is_aware() -> None:
    assert utcnow().tzinfo is UTC


def test_an_account_and_its_session_round_trip(session: Session) -> None:
    user = User(username="brian", password_hash="$argon2id$x")
    session.add(user)
    session.flush()
    session.add(
        UserSession(
            token_hash="a" * 64,
            user=user,
            csrf_token="csrf",
            expires_at=utcnow() + timedelta(hours=1),
        )
    )
    session.commit()
    session.expire_all()

    stored = session.scalars(select(UserSession)).one()
    assert stored.user.username == "brian"
    assert stored.user.created_at.tzinfo is UTC
    assert stored.last_seen_at.tzinfo is UTC


def test_usernames_are_unique(session: Session) -> None:
    session.add(User(username="brian", password_hash="x"))
    session.commit()
    session.add(User(username="brian", password_hash="y"))

    with pytest.raises(IntegrityError):
        session.flush()


def test_a_failure_count_starts_unlocked(session: Session) -> None:
    session.add(LoginThrottle(scope="account", key_hash="k" * 64, last_failure_at=utcnow()))
    session.commit()

    row = session.scalars(select(LoginThrottle)).one()
    assert row.failures == 0
    assert row.locked_until is None
