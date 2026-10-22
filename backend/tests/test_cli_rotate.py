import io
import os
import stat
import sys
from pathlib import Path

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import cli, secret_key
from app.audit import Action, Outcome
from app.config import Settings
from app.models import AuditEvent, RecoveryCode, User, utcnow
from app.security import credential_store, rotation, totp, two_factor, vault
from app.security.credential_store import Kind
from tests.helpers import TEST_DATABASE_URL, turn_on_two_factor

OLD_KEY = "the old key, long enough to be used"
NEW_KEY = "a new key from a file, long enough"
API_KEY = "a-firewall-api-key-for-tests"


def read_key(key_file: Path) -> Settings:
    """Settings as AresGate would have them after the key file changed."""
    return Settings(environment="test", database_url=TEST_DATABASE_URL, secret_key_file=key_file)


@pytest.fixture
def key_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The key file of a container that made its own key, which is where the command reads and
    replaces it."""
    path = tmp_path / "secret.key"
    path.write_text(f"{OLD_KEY}\n")
    path.chmod(0o400)
    monkeypatch.setattr(secret_key, "DEFAULT_SECRET_KEY_FILE", path)
    monkeypatch.setattr(cli, "get_settings", lambda: read_key(path))
    return path


@pytest.fixture
def supplied_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    """A key that came in the environment, so the command can't keep a new one."""
    settings = Settings(
        environment="test",
        database_url=TEST_DATABASE_URL,
        secret_key=SecretStr(OLD_KEY),
        secret_key_file=tmp_path / "nothing-here",
    )
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    return settings


def fill(session: Session, settings: Settings, account: User) -> str:
    credential_store.store(
        session, settings, Kind.INTEGRATION, "opnsense", "api_key", API_KEY, utcnow()
    )
    secret, _ = turn_on_two_factor(session, settings, account)
    return secret


def kept(session: Session, settings: Settings) -> str | None:
    session.expire_all()
    return credential_store.reveal(session, settings, Kind.INTEGRATION, "opnsense", "api_key")


def test_it_makes_a_new_key_and_seals_everything_again(
    command_line: None,
    key_file: Path,
    session: Session,
    account: User,
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret = fill(session, read_key(key_file), account)

    assert cli.rotate_secret_key(None) == 0

    new = read_key(key_file)
    new_key = secret_key.load_secret_key(new).get_secret_value()
    assert new_key != OLD_KEY
    assert len(new_key) >= secret_key.MIN_LENGTH
    assert kept(session, new) == API_KEY
    now = utcnow()
    code = totp.code_for(secret, totp.current_period(now) + 1)
    assert two_factor.accept_code(session, new, account.id, code, now) is not None
    old = Settings(secret_key=SecretStr(OLD_KEY))
    with pytest.raises(vault.VaultError):
        kept(session, old)
    output = capsys.readouterr()
    assert "Sealed 1 credentials and 1 authenticator keys again" in output.out
    assert "10 recovery codes" in output.out
    assert f"The new key is in {key_file}" in output.out
    assert output.err == ""
    assert new_key not in output.out
    assert OLD_KEY not in output.out


def test_the_new_key_file_is_private_and_nothing_is_left_beside_it(
    command_line: None, key_file: Path, session: Session, account: User
) -> None:
    fill(session, read_key(key_file), account)

    cli.rotate_secret_key(None)

    assert stat.S_IMODE(key_file.stat().st_mode) == 0o400
    assert sorted(path.name for path in key_file.parent.iterdir()) == ["secret.key"]


def test_it_leaves_an_event_in_the_audit_log_that_says_how_much_changed(
    command_line: None, key_file: Path, session: Session, account: User
) -> None:
    fill(session, read_key(key_file), account)

    cli.rotate_secret_key(None)

    session.expire_all()
    [event] = session.scalars(
        select(AuditEvent).where(AuditEvent.action == Action.KEY_ROTATED.value)
    )
    assert event.outcome == Outcome.SUCCESS.value
    assert event.user_agent == "command line"
    assert event.detail == {
        "by": "command_line",
        "credentials": 1,
        "authenticator_keys": 1,
        "recovery_codes_removed": 10,
    }
    new_key = secret_key.load_secret_key(read_key(key_file)).get_secret_value()
    assert new_key not in str(event.detail)


def test_a_rotation_with_nothing_stored_still_changes_the_key(
    command_line: None,
    key_file: Path,
    session: Session,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.rotate_secret_key(None) == 0

    assert secret_key.load_secret_key(read_key(key_file)).get_secret_value() != OLD_KEY
    output = capsys.readouterr().out
    assert "Sealed 0 credentials and 0 authenticator keys" in output
    assert "recovery codes" not in output


def test_the_new_key_can_come_from_a_file(
    command_line: None, key_file: Path, tmp_path: Path, session: Session, account: User
) -> None:
    fill(session, read_key(key_file), account)
    chosen = tmp_path / "chosen.key"
    chosen.write_text(f"{NEW_KEY}\n")

    assert cli.rotate_secret_key(chosen) == 0

    assert key_file.read_text().strip() == NEW_KEY
    assert kept(session, read_key(key_file)) == API_KEY


def test_the_new_key_can_come_from_standard_input(
    command_line: None,
    key_file: Path,
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
    account: User,
) -> None:
    fill(session, read_key(key_file), account)
    monkeypatch.setattr(sys, "stdin", io.StringIO(f"{NEW_KEY}\n"))

    assert cli.main(["rotate-secret-key", "--new-key-file", "-"]) == 0

    assert key_file.read_text().strip() == NEW_KEY
    assert kept(session, read_key(key_file)) == API_KEY


def test_a_key_from_standard_input_that_is_too_short_is_refused(
    command_line: None,
    key_file: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO("short"))

    assert cli.main(["rotate-secret-key", "--new-key-file", "-"]) == 1

    assert "from standard input has 5 characters" in capsys.readouterr().err


def test_standard_input_that_cannot_be_read_is_reported(
    command_line: None,
    key_file: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"\xff\xfe not text"), "utf-8"))

    assert cli.main(["rotate-secret-key", "--new-key-file", "-"]) == 1

    assert "Can't read the new key from standard input" in capsys.readouterr().err


def test_a_key_that_is_too_short_is_refused_before_anything_changes(
    command_line: None,
    key_file: Path,
    tmp_path: Path,
    session: Session,
    account: User,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fill(session, read_key(key_file), account)
    short = tmp_path / "short.key"
    short.write_text("too short")

    assert cli.rotate_secret_key(short) == 1

    assert f"needs at least {secret_key.MIN_LENGTH}" in capsys.readouterr().err
    assert key_file.read_text().strip() == OLD_KEY
    assert kept(session, read_key(key_file)) == API_KEY


def test_a_key_file_that_cannot_be_read_is_reported(
    command_line: None, key_file: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.rotate_secret_key(tmp_path / "missing.key") == 1

    assert "Can't read the new key from" in capsys.readouterr().err
    assert key_file.read_text().strip() == OLD_KEY


def test_the_same_key_is_not_a_rotation(
    command_line: None, key_file: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    same = tmp_path / "same.key"
    same.write_text(OLD_KEY)

    assert cli.rotate_secret_key(same) == 1

    assert "already uses" in capsys.readouterr().err


def test_without_a_current_key_it_says_so(
    command_line: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing = read_key(tmp_path / "no-such-file")
    monkeypatch.setattr(cli, "get_settings", lambda: missing)

    assert cli.rotate_secret_key(None) == 1

    assert "There is no app secret key" in capsys.readouterr().err


def test_a_supplied_key_needs_the_new_one_in_a_file(
    command_line: None,
    supplied_key: Settings,
    session: Session,
    account: User,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fill(session, supplied_key, account)

    assert cli.rotate_secret_key(None) == 1

    assert "--new-key-file" in capsys.readouterr().err
    assert kept(session, supplied_key) == API_KEY


def test_a_supplied_key_is_resealed_and_left_for_the_operator_to_replace(
    command_line: None,
    supplied_key: Settings,
    tmp_path: Path,
    session: Session,
    account: User,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fill(session, supplied_key, account)
    chosen = tmp_path / "chosen.key"
    chosen.write_text(NEW_KEY)

    assert cli.rotate_secret_key(chosen) == 0

    assert kept(session, Settings(secret_key=SecretStr(NEW_KEY))) == API_KEY
    output = capsys.readouterr()
    assert "restart AresGate" in output.out
    assert "The new key is in" not in output.out
    assert not (tmp_path / "nothing-here").exists()


def test_a_value_that_cannot_be_opened_stops_it_and_changes_nothing(
    command_line: None,
    key_file: Path,
    session: Session,
    account: User,
    capsys: pytest.CaptureFixture[str],
) -> None:
    current = read_key(key_file)
    fill(session, current, account)
    elsewhere = Settings(secret_key=SecretStr("a key that sealed this somewhere else"))
    credential_store.store(
        session, elsewhere, Kind.AI_PROVIDER, "anthropic", "api_key", "x", utcnow()
    )
    session.commit()

    assert cli.rotate_secret_key(None) == 1

    assert "Nothing was changed. The ai_provider secret anthropic/api_key" in (
        capsys.readouterr().err
    )
    assert key_file.read_text().strip() == OLD_KEY
    assert sorted(path.name for path in key_file.parent.iterdir()) == ["secret.key"]
    assert kept(session, current) == API_KEY
    assert session.scalar(select(func.count()).select_from(RecoveryCode)) == 10
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0


def test_an_unexpected_failure_leaves_the_old_key_and_no_stray_file(
    command_line: None,
    key_file: Path,
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
    account: User,
) -> None:
    fill(session, read_key(key_file), account)

    def fail(*_: object) -> rotation.Rotated:
        raise RuntimeError("the database went away")

    monkeypatch.setattr(rotation, "rotate", fail)

    with pytest.raises(RuntimeError, match="went away"):
        cli.rotate_secret_key(None)

    assert key_file.read_text().strip() == OLD_KEY
    assert sorted(path.name for path in key_file.parent.iterdir()) == ["secret.key"]


def test_what_an_earlier_rotation_left_behind_is_not_overwritten(
    command_line: None,
    key_file: Path,
    session: Session,
    account: User,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fill(session, read_key(key_file), account)
    leftover = key_file.with_name("secret.key.new")
    leftover.write_text("from an earlier try")

    assert cli.rotate_secret_key(None) == 1

    assert "earlier rotation was cut short" in capsys.readouterr().err
    assert leftover.read_text() == "from an earlier try"
    assert kept(session, read_key(key_file)) == API_KEY


def test_a_key_file_that_cannot_be_written_beside_is_reported(
    command_line: None,
    key_file: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:

    def refuse(*_: object) -> int:
        raise PermissionError("read-only")

    monkeypatch.setattr(os, "open", refuse)

    assert cli.rotate_secret_key(None) == 1

    assert "Can't save the new key next to" in capsys.readouterr().err


def test_if_the_key_file_cannot_be_replaced_the_new_key_is_kept_and_named(
    command_line: None,
    key_file: Path,
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
    account: User,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fill(session, read_key(key_file), account)

    def refuse(*_: object) -> None:
        raise OSError("device busy")

    monkeypatch.setattr(os, "replace", refuse)

    assert cli.rotate_secret_key(None) == 1

    staged = key_file.with_name("secret.key.new")
    error = capsys.readouterr().err
    assert f"The new key is in {staged}" in error
    assert "device busy" in error
    # The secrets are sealed with the key in that file, which is what the message says to use.
    new = Settings(environment="test", secret_key=SecretStr(staged.read_text().strip()))
    assert kept(session, new) == API_KEY


def test_main_runs_the_rotation(
    command_line: None, key_file: Path, tmp_path: Path, session: Session, account: User
) -> None:
    fill(session, read_key(key_file), account)
    chosen = tmp_path / "chosen.key"
    chosen.write_text(NEW_KEY)

    assert cli.main(["rotate-secret-key", "--new-key-file", str(chosen)]) == 0

    assert key_file.read_text().strip() == NEW_KEY
