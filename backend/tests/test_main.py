import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import Settings
from app.main import create_app
from app.secret_key import SecretKeyError


def test_docs_are_off_by_default() -> None:
    client = TestClient(create_app(Settings(environment="production", enable_docs=False)))
    assert client.get("/api/docs").status_code == 404
    assert client.get("/api/openapi.json").status_code == 404


def test_docs_can_be_turned_on() -> None:
    client = TestClient(create_app(Settings(environment="development", enable_docs=True)))
    assert client.get("/api/docs").status_code == 200
    assert client.get("/api/openapi.json").json()["info"]["title"] == "AresGate API"


def test_the_version_is_the_apps() -> None:
    app = create_app(Settings(release="2.0.0"))
    assert app.version == "2.0.0"


def test_the_server_starts_with_the_secret_key_loaded(settings: Settings) -> None:
    app = create_app(settings)
    with TestClient(app):
        assert app.state.secret_key == settings.secret_key


def test_the_server_will_not_start_without_a_usable_secret_key(settings: Settings) -> None:
    app = create_app(settings.model_copy(update={"secret_key": SecretStr("too short")}))
    with pytest.raises(SecretKeyError, match="needs at least 32"), TestClient(app):
        pass
