from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.models import LoginThrottle
from app.security import throttle
from app.security.throttle import Scope

NOW = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
WHO = "brian"


def fail(db: Session, times: int, *, scope: Scope = Scope.ACCOUNT, now: datetime = NOW) -> None:
    for _ in range(times):
        throttle.record_failure(db, scope, WHO, now)
    db.commit()


def test_nothing_is_locked_at_first(session: Session) -> None:
    assert throttle.remaining_lockout(session, Scope.ACCOUNT, WHO, NOW) is None


def test_the_first_failures_are_free(session: Session) -> None:
    fail(session, throttle.ATTEMPTS_BEFORE_LOCKOUT - 1)

    assert throttle.remaining_lockout(session, Scope.ACCOUNT, WHO, NOW) is None


def test_the_fifth_failure_locks_for_a_minute(session: Session) -> None:
    fail(session, throttle.ATTEMPTS_BEFORE_LOCKOUT)

    assert throttle.remaining_lockout(session, Scope.ACCOUNT, WHO, NOW) == timedelta(minutes=1)


def test_the_lockout_ends(session: Session) -> None:
    fail(session, throttle.ATTEMPTS_BEFORE_LOCKOUT)

    later = NOW + timedelta(minutes=1)
    assert throttle.remaining_lockout(session, Scope.ACCOUNT, WHO, later) is None
    assert throttle.remaining_lockout(session, Scope.ACCOUNT, WHO, later - timedelta(seconds=1))


def test_each_failure_after_that_doubles_the_wait(session: Session) -> None:
    waits: list[int] = []
    for _ in range(4):
        fail(session, 1 if waits else throttle.ATTEMPTS_BEFORE_LOCKOUT)
        remaining = throttle.remaining_lockout(session, Scope.ACCOUNT, WHO, NOW)
        assert remaining is not None
        waits.append(int(remaining.total_seconds() // 60))

    assert waits == [1, 2, 4, 8]


def test_the_wait_stops_growing_at_an_hour(session: Session) -> None:
    fail(session, 40)

    assert throttle.remaining_lockout(session, Scope.ACCOUNT, WHO, NOW) == timedelta(hours=1)


def test_scopes_and_keys_are_counted_apart(session: Session) -> None:
    fail(session, throttle.ATTEMPTS_BEFORE_LOCKOUT)

    assert throttle.remaining_lockout(session, Scope.ADDRESS, WHO, NOW) is None
    assert throttle.remaining_lockout(session, Scope.ACCOUNT, "someone-else", NOW) is None


def test_neither_the_username_nor_the_address_is_kept(session: Session) -> None:
    fail(session, 1, scope=Scope.ADDRESS)

    row = session.scalars(select(LoginThrottle)).one()
    assert WHO not in (row.scope, row.key_hash)
    assert len(row.key_hash) == 64


def test_a_success_forgets_the_failures(session: Session) -> None:
    fail(session, throttle.ATTEMPTS_BEFORE_LOCKOUT)

    throttle.clear(session, Scope.ACCOUNT, WHO)
    session.commit()

    assert throttle.remaining_lockout(session, Scope.ACCOUNT, WHO, NOW) is None
    assert session.scalar(select(func.count()).select_from(LoginThrottle)) == 0


def test_clearing_what_was_never_counted_is_fine(session: Session) -> None:
    throttle.clear(session, Scope.SETUP, "203.0.113.9")


def test_failures_are_forgotten_after_a_day(session: Session) -> None:
    fail(session, throttle.ATTEMPTS_BEFORE_LOCKOUT - 1)

    fail(session, 1, now=NOW + throttle.FORGET_AFTER + timedelta(seconds=1))

    row = session.scalars(select(LoginThrottle)).one()
    assert row.failures == 1
    assert row.locked_until is None


def test_old_counts_of_other_keys_are_cleared_out(session: Session) -> None:
    throttle.record_failure(session, Scope.ADDRESS, "198.51.100.7", NOW)
    session.commit()

    fail(session, 1, now=NOW + throttle.FORGET_AFTER + timedelta(seconds=1))

    keys = {row.scope for row in session.scalars(select(LoginThrottle))}
    assert keys == {Scope.ACCOUNT.value}


@pytest.mark.parametrize("scope", list(Scope))
def test_every_scope_locks_the_same_way(session: Session, scope: Scope) -> None:
    fail(session, throttle.ATTEMPTS_BEFORE_LOCKOUT, scope=scope)

    assert throttle.remaining_lockout(session, scope, WHO, NOW) == timedelta(minutes=1)


def test_attempts_at_the_same_moment_are_all_counted(engine: Engine, session: Session) -> None:
    attempts = 8
    start = Barrier(attempts)

    def guess(_: int) -> None:
        with sessionmaker(bind=engine)() as db:
            start.wait()
            throttle.record_failure(db, Scope.ACCOUNT, WHO, NOW)
            db.commit()

    with ThreadPoolExecutor(max_workers=attempts) as pool:
        list(pool.map(guess, range(attempts)))

    row = session.scalars(select(LoginThrottle)).one()
    assert row.failures == attempts
    assert throttle.remaining_lockout(session, Scope.ACCOUNT, WHO, NOW) is not None
