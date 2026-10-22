"""What signing in, signing out and setting up leave in the audit log."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import Action
from app.models import AuditEvent, User
from app.security import setup_code
from tests.helpers import ACCOUNT_PASSWORD, ACCOUNT_USERNAME, ORIGIN

BROWSER = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Firefox/150.0"}
SETUP_CODE = "K7QD-3MWX-9HPA"


def logged(session: Session) -> list[AuditEvent]:
    """Everything in the log, oldest first."""
    session.expire_all()
    return list(session.scalars(select(AuditEvent).order_by(AuditEvent.id)))


def log_in(client: TestClient, username: str = ACCOUNT_USERNAME, password: str = ACCOUNT_PASSWORD):
    return client.post(
        "/api/auth/login", json={"username": username, "password": password}, headers=BROWSER
    )


def test_signing_in_is_recorded(client: TestClient, account: User, session: Session) -> None:
    assert log_in(client).status_code == 200

    [event] = logged(session)
    assert (event.action, event.outcome) == (Action.LOGIN_SUCCEEDED, "success")
    assert (event.user_id, event.username) == (account.id, ACCOUNT_USERNAME)
    assert event.client_address == "testclient"
    assert event.user_agent == BROWSER["User-Agent"]
    assert event.detail is None


def test_a_wrong_password_is_recorded_against_the_account(
    client: TestClient, account: User, session: Session
) -> None:
    assert log_in(client, password="not it at all").status_code == 401

    [event] = logged(session)
    assert (event.action, event.outcome) == (Action.LOGIN_FAILED, "failure")
    assert (event.user_id, event.username) == (account.id, ACCOUNT_USERNAME)
    assert event.detail == {"reason": "wrong_password"}


def test_a_name_that_is_not_an_account_is_recorded_without_the_name(
    client: TestClient, account: User, session: Session
) -> None:
    # People sometimes type their password where the username goes.
    assert log_in(client, username="hunter2-is-my-password").status_code == 401

    [event] = logged(session)
    assert event.action == Action.LOGIN_FAILED
    assert (event.user_id, event.username) == (None, None)
    assert event.detail == {"reason": "unknown_account"}
    assert "hunter2" not in repr(vars(event))


def test_a_name_with_a_nul_in_it_is_just_a_wrong_name(
    client: TestClient, account: User, session: Session
) -> None:
    assert log_in(client, username="brian\x00").status_code == 401

    [event] = logged(session)
    assert event.detail == {"reason": "unknown_account"}


def test_the_password_is_never_in_the_log(
    client: TestClient, account: User, session: Session
) -> None:
    log_in(client, password="a wrong password worth finding")
    log_in(client)

    text = " ".join(repr(vars(event)) for event in logged(session))
    assert "worth finding" not in text
    assert ACCOUNT_PASSWORD not in text


def test_the_attempt_that_locks_the_account_says_for_how_long(
    client: TestClient, account: User, session: Session
) -> None:
    for _ in range(5):
        assert log_in(client, password="wrong").status_code == 401

    details = [event.detail for event in logged(session)]
    assert details[:4] == [{"reason": "wrong_password"}] * 4
    assert details[4] == {"reason": "wrong_password", "locked_for_seconds": 60}


def test_attempts_while_locked_out_are_not_added_to_the_log(
    client: TestClient, account: User, session: Session
) -> None:
    for _ in range(5):
        log_in(client, password="wrong")

    for _ in range(3):
        assert log_in(client).status_code == 429

    assert len(logged(session)) == 5


def test_signing_out_is_recorded(
    client: TestClient, csrf_token: str, account: User, session: Session
) -> None:
    response = client.post("/api/auth/logout", headers={**BROWSER, "X-CSRF-Token": csrf_token})

    assert response.status_code == 204
    signed_in, signed_out = logged(session)
    assert signed_in.action == Action.LOGIN_SUCCEEDED
    assert (signed_out.action, signed_out.outcome) == (Action.LOGOUT, "success")
    assert (signed_out.user_id, signed_out.username) == (account.id, ACCOUNT_USERNAME)
    assert signed_out.user_agent == BROWSER["User-Agent"]


def test_a_refused_sign_out_is_not_recorded(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    assert client.post("/api/auth/logout").status_code == 403

    assert [event.action for event in logged(session)] == [Action.LOGIN_SUCCEEDED]


def test_setting_up_is_recorded_for_the_new_account(client: TestClient, session: Session) -> None:
    setup_code.store(session, SETUP_CODE)
    session.commit()

    response = client.post(
        "/api/setup",
        json={"code": SETUP_CODE, "username": "Brian", "password": ACCOUNT_PASSWORD},
        headers=BROWSER,
    )

    assert response.status_code == 201
    [event] = logged(session)
    user = session.scalars(select(User)).one()
    assert (event.action, event.outcome) == (Action.SETUP_COMPLETED, "success")
    assert (event.user_id, event.username) == (user.id, "brian")
    assert event.user_agent == BROWSER["User-Agent"]


def test_a_wrong_setup_code_is_recorded(client: TestClient, session: Session) -> None:
    setup_code.store(session, SETUP_CODE)
    session.commit()

    response = client.post(
        "/api/setup",
        json={"code": "AAAA-AAAA-AAAA", "username": "Brian", "password": ACCOUNT_PASSWORD},
        headers=BROWSER,
    )

    assert response.status_code == 403
    [event] = logged(session)
    assert (event.action, event.outcome) == (Action.SETUP_CODE_REJECTED, "failure")
    assert (event.user_id, event.username) == (None, None)
    assert "AAAA" not in repr(vars(event))


def test_a_password_the_policy_refuses_is_not_recorded(
    client: TestClient, session: Session
) -> None:
    setup_code.store(session, SETUP_CODE)
    session.commit()

    response = client.post(
        "/api/setup",
        json={"code": SETUP_CODE, "username": "Brian", "password": "short"},
    )

    assert response.status_code == 422
    assert logged(session) == []


def test_the_address_is_the_one_the_request_came_from(
    app: FastAPI, account: User, session: Session
) -> None:
    with TestClient(
        app, base_url=ORIGIN, headers={"Origin": ORIGIN}, client=("203.0.113.9", 50000)
    ) as elsewhere:
        log_in(elsewhere)

    assert logged(session)[0].client_address == "203.0.113.9"
