import asyncio
import logging
from collections.abc import Callable
from datetime import timedelta

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.events.event import NewEvent
from app.events.store import record as record_events
from app.incidents import engine as correlation
from app.incidents import run as incidents
from app.models import Incident, utcnow
from tests.helpers import new_event


@pytest.fixture
def new_session(engine: Engine) -> Callable[[], Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def long_ago_alert() -> NewEvent:
    return new_event(
        occurred_at=utcnow() - timedelta(minutes=10),
        identity=("alert-1",),
        src_address="93.184.216.34",
        dst_address="192.168.1.20",
        signature="ET SCAN Potential SSH Scan",
    )


def count(db: Session) -> int:
    db.expire_all()
    return db.scalar(select(func.count()).select_from(Incident)) or 0


class TestOneRun:
    def test_it_files_what_was_stored_and_saves_it(
        self,
        session: Session,
        settings: Settings,
        new_session: Callable[[], Session],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        record_events(session, settings, [long_ago_alert()], utcnow() - timedelta(minutes=9))
        session.commit()

        with caplog.at_level(logging.INFO):
            result = incidents.correlate_once(new_session)

        assert result == correlation.Result(events=1, created=1, updated=0)
        assert count(session) == 1
        assert "Filed 1 signals: 1 new incidents, 0 updated" in caplog.text

    def test_it_says_nothing_when_there_was_nothing_to_file(
        self, new_session: Callable[[], Session], caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO):
            result = incidents.correlate_once(new_session)

        assert result == correlation.Result()
        assert "Filed" not in caplog.text


class FakeRun:
    """Stands in for ``correlate_once``, counting its calls and failing the first one if told to."""

    def __init__(self, *, fail_first: bool = False, behind_first: int = 0) -> None:
        self.calls = 0
        self.fail_first = fail_first
        self.behind_first = behind_first

    def __call__(self, new_session: Callable[[], Session]) -> correlation.Result:
        self.calls += 1
        if self.fail_first and self.calls == 1:
            raise ConnectionError("the database isn't up yet")
        return correlation.Result(behind=self.calls <= self.behind_first)


def run_until_called(
    fake: FakeRun,
    times: int,
    *,
    enabled: bool = True,
    interval: timedelta = timedelta(milliseconds=1),
) -> None:
    """Runs the loop, with its work swapped for the fake, until it has been called that many
    times (or for a moment, if it never will be), then cancels it."""

    async def run() -> None:
        task = asyncio.create_task(
            incidents.run(
                lambda: None,  # type: ignore[arg-type,return-value]
                enabled=enabled,
                interval=interval,
            )
        )
        for _ in range(50):
            if fake.calls >= times:
                break
            await asyncio.sleep(0.001)
        task.cancel()
        await asyncio.wait({task})

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(incidents, "correlate_once", fake)
        asyncio.run(run())


def test_the_loop_files_again_and_again() -> None:
    fake = FakeRun()

    run_until_called(fake, 3)

    assert fake.calls >= 3


def test_a_run_with_more_waiting_is_followed_at_once_by_another() -> None:
    fake = FakeRun(behind_first=2)

    # The interval is far longer than the test, so only being behind can make it call again.
    run_until_called(fake, 3, interval=timedelta(hours=1))

    assert fake.calls == 3


def test_a_failed_run_is_logged_and_tried_again(caplog: pytest.LogCaptureFixture) -> None:
    fake = FakeRun(fail_first=True)

    with caplog.at_level(logging.ERROR):
        run_until_called(fake, 2)

    assert "Couldn't file the latest signals into incidents" in caplog.text
    assert "the database isn't up yet" in caplog.text
    assert fake.calls >= 2


def test_when_collecting_is_off_nothing_is_filed() -> None:
    fake = FakeRun()

    run_until_called(fake, 1, enabled=False)

    assert fake.calls == 0
