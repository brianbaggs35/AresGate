from pathlib import Path

import pytest
from pydantic import ValidationError

from app import __version__
from app.config import Settings, get_settings


def test_defaults_target_bundled_postgres_socket(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)  # no stray .env file
    monkeypatch.delenv("ARESGATE_DATABASE_URL", raising=False)
    monkeypatch.delenv("ARESGATE_ENVIRONMENT", raising=False)
    settings = Settings()
    assert settings.database_url == "postgresql+psycopg://aresgate@/aresgate?host=/run/postgresql"
    assert settings.is_production
    assert not settings.enable_docs
    assert settings.secret_key is None
    assert settings.secret_key_file == Path("/data/secrets/secret.key")


def test_reads_prefixed_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ARESGATE_ENVIRONMENT", "development")
    monkeypatch.setenv("ARESGATE_ENABLE_DOCS", "true")
    settings = Settings()
    assert settings.environment == "development"
    assert not settings.is_production
    assert settings.enable_docs


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()


def test_version_comes_from_the_release_when_there_is_one() -> None:
    assert Settings(release=None).version == __version__
    assert Settings(release="1.4.0").version == "1.4.0"


def test_public_origin_leaves_out_the_default_port() -> None:
    assert Settings(server_name="ares.example.com", https_port=443).public_origin == (
        "https://ares.example.com"
    )
    assert Settings(server_name="ares.example.com", https_port=9443).public_origin == (
        "https://ares.example.com:9443"
    )


def test_port_must_be_a_real_port() -> None:
    with pytest.raises(ValidationError):
        Settings(https_port=0)
    with pytest.raises(ValidationError):
        Settings(https_port=70000)


def test_secret_key_is_read_from_the_environment_and_kept_out_of_logs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ARESGATE_SECRET_KEY", "k" * 40)
    monkeypatch.setenv("ARESGATE_SECRET_KEY_FILE", str(tmp_path / "key"))
    settings = Settings()
    assert settings.secret_key is not None
    assert settings.secret_key.get_secret_value() == "k" * 40
    assert "k" * 40 not in repr(settings)
    assert settings.secret_key_file == tmp_path / "key"


def test_a_sign_in_lasts_half_an_hour_idle_and_half_a_day_at_most() -> None:
    settings = Settings()

    assert settings.session_idle_minutes == 30
    assert settings.session_max_hours == 12


@pytest.mark.parametrize("setting", ["session_idle_minutes", "session_max_hours"])
def test_a_sign_in_cannot_last_no_time_at_all(setting: str) -> None:
    with pytest.raises(ValidationError):
        Settings(**{setting: 0})  # type: ignore[arg-type]


def test_the_audit_log_keeps_a_year_by_default() -> None:
    assert Settings().audit_retention_days == 365


@pytest.mark.parametrize("days", [0, -1, 3651])
def test_the_audit_log_keeps_between_a_day_and_ten_years(days: int) -> None:
    with pytest.raises(ValidationError):
        Settings(audit_retention_days=days)


def test_logs_are_json_at_info_by_default() -> None:
    settings = Settings()

    assert (settings.log_format, settings.log_level) == ("json", "info")


@pytest.mark.parametrize("setting", [{"log_format": "xml"}, {"log_level": "chatty"}])
def test_logs_come_in_the_formats_and_levels_that_exist(setting: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        Settings(**setting)  # type: ignore[arg-type]
