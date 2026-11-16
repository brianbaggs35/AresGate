"""The loop that learns what is normal and stores what is not."""

import asyncio
import logging
from collections.abc import Callable
from datetime import timedelta

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.baselines import run as baselines
from app.config import Settings
from app.models import Device, Event, utcnow


@pytest.fixture
def new_session(engine: Engine, session: Session) -> Callable[[], Session]:
    # The session fixture empties the tables after the test, which is what a run's own sessions
    # need too.
    return sessionmaker(bind=engine, expire_on_commit=False)


def add(session: Session, number: int, age: timedelta) -> None:
    now = utcnow()
    session.add(
        Device(
            mac=f"aa:bb:cc:00:00:{number:02x}",
            first_seen_at=now - age,
            last_seen_at=now,
        )
    )
    session.commit()


class TestOneRun:
    def test_a_quiet_network_has_nothing_to_say(
        self,
        settings: Settings,
        new_session: Callable[[], Session],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        with caplog.at_level(logging.INFO):
            result = baselines.learn_once(new_session, settings)

        assert result == baselines.Result()
        assert result.total == 0
        assert "Learned baselines" not in caplog.text

    def test_what_deviates_is_stored_as_events_and_said(
        self,
        session: Session,
        settings: Settings,
        new_session: Callable[[], Session],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        for number in range(1, 5):
            add(session, number, timedelta(days=30))
        baselines.learn_once(new_session, settings)
        add(session, 9, timedelta(minutes=1))

        with caplog.at_level(logging.INFO):
            result = baselines.learn_once(new_session, settings)

        assert result == baselines.Result(devices=1)
        assert "found 1 deviations: 0 traffic, 0 destinations, 1 devices" in caplog.text
        [event] = session.scalars(select(Event)).all()
        assert (event.source, event.connection, event.kind) == ("baseline", "learned", "alert")


class FakeRun:
    """Stands in for ``learn_once``, counting its calls and failing the first one if told to."""

    def __init__(self, *, fail_first: bool = False) -> None:
        self.calls = 0
        self.fail_first = fail_first

    def __call__(self, new_session: Callable[[], Session], settings: Settings) -> baselines.Result:
        self.calls += 1
        if self.fail_first and self.calls == 1:
            raise ConnectionError("the database isn't up yet")
        return baselines.Result()


def run_until_called(
    fake: FakeRun, times: int, settings: Settings, *, enabled: bool = True
) -> None:
    async def run() -> None:
        task = asyncio.create_task(
            baselines.run(
                lambda: None,  # type: ignore[arg-type,return-value]
                settings,
                enabled=enabled,
                interval=timedelta(milliseconds=1),
            )
        )
        for _ in range(50):
            if fake.calls >= times:
                break
            await asyncio.sleep(0.001)
        task.cancel()
        await asyncio.wait({task})

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(baselines, "learn_once", fake)
        asyncio.run(run())


def test_the_loop_learns_again_and_again(settings: Settings) -> None:
    fake = FakeRun()

    run_until_called(fake, 3, settings)

    assert fake.calls >= 3


def test_a_failure_is_logged_and_the_loop_goes_on(
    settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    fake = FakeRun(fail_first=True)

    with caplog.at_level(logging.ERROR):
        run_until_called(fake, 2, settings)

    assert fake.calls >= 2
    assert "Couldn't learn what is normal on the network" in caplog.text


def test_turned_off_it_learns_nothing(settings: Settings) -> None:
    fake = FakeRun()

    run_until_called(fake, 1, settings, enabled=False)

    assert fake.calls == 0


def test_the_count_of_what_a_run_found_is_the_sum_of_its_kinds() -> None:
    assert baselines.Result(traffic=1, destinations=2, devices=3).total == 6


def test_what_is_stored_is_not_more_than_the_events_it_made(session: Session) -> None:
    assert session.scalar(select(func.count()).select_from(Event)) == 0
