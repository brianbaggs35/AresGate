"""The worker's loops are told of work by PostgreSQL instead of finding it when their interval runs
out, and go on as they did when they aren't told."""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Coroutine
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app import wakeups
from app.agents import run as agents
from app.agents import service as agent_service
from app.alerts import notify
from app.alerts.discord import Sent
from app.config import Settings
from app.events.store import record as record_events
from app.incidents import run as incidents
from app.integrations import netguard
from app.models import Agent, AlertDelivery, Incident, utcnow
from app.wakeups import Signal, Wakeups
from tests.helpers import new_event
from tests.test_alerts_notify import HOUR, destination, nothing
from tests.test_incidents_run import long_ago_alert

LONG = timedelta(hours=1)
SOON = 5.0


async def until(condition: Callable[[], bool | Awaitable[bool]], seconds: float = SOON) -> bool:
    """Waits for ``condition`` to hold, and says whether it did within ``seconds``."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        found = condition()
        if (await found) if isinstance(found, Awaitable) else found:
            return True
        await asyncio.sleep(0.01)
    return False


def forgetting_nothing(_: object) -> None:
    """Stands in for what an agents loop does when it starts."""


def count(session: Session, model: Any) -> int:
    session.expire_all()
    return session.scalar(select(func.count()).select_from(model)) or 0


class TestASignal:
    def test_it_ends_the_wait_when_it_comes(self) -> None:
        async def go() -> list[bool]:
            signal = Signal()
            asyncio.get_running_loop().call_later(0.01, signal.set)
            return [await signal.wait(LONG)]

        assert asyncio.run(go()) == [True]

    def test_the_wait_runs_out_when_it_does_not(self) -> None:
        assert asyncio.run(Signal().wait(timedelta(milliseconds=5))) is False

    def test_one_that_came_while_the_loop_was_busy_ends_the_next_wait_at_once(self) -> None:
        async def go() -> list[bool]:
            signal = Signal()
            signal.set()
            signal.set()
            return [await signal.wait(LONG), await signal.wait(timedelta(milliseconds=5))]

        assert asyncio.run(go()) == [True, False]

    def test_without_one_a_loop_only_waits(self) -> None:
        assert asyncio.run(wakeups.pause(None, timedelta(milliseconds=1))) is False

    def test_with_one_a_loop_waits_for_it(self) -> None:
        signal = Signal()
        signal.set()

        assert asyncio.run(wakeups.pause(signal, LONG)) is True


class TestWhoIsTold:
    def test_each_channel_wakes_its_own_loop(self) -> None:
        wake = Wakeups()

        wake.wake(wakeups.INCIDENTS)
        wake.wake("someone_elses")

        async def asked() -> list[bool]:
            quick = timedelta(milliseconds=1)
            return [
                await wake.events.wait(quick),
                await wake.incidents.wait(quick),
                await wake.agent_runs.wait(quick),
            ]

        assert asyncio.run(asked()) == [False, True, False]

    def test_all_of_them_can_be_woken(self) -> None:
        wake = Wakeups()
        wake.wake_all()

        async def asked() -> list[bool]:
            quick = timedelta(milliseconds=1)
            return [
                await wake.events.wait(quick),
                await wake.incidents.wait(quick),
                await wake.agent_runs.wait(quick),
            ]

        assert asyncio.run(asked()) == [True, True, True]


class TestListening:
    def test_a_note_sent_in_a_committed_change_wakes_the_loop(
        self, session: Session, settings: Settings
    ) -> None:
        async def go() -> list[bool]:
            wake = Wakeups()
            listener = asyncio.create_task(wakeups.listen(settings, wake))
            # The first thing it does is to wake everything, which is not what is looked at.
            await wake.events.wait(LONG)
            await wake.incidents.wait(LONG)
            await wake.agent_runs.wait(LONG)
            await asyncio.to_thread(self.send, session, wakeups.INCIDENTS)
            woken = await wake.incidents.wait(timedelta(seconds=SOON))
            others = [
                await wake.events.wait(timedelta(milliseconds=50)),
                await wake.agent_runs.wait(timedelta(milliseconds=50)),
            ]
            listener.cancel()
            await asyncio.wait({listener})
            return [woken, *others]

        assert asyncio.run(go()) == [True, False, False]

    @staticmethod
    def send(session: Session, channel: str, *, commit: bool = True) -> None:
        wakeups.notify(session, channel)
        session.commit() if commit else session.rollback()

    def test_a_note_in_a_change_that_was_rolled_back_wakes_nothing(
        self, session: Session, settings: Settings
    ) -> None:
        async def go() -> bool:
            wake = Wakeups()
            listener = asyncio.create_task(wakeups.listen(settings, wake))
            await wake.events.wait(LONG)
            await asyncio.to_thread(self.send, session, wakeups.EVENTS, commit=False)
            woken = await wake.events.wait(timedelta(milliseconds=300))
            listener.cancel()
            await asyncio.wait({listener})
            return woken

        assert asyncio.run(go()) is False

    def test_storing_events_notes_that_there_are_some(
        self, session: Session, settings: Settings
    ) -> None:
        async def go() -> bool:
            wake = Wakeups()
            listener = asyncio.create_task(wakeups.listen(settings, wake))
            await wake.events.wait(LONG)

            def store() -> None:
                now = utcnow()
                record_events(session, settings, [new_event(occurred_at=now)], now)
                session.commit()

            await asyncio.to_thread(store)
            woken = await wake.events.wait(timedelta(seconds=SOON))
            listener.cancel()
            await asyncio.wait({listener})
            return woken

        assert asyncio.run(go()) is True

    def test_events_that_were_all_stored_before_say_nothing(
        self, session: Session, settings: Settings
    ) -> None:
        async def go() -> bool:
            now = utcnow()
            record_events(session, settings, [new_event(occurred_at=now)], now)
            session.commit()
            wake = Wakeups()
            listener = asyncio.create_task(wakeups.listen(settings, wake))
            await wake.events.wait(LONG)

            def again() -> None:
                record_events(session, settings, [new_event(occurred_at=now)], now)
                session.commit()

            await asyncio.to_thread(again)
            woken = await wake.events.wait(timedelta(milliseconds=300))
            listener.cancel()
            await asyncio.wait({listener})
            return woken

        assert asyncio.run(go()) is False

    def test_asking_for_an_agent_run_notes_it(self, session: Session, settings: Settings) -> None:
        agent = Agent(
            name="Quiet hours",
            template="network-health",
            goal="",
            enabled=True,
            created_at=utcnow(),
        )

        async def go() -> bool:
            session.add(agent)
            session.commit()
            wake = Wakeups()
            listener = asyncio.create_task(wakeups.listen(settings, wake))
            await wake.agent_runs.wait(LONG)

            def ask() -> None:
                agent_service.queue(session, agent, "manual", utcnow())
                session.commit()

            await asyncio.to_thread(ask)
            woken = await wake.agent_runs.wait(timedelta(seconds=SOON))
            listener.cancel()
            await asyncio.wait({listener})
            return woken

        assert asyncio.run(go()) is True


class TestFilingIncidents:
    def test_filing_an_incident_notes_it_and_filing_nothing_does_not(
        self, session: Session, settings: Settings, engine: Engine
    ) -> None:
        new_session = sessionmaker(bind=engine, expire_on_commit=False)

        async def go() -> list[bool]:
            wake = Wakeups()
            listener = asyncio.create_task(wakeups.listen(settings, wake))
            await wake.incidents.wait(LONG)
            nothing_to_file = await asyncio.to_thread(incidents.correlate_once, new_session)
            quiet = await wake.incidents.wait(timedelta(milliseconds=300))

            def store() -> None:
                record_events(
                    session, settings, [long_ago_alert()], utcnow() - timedelta(minutes=9)
                )
                session.commit()

            await asyncio.to_thread(store)
            filed = await asyncio.to_thread(incidents.correlate_once, new_session)
            told = await wake.incidents.wait(timedelta(seconds=SOON))
            listener.cancel()
            await asyncio.wait({listener})
            assert nothing_to_file.created == 0
            assert filed.created == 1
            return [quiet, told]

        assert asyncio.run(go()) == [False, True]


class TestWhenTheConnectionIsLost:
    def test_it_listens_again_and_makes_up_for_what_it_missed(
        self,
        session: Session,
        settings: Settings,
        engine: Engine,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        def listener_pids() -> list[int]:
            with engine.connect() as connection:
                return [
                    row[0]
                    for row in connection.execute(
                        text(
                            "SELECT pid FROM pg_stat_activity WHERE datname = current_database()"
                            " AND pid <> pg_backend_pid() AND query LIKE 'LISTEN%'"
                        )
                    )
                ]

        def cut() -> None:
            with engine.connect() as connection:
                for pid in listener_pids():
                    connection.execute(text("SELECT pg_terminate_backend(:pid)"), {"pid": pid})

        async def go() -> list[bool]:
            wake = Wakeups()
            listener = asyncio.create_task(
                wakeups.listen(settings, wake, first_retry=0.01, longest_retry=0.05)
            )
            assert await until(lambda: bool(listener_pids()))
            await wake.events.wait(LONG)
            await asyncio.to_thread(cut)
            # Listening again wakes everything, for it can't know what it missed.
            back = await wake.events.wait(timedelta(seconds=SOON))
            await wake.incidents.wait(LONG)
            assert await until(lambda: bool(listener_pids()))
            await asyncio.to_thread(TestListening.send, session, wakeups.INCIDENTS)
            told = await wake.incidents.wait(timedelta(seconds=SOON))
            listener.cancel()
            await asyncio.wait({listener})
            return [back, told]

        with caplog.at_level(logging.INFO, logger="app.wakeups"):
            assert asyncio.run(go()) == [True, True]

        assert [record.levelno for record in caplog.records if record.name == "app.wakeups"] == [
            logging.WARNING,
            logging.INFO,
        ]

    def test_a_database_that_is_not_there_is_logged_once_and_tried_again(
        self, settings: Settings, caplog: pytest.LogCaptureFixture
    ) -> None:
        nowhere = settings.model_copy(
            update={"database_url": "postgresql+psycopg://nobody@127.0.0.1:1/nothing"}
        )

        async def go() -> None:
            listener = asyncio.create_task(
                wakeups.listen(nowhere, Wakeups(), first_retry=0.01, longest_retry=0.02)
            )
            await asyncio.sleep(0.4)
            listener.cancel()
            await asyncio.wait({listener})

        with caplog.at_level(logging.INFO, logger="app.wakeups"):
            asyncio.run(go())

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1
        assert "go by their intervals" in warnings[0].message


class TestTheLoopsWithoutNotes:
    """A signal that never comes leaves each loop going by its interval, as without one."""

    @staticmethod
    def goes_on(loop: Callable[[Signal], Coroutine[Any, Any, None]], calls: list[int]) -> None:
        async def go() -> None:
            task: asyncio.Task[None] = asyncio.create_task(loop(Signal()))
            assert await until(lambda: len(calls) >= 3)
            task.cancel()
            await asyncio.wait({task})

        asyncio.run(go())

    def test_the_incidents_loop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[int] = []

        def correlated(_: Any) -> incidents.engine.Result:
            calls.append(1)
            return incidents.engine.Result()

        monkeypatch.setattr(incidents, "correlate_once", correlated)

        self.goes_on(
            lambda signal: incidents.run(
                lambda: None,  # type: ignore[arg-type,return-value]
                interval=timedelta(milliseconds=1),
                wake=signal,
            ),
            calls,
        )

    def test_the_agents_loop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[int] = []

        async def ran(*args: Any, **kwargs: Any) -> int:
            calls.append(1)
            return 0

        monkeypatch.setattr(agents, "run_once", ran)
        monkeypatch.setattr(agents, "_forget", forgetting_nothing)

        self.goes_on(
            lambda signal: agents.run(
                lambda: None,  # type: ignore[arg-type,return-value]
                None,  # type: ignore[arg-type]
                interval=timedelta(milliseconds=1),
                wake=signal,
            ),
            calls,
        )

    def test_the_notifier_loop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[int] = []

        async def told(*args: Any, **kwargs: Any) -> notify.Report:
            calls.append(1)
            return notify.Report()

        monkeypatch.setattr(notify, "notify_once", told)

        self.goes_on(
            lambda signal: notify.run(
                None,  # type: ignore[arg-type]
                lambda: None,  # type: ignore[arg-type,return-value]
                nothing,
                netguard.PUBLIC_INTERNET,
                interval=timedelta(milliseconds=1),
                wake=signal,
            ),
            calls,
        )


class TestTheLoopsAreWoken:
    def test_the_incidents_loop_files_what_was_stored_after_the_events_settle(
        self, session: Session, settings: Settings, engine: Engine
    ) -> None:
        new_session = sessionmaker(bind=engine, expire_on_commit=False)
        calls: list[float] = []

        def counted(_: Any) -> Any:
            calls.append(time.monotonic())
            return incidents.engine.Result()

        async def go() -> list[float]:
            signal = Signal()
            with pytest.MonkeyPatch.context() as patch:
                patch.setattr(incidents, "correlate_once", counted)
                task = asyncio.create_task(
                    incidents.run(
                        new_session, interval=LONG, wake=signal, settle=timedelta(seconds=0.2)
                    )
                )
                assert await until(lambda: len(calls) == 1)
                await asyncio.sleep(0.1)
                assert len(calls) == 1
                woke = time.monotonic()
                signal.set()
                assert await until(lambda: len(calls) == 2)
                task.cancel()
                await asyncio.wait({task})
            return [calls[1] - woke]

        [waited] = asyncio.run(go())

        assert 0.2 <= waited < 2

    def test_the_agents_loop_runs_a_run_that_was_asked_for_at_once(self) -> None:
        calls: list[int] = []

        async def counted(*args: Any, **kwargs: Any) -> int:
            calls.append(1)
            return 0

        async def go() -> None:
            signal = Signal()
            with pytest.MonkeyPatch.context() as patch:
                patch.setattr(agents, "run_once", counted)
                patch.setattr(agents, "_forget", forgetting_nothing)
                task = asyncio.create_task(
                    agents.run(
                        lambda: None,  # type: ignore[arg-type,return-value]
                        None,  # type: ignore[arg-type]
                        interval=LONG,
                        wake=signal,
                    )
                )
                assert await until(lambda: len(calls) == 1)
                signal.set()
                assert await until(lambda: len(calls) == 2)
                task.cancel()
                await asyncio.wait({task})

        asyncio.run(go())

    def test_the_notifier_loop_tells_at_once_when_an_incident_is_filed(self) -> None:
        calls: list[int] = []

        async def counted(*args: Any, **kwargs: Any) -> notify.Report:
            calls.append(1)
            return notify.Report()

        async def go() -> None:
            signal = Signal()
            with pytest.MonkeyPatch.context() as patch:
                patch.setattr(notify, "notify_once", counted)
                task = asyncio.create_task(
                    notify.run(
                        None,  # type: ignore[arg-type]
                        lambda: None,  # type: ignore[arg-type,return-value]
                        nothing,
                        netguard.PUBLIC_INTERNET,
                        interval=LONG,
                        wake=signal,
                    )
                )
                assert await until(lambda: len(calls) == 1)
                signal.set()
                assert await until(lambda: len(calls) == 2)
                task.cancel()
                await asyncio.wait({task})

        asyncio.run(go())


class TestFromAnAlertToAMessage:
    """With every interval an hour long, only notes can get an alert to its destination in time."""

    def test_an_alert_is_filed_and_told_within_seconds_of_settling(
        self,
        session: Session,
        settings: Settings,
        engine: Engine,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        new_session = sessionmaker(bind=engine, expire_on_commit=False)
        told: list[float] = []

        async def discord_says_yes(*args: Any, **kwargs: Any) -> Sent:
            told.append(time.monotonic())
            return Sent(ok=True, status=200, message_id="1100000000000000001")

        monkeypatch.setattr(notify.discord, "send", discord_says_yes)
        row = destination(session, settings, min_severity=1, min_confidence=1)
        row.listening_since = utcnow() - 2 * HOUR
        session.commit()

        async def go() -> float:
            wake = Wakeups()
            listener = asyncio.create_task(wakeups.listen(settings, wake))
            filing = asyncio.create_task(
                incidents.run(
                    new_session, interval=LONG, wake=wake.events, settle=timedelta(seconds=0.1)
                )
            )
            telling = asyncio.create_task(
                notify.run(
                    settings,
                    new_session,
                    nothing,
                    netguard.PUBLIC_INTERNET,
                    interval=LONG,
                    wake=wake.incidents,
                )
            )
            # Both loops have done their first look, and now sleep for an hour.
            await asyncio.sleep(1)
            started = time.monotonic()

            def alert() -> None:
                now = utcnow() - timedelta(minutes=9)
                record_events(session, settings, [long_ago_alert()], now)
                session.commit()

            await asyncio.to_thread(alert)
            arrived = await until(lambda: bool(told), seconds=10)
            elapsed = told[0] - started if told else 10.0
            for task in (listener, filing, telling):
                task.cancel()
            await asyncio.wait({listener, filing, telling})
            assert arrived
            return elapsed

        elapsed = asyncio.run(go())

        assert elapsed < 5
        assert count(session, Incident) == 1
        assert count(session, AlertDelivery) == 1
