from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api import auth as auth_api
from app.api import two_factor as two_factor_api
from app.audit import Action, Outcome
from app.config import Settings
from app.models import (
    AuditEvent,
    LoginThrottle,
    RecoveryCode,
    TotpCredential,
    User,
    UserSession,
    utcnow,
)
from app.security import totp, two_factor, vault
from tests.helpers import ACCOUNT_PASSWORD, ACCOUNT_USERNAME
from tests.test_auth_api import COOKIE, log_in

BASE = "/api/auth/two-factor"


class Clock:
    """The time the API sees, which a test moves on so that it can take one code after another:
    an authenticator code is good for one use."""

    def __init__(self) -> None:
        self.now = utcnow()

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float = totp.PERIOD_SECONDS) -> None:
        self.now += timedelta(seconds=seconds)

    def code(self, secret: str) -> str:
        return totp.code_for(secret, totp.current_period(self.now))


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    clock = Clock()
    monkeypatch.setattr(auth_api, "utcnow", clock)
    monkeypatch.setattr(two_factor_api, "utcnow", clock)
    return clock


def post(client: TestClient, path: str, token: str, **body: object) -> Response:
    return client.post(f"{BASE}{path}", json=body, headers={"X-CSRF-Token": token})


@pytest.fixture
def enrolled(client: TestClient, csrf_token: str, clock: Clock) -> tuple[str, list[str]]:
    """The signed-in account with an authenticator app on, and the codes it was given. The
    clock has moved on, so the app's next code is good."""
    secret = post(client, "/enroll", csrf_token).json()["secret"]
    codes = post(client, "/confirm", csrf_token, code=clock.code(secret)).json()["recovery_codes"]
    clock.advance()
    return secret, codes


def audit_events(session: Session, action: Action) -> list[AuditEvent]:
    session.expire_all()
    return list(
        session.scalars(
            select(AuditEvent).where(AuditEvent.action == action.value).order_by(AuditEvent.id)
        )
    )


def sign_out_and_in_again(client: TestClient) -> Response:
    client.cookies.clear()
    return log_in(client)


def second_step(client: TestClient, challenge: str, code: str) -> Response:
    return client.post("/api/auth/login/two-factor", json={"challenge": challenge, "code": code})


def challenge_for(client: TestClient) -> str:
    response = log_in(client)
    assert response.status_code == 200
    assert response.json()["two_factor_required"] is True
    return str(response.json()["challenge"])


# ---- Looking at it, and the routes needing a sign-in -------------------------------------


def test_the_status_of_an_account_without_one(client: TestClient, csrf_token: str) -> None:
    response = client.get(BASE)

    assert response.status_code == 200
    assert response.json() == {"enabled": False, "recovery_codes_left": 0}


def test_the_status_of_an_account_with_one(
    client: TestClient, enrolled: tuple[str, list[str]]
) -> None:
    assert client.get(BASE).json() == {"enabled": True, "recovery_codes_left": 10}


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", ""),
        ("POST", "/enroll"),
        ("POST", "/confirm"),
        ("POST", "/recovery-codes"),
        ("POST", "/disable"),
    ],
)
def test_every_route_needs_a_sign_in(client: TestClient, method: str, path: str) -> None:
    response = client.request(method, f"{BASE}{path}", json={"code": "123456", "password": "x"})

    assert response.status_code == 401


@pytest.mark.parametrize("path", ["/enroll", "/confirm", "/recovery-codes", "/disable"])
def test_a_change_needs_the_security_token(client: TestClient, csrf_token: str, path: str) -> None:
    response = client.post(f"{BASE}{path}", json={"code": "123456", "password": "x"})

    assert response.status_code == 403


# ---- Adding an authenticator app ---------------------------------------------------------


def test_enrolling_gives_a_key_and_an_address_for_a_qr_code(
    client: TestClient, csrf_token: str
) -> None:
    response = post(client, "/enroll", csrf_token)

    assert response.status_code == 201
    body = response.json()
    assert len(body["secret"]) == 32
    assert body["otpauth_uri"].startswith(f"otpauth://totp/AresGate:{ACCOUNT_USERNAME}?")
    assert f"secret={body['secret']}" in body["otpauth_uri"]


def test_a_key_that_is_not_confirmed_changes_nothing_about_signing_in(
    client: TestClient, csrf_token: str
) -> None:
    post(client, "/enroll", csrf_token)

    assert client.get(BASE).json()["enabled"] is False
    assert sign_out_and_in_again(client).json()["username"] == ACCOUNT_USERNAME


def test_enrolling_again_before_confirming_makes_a_new_key(
    client: TestClient, csrf_token: str, clock: Clock
) -> None:
    first = post(client, "/enroll", csrf_token).json()["secret"]
    second = post(client, "/enroll", csrf_token).json()["secret"]

    assert first != second
    assert post(client, "/confirm", csrf_token, code=clock.code(first)).status_code == 422
    assert post(client, "/confirm", csrf_token, code=clock.code(second)).status_code == 200


def test_the_right_code_turns_it_on_and_shows_the_recovery_codes(
    client: TestClient, csrf_token: str, clock: Clock, session: Session
) -> None:
    secret = post(client, "/enroll", csrf_token).json()["secret"]

    response = post(client, "/confirm", csrf_token, code=clock.code(secret))

    assert response.status_code == 200
    codes = response.json()["recovery_codes"]
    assert len(set(codes)) == 10
    assert all(len(code) == 14 and code.count("-") == 2 for code in codes)
    assert client.get(BASE).json() == {"enabled": True, "recovery_codes_left": 10}
    [event] = audit_events(session, Action.TWO_FACTOR_ENABLED)
    assert (event.outcome, event.username) == (Outcome.SUCCESS.value, ACCOUNT_USERNAME)
    # The codes are shown once: asking again doesn't repeat them.
    assert "recovery_codes" not in client.get(BASE).json()


def test_nothing_secret_goes_in_the_audit_log(
    client: TestClient, csrf_token: str, clock: Clock, session: Session
) -> None:
    secret = post(client, "/enroll", csrf_token).json()["secret"]
    codes = post(client, "/confirm", csrf_token, code=clock.code(secret)).json()["recovery_codes"]

    everything = " ".join(
        f"{event.action} {event.detail}" for event in session.scalars(select(AuditEvent))
    )
    assert secret not in everything
    assert not any(code in everything for code in codes)


def test_a_wrong_code_leaves_it_off(client: TestClient, csrf_token: str, clock: Clock) -> None:
    secret = post(client, "/enroll", csrf_token).json()["secret"]
    wrong = totp.code_for(secret, totp.current_period(clock.now) + 10)

    response = post(client, "/confirm", csrf_token, code=wrong)

    assert response.status_code == 422
    assert "isn't right" in response.json()["detail"]
    assert client.get(BASE).json() == {"enabled": False, "recovery_codes_left": 0}


def test_confirming_without_starting_is_refused(client: TestClient, csrf_token: str) -> None:
    response = post(client, "/confirm", csrf_token, code="123456")

    assert response.status_code == 409
    assert "Start adding" in response.json()["detail"]


def test_a_second_app_cannot_be_added_while_one_is_on(
    client: TestClient, csrf_token: str, enrolled: tuple[str, list[str]]
) -> None:
    response = post(client, "/enroll", csrf_token)

    assert response.status_code == 409
    assert "already set up" in response.json()["detail"]


def test_the_codes_in_a_request_are_limited_in_length(client: TestClient, csrf_token: str) -> None:
    assert post(client, "/confirm", csrf_token, code="1" * 65).status_code == 422


# ---- Signing in with it ------------------------------------------------------------------


def test_the_password_alone_no_longer_signs_in(
    client: TestClient, enrolled: tuple[str, list[str]], session: Session
) -> None:
    client.cookies.clear()

    response = log_in(client)

    assert response.status_code == 200
    body = response.json()
    assert body["two_factor_required"] is True
    assert body["challenge"]
    assert set(body) == {"two_factor_required", "challenge"}
    assert COOKIE not in client.cookies
    assert client.get("/api/auth/session").status_code == 401
    # Only the sign-in from before is a session; this one has not made one.
    assert session.scalar(select(func.count()).select_from(UserSession)) == 1


def test_a_wrong_password_looks_the_same_with_or_without_it(
    client: TestClient, enrolled: tuple[str, list[str]]
) -> None:
    client.cookies.clear()

    response = log_in(client, password="wrong")

    assert response.status_code == 401
    assert response.json() == {"detail": "Incorrect username or password."}


def test_the_code_from_the_app_finishes_signing_in(
    client: TestClient, enrolled: tuple[str, list[str]], clock: Clock, session: Session
) -> None:
    secret, _ = enrolled
    client.cookies.clear()
    challenge = challenge_for(client)

    response = second_step(client, challenge, clock.code(secret))

    assert response.status_code == 200
    assert response.json()["username"] == ACCOUNT_USERNAME
    assert client.get("/api/auth/session").json()["username"] == ACCOUNT_USERNAME
    [event] = [
        event
        for event in audit_events(session, Action.LOGIN_SUCCEEDED)
        if event.detail and "second_factor" in event.detail
    ]
    assert event.detail == {"second_factor": "authenticator"}


def test_a_code_works_once(
    client: TestClient, enrolled: tuple[str, list[str]], clock: Clock
) -> None:
    secret, _ = enrolled
    client.cookies.clear()
    code = clock.code(secret)
    assert second_step(client, challenge_for(client), code).status_code == 200

    client.cookies.clear()
    response = second_step(client, challenge_for(client), code)

    assert response.status_code == 401
    assert response.json() == {"detail": "That code isn't right."}


def test_a_recovery_code_finishes_signing_in_once(
    client: TestClient, enrolled: tuple[str, list[str]], session: Session
) -> None:
    _, codes = enrolled
    client.cookies.clear()
    assert second_step(client, challenge_for(client), codes[0]).status_code == 200
    [event] = [
        event
        for event in audit_events(session, Action.LOGIN_SUCCEEDED)
        if event.detail and "second_factor" in event.detail
    ]
    assert event.detail == {"second_factor": "recovery_code", "recovery_codes_left": 9}

    client.cookies.clear()
    assert second_step(client, challenge_for(client), codes[0]).status_code == 401
    assert second_step(client, challenge_for(client), codes[1]).status_code == 200
    assert client.get(BASE).json() == {"enabled": True, "recovery_codes_left": 8}


def test_a_wrong_code_is_refused_and_counted(
    client: TestClient, enrolled: tuple[str, list[str]], session: Session
) -> None:
    client.cookies.clear()

    response = second_step(client, challenge_for(client), "000000")

    assert response.status_code == 401
    assert COOKIE not in client.cookies
    [event] = audit_events(session, Action.TWO_FACTOR_FAILED)
    assert (event.outcome, event.detail) == (Outcome.FAILURE.value, {"reason": "wrong_code"})
    assert session.scalar(select(func.count()).select_from(LoginThrottle)) == 2


def test_five_wrong_codes_lock_even_the_right_one_out(
    client: TestClient, enrolled: tuple[str, list[str]], clock: Clock, session: Session
) -> None:
    secret, _ = enrolled
    client.cookies.clear()
    challenge = challenge_for(client)
    for _ in range(5):
        assert second_step(client, challenge, "000000").status_code == 401

    response = second_step(client, challenge, clock.code(secret))

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"
    assert COOKIE not in client.cookies
    last = audit_events(session, Action.TWO_FACTOR_FAILED)[-1]
    assert last.detail == {"reason": "wrong_code", "locked_for_seconds": 60}
    # The password page is locked the same way.
    assert log_in(client).status_code == 429


def test_the_wait_ends_and_the_code_works_again(
    client: TestClient, enrolled: tuple[str, list[str]], clock: Clock
) -> None:
    secret, _ = enrolled
    client.cookies.clear()
    challenge = challenge_for(client)
    for _ in range(5):
        second_step(client, challenge, "000000")

    clock.advance(61)

    assert second_step(client, challenge, clock.code(secret)).status_code == 200


def test_a_right_password_does_not_wipe_the_wrong_guesses(
    client: TestClient, enrolled: tuple[str, list[str]], clock: Clock, session: Session
) -> None:
    secret, _ = enrolled
    client.cookies.clear()
    challenge = challenge_for(client)
    for _ in range(3):
        second_step(client, challenge, "000000")

    # Someone who knows the password signs in again, hoping the count starts over.
    challenge_for(client)

    assert [row.failures for row in session.scalars(select(LoginThrottle))] == [3, 3]
    assert second_step(client, challenge, clock.code(secret)).status_code == 200
    session.expire_all()
    assert session.scalar(select(func.count()).select_from(LoginThrottle)) == 0


def test_a_wrong_password_still_counts_towards_the_lockout(
    client: TestClient, enrolled: tuple[str, list[str]]
) -> None:
    client.cookies.clear()
    for _ in range(5):
        assert log_in(client, password="wrong").status_code == 401

    assert log_in(client).status_code == 429


def test_a_challenge_that_was_never_made_is_refused(
    client: TestClient, enrolled: tuple[str, list[str]], clock: Clock
) -> None:
    secret, _ = enrolled
    client.cookies.clear()

    response = second_step(client, "made.up.challenge", clock.code(secret))

    assert response.status_code == 401
    assert "timed out" in response.json()["detail"]
    assert COOKIE not in client.cookies


def test_a_challenge_stops_working_after_five_minutes(
    client: TestClient, enrolled: tuple[str, list[str]], clock: Clock
) -> None:
    secret, _ = enrolled
    client.cookies.clear()
    challenge = challenge_for(client)

    clock.advance(5 * 60)

    response = second_step(client, challenge, clock.code(secret))
    assert response.status_code == 401
    assert "timed out" in response.json()["detail"]


def test_a_challenge_for_an_account_that_has_gone_is_refused(
    client: TestClient,
    enrolled: tuple[str, list[str]],
    clock: Clock,
    session: Session,
    account: User,
) -> None:
    secret, _ = enrolled
    client.cookies.clear()
    challenge = challenge_for(client)
    session.delete(account)
    session.commit()

    assert second_step(client, challenge, clock.code(secret)).status_code == 401


def test_the_challenge_does_not_work_on_an_account_without_a_code(
    client: TestClient, csrf_token: str, settings: Settings, account: User, clock: Clock
) -> None:
    client.cookies.clear()
    challenge = two_factor.make_challenge(settings, account.id, clock.now)

    assert second_step(client, challenge, "123456").status_code == 401


def test_the_second_step_needs_both_fields(client: TestClient, csrf_token: str) -> None:
    assert client.post("/api/auth/login/two-factor", json={"code": "1"}).status_code == 422
    body = {"challenge": "x" * 513, "code": "1"}
    assert client.post("/api/auth/login/two-factor", json=body).status_code == 422
    body = {"challenge": "x", "code": "1" * 65}
    assert client.post("/api/auth/login/two-factor", json=body).status_code == 422


# ---- New recovery codes ------------------------------------------------------------------


def test_new_recovery_codes_end_the_old_ones(
    client: TestClient,
    csrf_token: str,
    enrolled: tuple[str, list[str]],
    clock: Clock,
    session: Session,
) -> None:
    secret, old = enrolled

    response = post(client, "/recovery-codes", csrf_token, code=clock.code(secret))

    assert response.status_code == 200
    new = response.json()["recovery_codes"]
    assert len(set(new)) == 10
    assert not set(new) & set(old)
    assert session.scalar(select(func.count()).select_from(RecoveryCode)) == 10
    assert client.get(BASE).json() == {"enabled": True, "recovery_codes_left": 10}
    [event] = audit_events(session, Action.RECOVERY_CODES_CREATED)
    assert event.outcome == Outcome.SUCCESS.value
    client.cookies.clear()
    assert second_step(client, challenge_for(client), old[0]).status_code == 401
    assert second_step(client, challenge_for(client), new[0]).status_code == 200


def test_a_recovery_code_will_do_to_make_new_ones(
    client: TestClient, csrf_token: str, enrolled: tuple[str, list[str]]
) -> None:
    _, old = enrolled

    response = post(client, "/recovery-codes", csrf_token, code=old[0])

    assert response.status_code == 200


def test_new_recovery_codes_need_a_right_code(
    client: TestClient,
    csrf_token: str,
    enrolled: tuple[str, list[str]],
    session: Session,
) -> None:
    _, old = enrolled

    response = post(client, "/recovery-codes", csrf_token, code="000000")

    # 403, not 401, which the web app takes to mean the sign-in has ended.
    assert response.status_code == 403
    assert response.json() == {"detail": "That isn't right."}
    assert client.get("/api/auth/session").status_code == 200
    [event] = audit_events(session, Action.TWO_FACTOR_FAILED)
    assert event.detail == {"reason": "wrong_password_or_code", "while": "new_recovery_codes"}
    assert two_factor.recovery_codes_left(session, event.user_id) == 10  # type: ignore[arg-type]
    assert old


def test_new_recovery_codes_need_an_authenticator_app(client: TestClient, csrf_token: str) -> None:
    response = post(client, "/recovery-codes", csrf_token, code="123456")

    assert response.status_code == 409
    assert response.json() == {"detail": "There is no authenticator app set up."}


def test_guessing_codes_here_locks_like_at_sign_in(
    client: TestClient, csrf_token: str, enrolled: tuple[str, list[str]], clock: Clock
) -> None:
    secret, _ = enrolled
    for _ in range(5):
        assert post(client, "/recovery-codes", csrf_token, code="000000").status_code == 403

    response = post(client, "/recovery-codes", csrf_token, code=clock.code(secret))

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"
    client.cookies.clear()
    assert log_in(client).status_code == 429


# ---- Turning it off ----------------------------------------------------------------------


def test_the_password_and_a_code_turn_it_off(
    client: TestClient,
    csrf_token: str,
    enrolled: tuple[str, list[str]],
    clock: Clock,
    session: Session,
) -> None:
    secret, _ = enrolled

    response = post(
        client, "/disable", csrf_token, password=ACCOUNT_PASSWORD, code=clock.code(secret)
    )

    assert response.status_code == 204
    assert client.get(BASE).json() == {"enabled": False, "recovery_codes_left": 0}
    [event] = audit_events(session, Action.TWO_FACTOR_DISABLED)
    assert (event.outcome, event.username) == (Outcome.SUCCESS.value, ACCOUNT_USERNAME)
    assert event.detail is None
    # The password alone signs in again.
    assert sign_out_and_in_again(client).json()["username"] == ACCOUNT_USERNAME


def test_a_recovery_code_will_do_to_turn_it_off(
    client: TestClient, csrf_token: str, enrolled: tuple[str, list[str]]
) -> None:
    _, codes = enrolled

    response = post(client, "/disable", csrf_token, password=ACCOUNT_PASSWORD, code=codes[0])

    assert response.status_code == 204


def test_a_wrong_password_refuses_and_keeps_the_code_unused(
    client: TestClient,
    csrf_token: str,
    enrolled: tuple[str, list[str]],
    clock: Clock,
    session: Session,
) -> None:
    secret, codes = enrolled
    code = clock.code(secret)

    refused = post(client, "/disable", csrf_token, password="wrong", code=code)
    refused_recovery = post(client, "/disable", csrf_token, password="wrong", code=codes[0])

    assert refused.status_code == refused_recovery.status_code == 403
    assert refused.json() == {"detail": "The password or the code isn't right."}
    assert client.get("/api/auth/session").status_code == 200
    assert client.get(BASE).json() == {"enabled": True, "recovery_codes_left": 10}
    events = audit_events(session, Action.TWO_FACTOR_FAILED)
    assert [event.detail for event in events] == [
        {"reason": "wrong_password_or_code", "while": "turning_off"}
    ] * 2
    # Both are still good, since the password was wrong before they were looked at.
    assert (
        post(client, "/disable", csrf_token, password=ACCOUNT_PASSWORD, code=code).status_code
        == 204
    )


def test_a_wrong_code_refuses(
    client: TestClient, csrf_token: str, enrolled: tuple[str, list[str]]
) -> None:
    response = post(client, "/disable", csrf_token, password=ACCOUNT_PASSWORD, code="000000")

    assert response.status_code == 403
    assert client.get(BASE).json()["enabled"] is True


def test_the_same_code_cannot_be_used_twice_in_a_row(
    client: TestClient, csrf_token: str, enrolled: tuple[str, list[str]], clock: Clock
) -> None:
    secret, _ = enrolled
    code = clock.code(secret)
    assert post(client, "/recovery-codes", csrf_token, code=code).status_code == 200

    response = post(client, "/disable", csrf_token, password=ACCOUNT_PASSWORD, code=code)

    assert response.status_code == 403


def test_turning_it_off_needs_it_to_be_on(client: TestClient, csrf_token: str) -> None:
    response = post(client, "/disable", csrf_token, password=ACCOUNT_PASSWORD, code="123456")

    assert response.status_code == 409


def test_guessing_the_password_here_locks_like_at_sign_in(
    client: TestClient, csrf_token: str, enrolled: tuple[str, list[str]], clock: Clock
) -> None:
    secret, _ = enrolled
    for _ in range(5):
        post(client, "/disable", csrf_token, password="wrong", code=clock.code(secret))

    response = post(
        client, "/disable", csrf_token, password=ACCOUNT_PASSWORD, code=clock.code(secret)
    )

    assert response.status_code == 429


def test_the_request_to_turn_it_off_needs_both_fields(client: TestClient, csrf_token: str) -> None:
    assert post(client, "/disable", csrf_token, code="1").status_code == 422
    assert post(client, "/disable", csrf_token, password="x" * 1025, code="1").status_code == 422


# ---- Keeping the key safe ----------------------------------------------------------------


def test_the_database_holds_neither_the_key_nor_the_codes(
    client: TestClient,
    enrolled: tuple[str, list[str]],
    session: Session,
    settings: Settings,
    account: User,
) -> None:
    secret, codes = enrolled

    session.expire_all()
    sealed = session.scalars(select(TotpCredential.secret_sealed)).one()
    hashes = " ".join(session.scalars(select(RecoveryCode.code_hash)))
    assert secret not in sealed
    assert vault.unseal(settings, "authenticator-key", sealed, str(account.id)).decode() == secret
    assert not any(code in hashes or code.replace("-", "") in hashes for code in codes)
