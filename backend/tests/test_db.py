import pytest

from app import db
from app.config import Settings
from tests.helpers import TEST_DATABASE_URL


@pytest.fixture(autouse=True)
def fresh_caches() -> None:
    db.get_engine.cache_clear()
    db.get_sessionmaker.cache_clear()


def test_engine_is_built_from_the_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db, "get_settings", lambda: Settings(database_url=TEST_DATABASE_URL))
    engine = db.get_engine()
    assert engine.url.render_as_string(hide_password=False) == TEST_DATABASE_URL
    assert db.get_engine() is engine
    assert db.get_sessionmaker() is db.get_sessionmaker()
    engine.dispose()


def test_get_session_yields_a_working_session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db, "get_settings", lambda: Settings(database_url=TEST_DATABASE_URL))
    for session in db.get_session():
        assert session.connection().exec_driver_sql("SELECT 1").scalar_one() == 1
    db.get_engine().dispose()
