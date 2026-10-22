from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db import get_session
from app.main import create_app
from app.models import Base
from tests.helpers import ORIGIN, SERVER_NAME, TEST_DATABASE_URL


def pytest_configure() -> None:
    if not TEST_DATABASE_URL.startswith("postgresql"):
        raise pytest.UsageError(
            "The tests run on Postgres. Run `make test-backend`, which starts one, or set "
            "ARESGATE_TEST_DATABASE_URL to a Postgres database the tests may empty."
        )


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def settings() -> Settings:
    return Settings(
        environment="test",
        database_url=TEST_DATABASE_URL,
        enable_docs=True,
        server_name=SERVER_NAME,
    )


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        yield session
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())


@pytest.fixture
def app(settings: Settings, session: Session) -> FastAPI:
    def request_session() -> Iterator[Session]:
        # Like a real request's session, anything not committed is rolled back at the end.
        try:
            yield session
        finally:
            session.rollback()

    app = create_app(settings)
    app.dependency_overrides[get_session] = request_session
    return app


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    # HTTPS, so the Secure session cookie (added with sign-in) is sent back like a browser would.
    with TestClient(app, base_url=ORIGIN) as client:
        yield client
