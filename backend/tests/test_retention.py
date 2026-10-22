import asyncio
import logging
from collections.abc import Callable, Iterator
from contextlib import suppress
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app import audit, main, retention
from app.audit import Action, Outcome
from app.config import Settings
from app.models import AuditEvent


@pytest.fixture
def new_session(engine: Engine) -> Iterator[Callable[[], Session]]:
    yield sessionmaker(bind=engine, expire_on_commit=False)


def add_event(db: Session, age: timedelta) -> None:
    audit.record(db, Action.LOGOUT, Outcome.SUCCESS, now=datetime.now(UTC) - age)
    db.commit()


def remaining(db: Session) -> int:
    db.expire_all()
    return db.scalar(select(func.count()).select_from(AuditEvent)) or 0


def test_purging_deletes_what_is_past_the_retention_period(
    session: Session, settings: Settings, new_session: Callable[[], Session]
) -> None:
    add_event(session, timedelta(days=settings.audit_retention_days + 1))
    add_event(session, timedelta(days=1))

    assert retention.purge_once(settings, new_session) == 1

    # The recent event stays, and the purge itself is in the log.
    assert remaining(session) == 2


class FakePurge:
    """Stands in for ``purge_once``, counting its calls and failing the first one if told to."""

    def __init__(self, *, fail_first: bool = False) -> None:
        self.calls = 0
        self.fail_first = fail_first

    def __call__(self, settings: Settings, new_session: Callable[[], Session]) -> int:
        self.calls += 1
        if self.fail_first and self.calls == 1:
            raise ConnectionError("the database isn't up yet")
        return 0


def run_until_called(settings: Settings, purge: FakePurge, times: int) -> None:
    """Runs the loop, with its purge swapped for the fake, until it has been called that many
    times, then cancels it."""

    async def run() -> None:
        task = asyncio.create_task(
            retention.run(settings, lambda: None, interval=timedelta(milliseconds=1))  # type: ignore[arg-type,return-value]
        )
        while purge.calls < times:
            await asyncio.sleep(0.001)
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(retention, "purge_once", purge)
        asyncio.run(run())


def test_the_loop_purges_again_and_again(settings: Settings) -> None:
    purge = FakePurge()

    run_until_called(settings, purge, 3)

    assert purge.calls >= 3


def test_a_failed_purge_is_logged_and_tried_again(
    settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    purge = FakePurge(fail_first=True)

    with caplog.at_level(logging.ERROR):
        run_until_called(settings, purge, 2)

    assert "past their retention period" in caplog.text
    assert "the database isn't up yet" in caplog.text
    assert purge.calls >= 2


class TestStartingWithTheAPI:
    def test_the_api_purges_while_it_runs(
        self, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        events: list[str] = []

        async def run(given: Settings, new_session: Callable[[], Session]) -> None:
            events.append("started")
            assert given.environment == "development"
            assert callable(new_session)
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                events.append("stopped")
                raise

        monkeypatch.setattr(main.retention, "run", run)
        app = main.create_app(settings.model_copy(update={"environment": "development"}))

        with TestClient(app):
            assert events == ["started"]

        assert events == ["started", "stopped"]

    def test_tests_and_the_harness_decide_for_themselves(
        self, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def run(*_: object) -> None:
            pytest.fail("The log shouldn't be purged behind a test's back.")

        monkeypatch.setattr(main.retention, "run", run)

        assert settings.environment == "test"
        with TestClient(main.create_app(settings)):
            pass
