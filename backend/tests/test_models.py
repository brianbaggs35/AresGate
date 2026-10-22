from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.models import SystemInfo, UTCDateTime, utcnow


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
