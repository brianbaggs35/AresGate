import hashlib
from datetime import datetime, timedelta

import pytest
from argon2 import PasswordHasher
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import LoginThrottle, User, UserSession, utcnow
from app.security import passwords, sessions
from tests.helpers import ACCOUNT_PASSWORD, ACCOUNT_USERNAME, ORIGIN

COOKIE = sessions.COOKIE_NAME


def log_in(
    client: TestClient, username: str = ACCOUNT_USERNAME, password: str = ACCOUNT_PASSWORD
) -> Response:
    return client.post("/api/auth/login", json={"username": username, "password": password})


def from_address(app: FastAPI, address: str) -> TestClient:
    """A browser that reaches the server from another address."""
    return TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN}, client=(address, 50000))


def test_the_right_password_signs_in(client: TestClient, account: User) -> None:
    response = log_in(client)

    assert response.status_code == 200
    body = response.json()
    assert body["username"] == ACCOUNT_USERNAME
    assert len(body["csrf_token"]) >= 32
    expires = datetime.fromisoformat(body["expires_at"])
    assert timedelta(minutes=29) < expires - utcnow() <= timedelta(minutes=30)
    assert client.get("/api/auth/session").json()["username"] == ACCOUNT_USERNAME


def test_the_username_is_not_case_or_space_sensitive(client: TestClient, account: User) -> None:
    assert log_in(client, f"  {ACCOUNT_USERNAME.upper()} ").status_code == 200


def test_the_cookie_is_locked_down(client: TestClient, account: User) -> None:
    cookie = log_in(client).headers["set-cookie"]

    assert cookie.startswith(f"{COOKIE}=")
    parts = {part.strip().lower() for part in cookie.split(";")}
    assert {"httponly", "secure", "samesite=strict", "path=/"} <= parts
    # No Domain, which the __Host- prefix requires, and no expiry, so it ends with the browser.
    assert not any(part.startswith(("domain=", "max-age=", "expires=")) for part in parts)


def test_only_a_hash_of_the_cookie_is_stored(
    client: TestClient, account: User, session: Session
) -> None:
    log_in(client)

    token = client.cookies[COOKIE]
    row = session.scalars(select(UserSession)).one()
    assert row.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert token not in (row.token_hash, row.csrf_token)


def test_each_sign_in_gets_a_session_of_its_own(
    app: FastAPI, client: TestClient, account: User, session: Session
) -> None:
    log_in(client)
    with from_address(app, "203.0.113.5") as phone:
        log_in(phone)

    assert session.scalar(select(func.count()).select_from(UserSession)) == 2


@pytest.mark.parametrize("password", ["wrong", "", ACCOUNT_PASSWORD.upper()])
def test_the_wrong_password_is_refused(client: TestClient, account: User, password: str) -> None:
    response = log_in(client, password=password)

    assert response.status_code == 401
    assert response.json() == {"detail": "Incorrect username or password."}
    assert COOKIE not in client.cookies


def test_an_unknown_username_is_refused_in_the_same_words(
    client: TestClient, account: User
) -> None:
    wrong_password = log_in(client, password="wrong")
    unknown_user = log_in(client, username="nobody", password=ACCOUNT_PASSWORD)

    assert unknown_user.status_code == 401
    assert unknown_user.json() == wrong_password.json()


def test_a_request_that_is_not_a_login_is_refused(client: TestClient) -> None:
    assert client.post("/api/auth/login", json={"username": "brian"}).status_code == 422
    assert (
        client.post("/api/auth/login", json={"username": "x" * 257, "password": "x"}).status_code
        == 422
    )
    assert (
        client.post("/api/auth/login", json={"username": "x", "password": "x" * 1025}).status_code
        == 422
    )


def test_five_wrong_passwords_lock_the_account(client: TestClient, account: User) -> None:
    for _ in range(5):
        assert log_in(client, password="wrong").status_code == 401

    locked = log_in(client)

    assert locked.status_code == 429
    assert locked.headers["Retry-After"] == "60"
    assert locked.json() == {"detail": "Too many attempts. Try again in 1 minute."}
    assert COOKIE not in client.cookies


def test_a_longer_wait_is_in_plural_minutes(
    client: TestClient, account: User, session: Session
) -> None:
    for _ in range(5):
        log_in(client, password="wrong")
    for row in session.scalars(select(LoginThrottle)):
        row.locked_until = utcnow() + timedelta(minutes=3, seconds=30)
    session.commit()

    response = log_in(client)

    assert response.status_code == 429
    assert response.json() == {"detail": "Too many attempts. Try again in 4 minutes."}
    assert 205 <= int(response.headers["Retry-After"]) <= 210


def test_guessing_another_users_name_locks_that_name_from_everywhere(
    app: FastAPI, client: TestClient, account: User
) -> None:
    for _ in range(5):
        log_in(client, password="wrong")

    with from_address(app, "203.0.113.5") as elsewhere:
        assert log_in(elsewhere).status_code == 429


def test_guessing_many_names_locks_the_address(
    app: FastAPI, client: TestClient, account: User
) -> None:
    for number in range(5):
        log_in(client, username=f"guess-{number}", password="wrong")

    # The right name and password, but from the address that has been guessing.
    assert log_in(client).status_code == 429
    with from_address(app, "203.0.113.5") as elsewhere:
        assert log_in(elsewhere).status_code == 200


def test_a_success_forgets_the_failures_before_it(client: TestClient, account: User) -> None:
    for _ in range(4):
        log_in(client, password="wrong")
    assert log_in(client).status_code == 200

    for _ in range(4):
        assert log_in(client, password="wrong").status_code == 401

    assert log_in(client).status_code == 200


def test_signing_in_clears_out_sessions_nobody_came_back_to(
    client: TestClient, account: User, session: Session
) -> None:
    log_in(client)
    stale = session.scalars(select(UserSession)).one()
    stale.expires_at = stale.created_at
    session.commit()

    log_in(client)

    assert session.scalar(select(func.count()).select_from(UserSession)) == 1
    assert stale not in session.scalars(select(UserSession)).all()


def test_a_password_hashed_with_old_settings_is_hashed_again(
    client: TestClient, account: User, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = account.password_hash
    monkeypatch.setattr(
        passwords, "hasher", PasswordHasher(time_cost=2, memory_cost=16, parallelism=1)
    )

    assert log_in(client).status_code == 200

    session.refresh(account)
    assert account.password_hash != before
    assert not passwords.needs_rehash(account.password_hash)
    assert passwords.verify_password(ACCOUNT_PASSWORD, account.password_hash)


def test_a_current_hash_is_left_alone(client: TestClient, account: User, session: Session) -> None:
    before = account.password_hash

    log_in(client)

    session.refresh(account)
    assert account.password_hash == before


def test_signing_out_ends_the_session_and_clears_the_cookie(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    response = client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf_token})

    assert response.status_code == 204
    assert response.content == b""
    cleared = response.headers["set-cookie"].lower()
    assert cleared.startswith(f"{COOKIE.lower()}=")
    assert "max-age=0" in cleared
    assert client.get("/api/auth/session").status_code == 401
    assert session.scalar(select(func.count()).select_from(UserSession)) == 0


def test_signing_out_when_not_signed_in_is_refused(client: TestClient) -> None:
    assert client.post("/api/auth/logout").status_code == 401


def test_the_session_says_when_it_ends(client: TestClient, csrf_token: str) -> None:
    body = client.get("/api/auth/session").json()

    assert set(body) == {"username", "csrf_token", "expires_at"}
