import asyncio
import runpy
from collections.abc import Callable, Coroutine
from typing import Any

import pytest
from pydantic import SecretStr
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app import config, db, worker
from app.ai.gateway import Context
from app.config import Settings
from app.integrations import netguard
from app.models import CollectorHealth, IntegrationConnection, WorkerBeat
from app.secret_key import SecretKeyError
from tests.helpers import TEST_DATABASE_URL, TEST_SECRET_KEY


@pytest.fixture
def worker_database(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    """Points the worker at the test database."""
    monkeypatch.setattr(
        worker, "get_sessionmaker", lambda: sessionmaker(bind=engine, expire_on_commit=False)
    )


def test_in_the_tests_the_worker_says_it_is_alive_and_collects_nothing(
    session: Session, settings: Settings, worker_database: None
) -> None:
    session.add(
        IntegrationConnection(
            integration="ntopng",
            connection="api",
            base_url="http://192.168.1.2:3000",
            tls_mode="system",
            options={},
            disabled_modules=[],
        )
    )
    session.commit()

    asyncio.run(worker.build(settings).tick())

    assert session.scalar(select(WorkerBeat)) is not None
    assert session.scalars(select(CollectorHealth)).all() == []


def test_a_real_install_collects(
    session: Session, settings: Settings, worker_database: None
) -> None:
    session.add(
        IntegrationConnection(
            integration="ntopng",
            connection="api",
            base_url="http://192.168.1.2:3000",
            tls_mode="system",
            options={},
            disabled_modules=[],
        )
    )
    session.commit()
    production = settings.model_copy(update={"environment": "production"})

    asyncio.run(worker.build(production).tick())

    assert session.scalar(select(WorkerBeat)) is not None
    assert sorted(row.collector for row in session.scalars(select(CollectorHealth))) == [
        "connection-check",
        "ntopng-alerts",
        "ntopng-hosts",
        "ntopng-interface",
    ]


def test_turned_off_it_does_not_collect(
    session: Session, settings: Settings, worker_database: None
) -> None:
    session.add(
        IntegrationConnection(
            integration="ntopng",
            connection="api",
            base_url="http://192.168.1.2:3000",
            tls_mode="system",
            options={},
            disabled_modules=[],
        )
    )
    session.commit()
    off = settings.model_copy(update={"environment": "production", "collectors_enabled": False})

    asyncio.run(worker.build(off).tick())

    assert session.scalar(select(WorkerBeat)) is not None
    assert session.scalars(select(CollectorHealth)).all() == []


@pytest.mark.parametrize(
    ("changes", "collects"),
    [
        ({"environment": "production"}, True),
        ({"environment": "production", "collectors_enabled": False}, False),
        ({"environment": "test"}, False),
    ],
    ids=["a real install", "turned off", "the tests"],
)
def test_it_collects_on_a_real_install_unless_it_is_turned_off(
    settings: Settings, changes: dict[str, object], collects: bool
) -> None:
    assert worker.collecting(settings.model_copy(update=changes)) is collects


class TestServing:
    def test_it_collects_files_incidents_and_has_them_read_side_by_side(
        self, settings: Settings, worker_database: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        started: list[str] = []

        class Collecting:
            async def run(self) -> None:
                started.append("collectors")

        async def file_incidents(new_session: Callable[[], Session], *, enabled: bool) -> None:
            assert callable(new_session)
            started.append(f"incidents, enabled: {enabled}")

        async def read_incidents(
            new_session: Callable[[], Session], context: Context, *, enabled: bool
        ) -> None:
            assert callable(new_session)
            assert context.settings.environment == "production"
            started.append(f"AI, enabled: {enabled}")

        def collecting(_: Settings) -> Collecting:
            return Collecting()

        async def tell_destinations(
            settings: Settings,
            new_session: Callable[[], Session],
            recorder: object,
            policy: object,
            *,
            enabled: bool,
        ) -> None:
            assert callable(new_session)
            assert settings.environment == "production"
            assert callable(recorder)
            assert policy is netguard.PUBLIC_INTERNET
            started.append(f"alerts, enabled: {enabled}")

        monkeypatch.setattr(worker, "build", collecting)
        monkeypatch.setattr(worker.incidents, "run", file_incidents)
        monkeypatch.setattr(worker.ai, "run", read_incidents)
        monkeypatch.setattr(worker.notify, "run", tell_destinations)
        production = settings.model_copy(update={"environment": "production"})

        asyncio.run(worker.serve(production))

        assert sorted(started) == [
            "AI, enabled: True",
            "alerts, enabled: True",
            "collectors",
            "incidents, enabled: True",
        ]

    def test_one_that_stops_takes_the_other_with_it(
        self, settings: Settings, worker_database: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cancelled: list[str] = []

        class Failing:
            async def run(self) -> None:
                raise RuntimeError("the scheduler fell over")

        def waiting(name: str) -> Callable[..., Coroutine[Any, Any, None]]:
            async def wait_forever(*_: object, **__: object) -> None:
                try:
                    await asyncio.sleep(3600)
                except asyncio.CancelledError:
                    cancelled.append(name)
                    raise

            return wait_forever

        def failing(_: Settings) -> Failing:
            return Failing()

        monkeypatch.setattr(worker, "build", failing)
        monkeypatch.setattr(worker.incidents, "run", waiting("incidents"))
        monkeypatch.setattr(worker.ai, "run", waiting("AI"))
        monkeypatch.setattr(worker.notify, "run", waiting("alerts"))

        serving = worker.serve(settings)

        with pytest.raises(ExceptionGroup) as raised:
            asyncio.run(serving)

        assert raised.group_contains(RuntimeError, match="fell over")
        assert sorted(cancelled) == ["AI", "alerts", "incidents"]


@pytest.mark.filterwarnings("ignore:.*found in sys.modules:RuntimeWarning")
def test_it_runs_as_a_module(
    monkeypatch: pytest.MonkeyPatch, untouched_logging: None, engine: Engine
) -> None:
    ran: list[str] = []

    def run(coroutine: Coroutine[Any, Any, None]) -> None:
        # What `asyncio.run` would run for as long as the worker lives.
        ran.append(coroutine.__qualname__)
        coroutine.close()

    for name, value in {
        "ARESGATE_ENVIRONMENT": "test",
        "ARESGATE_DATABASE_URL": TEST_DATABASE_URL,
        "ARESGATE_SECRET_KEY": TEST_SECRET_KEY,
    }.items():
        monkeypatch.setenv(name, value)
    config.get_settings.cache_clear()
    db.get_engine.cache_clear()
    db.get_sessionmaker.cache_clear()
    monkeypatch.setattr(asyncio, "run", run)
    try:
        runpy.run_module("app.worker", run_name="__main__")
    finally:
        config.get_settings.cache_clear()
        db.get_engine.cache_clear()
        db.get_sessionmaker.cache_clear()

    assert ran == ["serve"]


def test_main_needs_a_usable_secret_key(
    monkeypatch: pytest.MonkeyPatch, untouched_logging: None
) -> None:
    short = Settings(environment="test", secret_key=SecretStr("too short"))
    monkeypatch.setattr(worker, "get_settings", lambda: short)

    with pytest.raises(SecretKeyError, match="at least 32"):
        worker.main()
