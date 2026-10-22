import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app import main
from app.config import Settings
from app.main import create_app
from app.secret_key import SecretKeyError
from tests.helpers import TEST_SECRET_KEY


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


def test_the_server_sets_up_logging_with_the_secret_key_to_hide(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[Settings, list[str]]] = []

    def configure(given: Settings, secrets: list[str]) -> None:
        calls.append((given, secrets))

    monkeypatch.setattr(main.logs, "configure", configure)
    development = settings.model_copy(update={"environment": "development"})

    with TestClient(create_app(development)):
        pass

    assert calls == [(development, [TEST_SECRET_KEY])]


def test_tests_and_the_harness_leave_logging_as_it_is(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    def configure(*_: object, **__: object) -> None:
        pytest.fail("The tests' own logging shouldn't be replaced.")

    monkeypatch.setattr(main.logs, "configure", configure)

    with TestClient(create_app(settings)):
        pass
