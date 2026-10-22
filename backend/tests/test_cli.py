import runpy
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import cli
from app.audit import Action, Outcome
from app.config import Settings
from app.models import AuditEvent, RecoveryCode, TotpCredential, User, UserSession
from app.security import two_factor
from tests.helpers import ACCOUNT_USERNAME, turn_on_two_factor


def test_it_takes_the_authenticator_app_off(
    command_line: None,
    session: Session,
    settings: Settings,
    account: User,
    capsys: pytest.CaptureFixture[str],
) -> None:
    turn_on_two_factor(session, settings, account)

    assert cli.disable_two_factor(ACCOUNT_USERNAME) == 0

    session.expire_all()
    assert not two_factor.is_enabled(session, account.id)
    assert session.scalar(select(func.count()).select_from(TotpCredential)) == 0
    assert session.scalar(select(func.count()).select_from(RecoveryCode)) == 0
    output = capsys.readouterr()
    assert f"Turned off the authenticator app for {ACCOUNT_USERNAME}" in output.out
    assert output.err == ""


def test_it_leaves_an_event_in_the_audit_log(
    command_line: None, session: Session, settings: Settings, account: User
) -> None:
    turn_on_two_factor(session, settings, account)

    cli.disable_two_factor(ACCOUNT_USERNAME)

    session.expire_all()
    [event] = session.scalars(
        select(AuditEvent).where(AuditEvent.action == Action.TWO_FACTOR_DISABLED.value)
    )
    assert event.outcome == Outcome.SUCCESS.value
    assert (event.user_id, event.username) == (account.id, ACCOUNT_USERNAME)
    assert event.user_agent == "command line"
    assert event.client_address is None
    assert event.detail == {"by": "command_line"}


def test_it_ends_the_accounts_sign_ins(
    command_line: None,
    client: TestClient,
    csrf_token: str,
    session: Session,
    settings: Settings,
    account: User,
) -> None:
    turn_on_two_factor(session, settings, account)
    assert client.get("/api/auth/session").status_code == 200

    cli.disable_two_factor(ACCOUNT_USERNAME)

    assert client.get("/api/auth/session").status_code == 401
    session.expire_all()
    assert session.scalar(select(func.count()).select_from(UserSession)) == 0


def test_the_name_is_matched_like_at_sign_in(
    command_line: None, session: Session, settings: Settings, account: User
) -> None:
    turn_on_two_factor(session, settings, account)

    assert cli.disable_two_factor(f"  {ACCOUNT_USERNAME.upper()} ") == 0


def test_an_unknown_account_is_reported(
    command_line: None, account: User, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.disable_two_factor("nobody") == 1

    output = capsys.readouterr()
    assert output.out == ""
    assert "There is no account called 'nobody'." in output.err


def test_an_account_without_one_is_reported_and_left_alone(
    command_line: None, session: Session, account: User, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.disable_two_factor(ACCOUNT_USERNAME) == 1

    output = capsys.readouterr()
    assert output.out == ""
    assert f"{ACCOUNT_USERNAME} hasn't turned on an authenticator app." in output.err
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0


def test_main_runs_the_command_it_is_given(
    command_line: None, session: Session, settings: Settings, account: User
) -> None:
    turn_on_two_factor(session, settings, account)

    assert cli.main(["disable-two-factor", ACCOUNT_USERNAME]) == 0

    session.expire_all()
    assert not two_factor.is_enabled(session, account.id)


@pytest.mark.parametrize("arguments", [[], ["unknown-command"], ["disable-two-factor"]])
def test_main_refuses_what_it_does_not_know(arguments: list[str]) -> None:
    with pytest.raises(SystemExit) as stopped:
        cli.main(arguments)

    assert stopped.value.code == 2


@pytest.mark.filterwarnings("ignore:.*found in sys.modules:RuntimeWarning")
def test_it_runs_as_a_module(
    command_line: None, monkeypatch: pytest.MonkeyPatch, account: User
) -> None:
    monkeypatch.setattr(sys, "argv", ["app.cli", "disable-two-factor", ACCOUNT_USERNAME])

    with pytest.raises(SystemExit) as stopped:
        runpy.run_module("app.cli", run_name="__main__")

    # The account has no authenticator app, which is reported with a 1.
    assert stopped.value.code == 1
