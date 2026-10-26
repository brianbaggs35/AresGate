import asyncio
import runpy
from collections.abc import Coroutine
from typing import Any

import pytest
from pydantic import SecretStr
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app import config, db, worker
from app.config import Settings
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

    assert ran == ["Scheduler.run"]


def test_main_needs_a_usable_secret_key(
    monkeypatch: pytest.MonkeyPatch, untouched_logging: None
) -> None:
    short = Settings(environment="test", secret_key=SecretStr("too short"))
    monkeypatch.setattr(worker, "get_settings", lambda: short)

    with pytest.raises(SecretKeyError, match="at least 32"):
        worker.main()
