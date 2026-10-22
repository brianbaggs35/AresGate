from collections.abc import Iterator

import pytest
from argon2 import PasswordHasher
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db import get_session
from app.main import create_app
from app.models import Base, User
from app.security import passwords
from e2e import factories
from tests.helpers import (
    ACCOUNT_PASSWORD,
    ACCOUNT_USERNAME,
    ORIGIN,
    SERVER_NAME,
    TEST_DATABASE_URL,
    TEST_SECRET_KEY,
)


def pytest_configure() -> None:
    if not TEST_DATABASE_URL.startswith("postgresql"):
        raise pytest.UsageError(
            "The tests run on Postgres. Run `make test-backend`, which starts one, or set "
            "ARESGATE_TEST_DATABASE_URL to a Postgres database the tests may empty."
        )


@pytest.fixture(autouse=True)
def cheap_hashing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hashes passwords with the least work Argon2 allows, so each test that signs in doesn't
    spend a tenth of a second and 64 MiB on it."""
    monkeypatch.setattr(
        passwords, "hasher", PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
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
        secret_key=SecretStr(TEST_SECRET_KEY),
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
    # HTTPS, so the Secure session cookie is sent back like a browser would, and the Origin a
    # browser adds to every change.
    with TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN}) as client:
        yield client


@pytest.fixture
def account(session: Session) -> User:
    """The install's one account, as it is after setup."""
    user = factories.account(session, username=ACCOUNT_USERNAME, password=ACCOUNT_PASSWORD)
    session.commit()
    return user


@pytest.fixture
def csrf_token(client: TestClient, account: User) -> str:
    """Signs the client in as the account, and returns the token it sends with changes."""
    response = client.post(
        "/api/auth/login", json={"username": ACCOUNT_USERNAME, "password": ACCOUNT_PASSWORD}
    )
    assert response.status_code == 200
    return str(response.json()["csrf_token"])
