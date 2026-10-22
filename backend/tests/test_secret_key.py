from pathlib import Path

import pytest
from pydantic import SecretStr

from app import secret_key
from app.config import Settings
from app.secret_key import MIN_LENGTH, SecretKeyError, check_or_exit, load_secret_key

KEY = "a-key-that-is-long-enough-to-use-123"


def settings_for(key_file: Path, key: str | None = None) -> Settings:
    return Settings(secret_key=None if key is None else SecretStr(key), secret_key_file=key_file)


def test_the_key_can_be_given_directly(tmp_path: Path) -> None:
    assert load_secret_key(settings_for(tmp_path / "none", KEY)).get_secret_value() == KEY


def test_the_key_is_read_from_the_file_without_its_newline(tmp_path: Path) -> None:
    key_file = tmp_path / "secret.key"
    key_file.write_text(f"{KEY}\n")
    assert load_secret_key(settings_for(key_file)).get_secret_value() == KEY


def test_a_key_given_directly_wins_over_the_file(tmp_path: Path) -> None:
    key_file = tmp_path / "secret.key"
    key_file.write_text("f" * MIN_LENGTH)
    assert load_secret_key(settings_for(key_file, KEY)).get_secret_value() == KEY


def test_a_blank_key_falls_back_to_the_file(tmp_path: Path) -> None:
    # `ARESGATE_SECRET_KEY=` left empty in .env is the same as not setting it.
    key_file = tmp_path / "secret.key"
    key_file.write_text(KEY)
    assert load_secret_key(settings_for(key_file, "  ")).get_secret_value() == KEY


def test_a_key_of_the_minimum_length_is_enough(tmp_path: Path) -> None:
    key = "k" * MIN_LENGTH
    assert load_secret_key(settings_for(tmp_path / "none", key)).get_secret_value() == key


@pytest.mark.parametrize("key", ["", "short", "k" * (MIN_LENGTH - 1)])
def test_a_key_that_is_too_short_is_refused(tmp_path: Path, key: str) -> None:
    key_file = tmp_path / "secret.key"
    key_file.write_text(key)
    with pytest.raises(SecretKeyError, match=f"needs at least {MIN_LENGTH}"):
        load_secret_key(settings_for(key_file))


def test_a_short_key_is_refused_without_repeating_it(tmp_path: Path) -> None:
    with pytest.raises(SecretKeyError, match="from ARESGATE_SECRET_KEY has 5 characters") as error:
        load_secret_key(settings_for(tmp_path / "none", "hunte"))
    assert "hunte" not in str(error.value)


def test_a_missing_file_says_where_to_put_the_key(tmp_path: Path) -> None:
    key_file = tmp_path / "missing.key"
    with pytest.raises(SecretKeyError, match="no app secret key") as error:
        load_secret_key(settings_for(key_file))
    assert "ARESGATE_SECRET_KEY" in str(error.value)
    assert str(key_file) in str(error.value)


def test_a_file_that_cannot_be_read_is_refused(tmp_path: Path) -> None:
    with pytest.raises(SecretKeyError):
        load_secret_key(settings_for(tmp_path))  # a directory
    key_file = tmp_path / "binary.key"
    key_file.write_bytes(b"\xff" * 40)
    with pytest.raises(SecretKeyError):
        load_secret_key(settings_for(key_file))


def test_the_start_up_check_passes_with_a_usable_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(secret_key, "get_settings", lambda: settings_for(tmp_path / "none", KEY))
    check_or_exit()


def test_the_start_up_check_stops_with_a_plain_message(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(secret_key, "get_settings", lambda: settings_for(tmp_path / "missing.key"))
    with pytest.raises(SystemExit, match=r"^aresgate: There is no app secret key"):
        check_or_exit()
