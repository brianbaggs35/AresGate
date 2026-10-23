from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.audit import Action, Outcome
from app.config import Settings
from app.models import LoginThrottle, User, UserSession, utcnow
from app.security import passwords
from tests.helpers import ACCOUNT_PASSWORD, ACCOUNT_USERNAME, ORIGIN
from tests.test_two_factor_api import audit_events

BASE = "/api/auth"
NEW_PASSWORD = "a different sentence entirely"
UNKNOWN = "00000000-0000-4000-8000-000000000000"
FIREFOX = "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0"


def change(
    client: TestClient,
    token: str,
    current: str = ACCOUNT_PASSWORD,
    new: str = NEW_PASSWORD,
):
    return client.post(
        f"{BASE}/password",
        json={"current_password": current, "new_password": new},
        headers={"X-CSRF-Token": token},
    )


@pytest.fixture
def other_browser(app: FastAPI, account: User) -> Iterator[TestClient]:
    """A second browser signed in to the account, which another client can end."""
    headers = {"Origin": ORIGIN, "User-Agent": FIREFOX}
    with TestClient(app, base_url=ORIGIN, headers=headers) as browser:
        response = browser.post(
            f"{BASE}/login", json={"username": ACCOUNT_USERNAME, "password": ACCOUNT_PASSWORD}
        )
        assert response.status_code == 200
        yield browser


def signed_in(client: TestClient) -> bool:
    return client.get(f"{BASE}/session").status_code == 200


def listed(client: TestClient) -> list[dict[str, Any]]:
    response = client.get(f"{BASE}/sessions")
    assert response.status_code == 200
    return list(response.json())


# ---- Changing the password ---------------------------------------------------------------


def test_the_password_is_changed(
    client: TestClient, csrf_token: str, session: Session, account: User
) -> None:
    before = account.password_changed_at

    response = change(client, csrf_token)

    assert response.status_code == 200
    assert response.json() == {"ended": 0}
    session.expire_all()
    assert passwords.verify_password(NEW_PASSWORD, account.password_hash)
    assert not passwords.verify_password(ACCOUNT_PASSWORD, account.password_hash)
    assert account.password_changed_at > before
    [event] = audit_events(session, Action.PASSWORD_CHANGED)
    assert event.outcome == Outcome.SUCCESS.value
    assert event.username == ACCOUNT_USERNAME
    assert event.detail == {"sessions_ended": 0}


def test_the_new_password_signs_in_and_the_old_one_does_not(
    client: TestClient, csrf_token: str
) -> None:
    change(client, csrf_token)
    client.cookies.clear()

    old = client.post(
        f"{BASE}/login", json={"username": ACCOUNT_USERNAME, "password": ACCOUNT_PASSWORD}
    )
    new = client.post(
        f"{BASE}/login", json={"username": ACCOUNT_USERNAME, "password": NEW_PASSWORD}
    )

    assert old.status_code == 401
    assert new.status_code == 200


def test_every_other_sign_in_ends_and_this_one_stays(
    client: TestClient, csrf_token: str, other_browser: TestClient, session: Session
) -> None:
    assert signed_in(other_browser)

    response = change(client, csrf_token)

    assert response.json() == {"ended": 1}
    assert signed_in(client)
    assert not signed_in(other_browser)
    [event] = audit_events(session, Action.PASSWORD_CHANGED)
    assert event.detail == {"sessions_ended": 1}


def test_changing_the_password_needs_the_current_one(
    client: TestClient, csrf_token: str, session: Session, account: User
) -> None:
    response = change(client, csrf_token, current="not the password")

    assert response.status_code == 403
    assert response.json() == {"detail": "The password isn't right."}
    session.expire_all()
    assert passwords.verify_password(ACCOUNT_PASSWORD, account.password_hash)
    assert audit_events(session, Action.PASSWORD_CHANGED) == []
    assert sorted((row.scope, row.failures) for row in session.scalars(select(LoginThrottle))) == [
        ("account", 1),
        ("address", 1),
    ]
    [event] = audit_events(session, Action.LOGIN_FAILED)
    assert event.detail == {"reason": "wrong_password", "while": "changing_password"}


@pytest.mark.parametrize(
    ("new", "message"),
    [
        ("too short", "Use at least 12 characters."),
        ("password123456", "That password is too easy to guess. Try a longer phrase."),
        (
            f"{ACCOUNT_USERNAME} likes this one",
            "Don't use your username, the server's name or AresGate in your password.",
        ),
        (ACCOUNT_PASSWORD, "Choose a password you aren't using now."),
    ],
)
def test_a_new_password_that_breaks_a_rule_is_refused_and_says_which(
    client: TestClient,
    csrf_token: str,
    session: Session,
    account: User,
    new: str,
    message: str,
) -> None:
    response = change(client, csrf_token, new=new)

    assert response.status_code == 422
    assert response.json() == {"detail": message}
    session.expire_all()
    assert passwords.verify_password(ACCOUNT_PASSWORD, account.password_hash)
    assert audit_events(session, Action.PASSWORD_CHANGED) == []


def test_changing_the_password_needs_a_sign_in(client: TestClient, account: User) -> None:
    response = client.post(
        f"{BASE}/password",
        json={"current_password": ACCOUNT_PASSWORD, "new_password": NEW_PASSWORD},
    )

    assert response.status_code == 401


def test_changing_the_password_needs_the_security_token(
    client: TestClient, csrf_token: str
) -> None:
    response = client.post(
        f"{BASE}/password",
        json={"current_password": ACCOUNT_PASSWORD, "new_password": NEW_PASSWORD},
    )

    assert response.status_code == 403


# ---- Where the account is signed in -------------------------------------------------------


def test_this_browser_is_listed_and_marked(client: TestClient, csrf_token: str) -> None:
    [this] = listed(client)

    assert this["current"] is True
    assert this["address"] == "testclient"
    assert this["user_agent"] == "testclient"
    assert this["expires_at"] > this["last_seen_at"]
    assert this["started_at"] <= this["last_seen_at"]


def test_every_browser_signed_in_is_listed_the_one_used_last_first(
    client: TestClient, csrf_token: str, other_browser: TestClient, session: Session
) -> None:
    session.execute(
        update(UserSession)
        .where(UserSession.user_agent == "testclient")
        # Not yet a minute ago, which is when asking about it would note it was used again.
        .values(last_seen_at=utcnow() - timedelta(seconds=30))
    )
    session.commit()

    here, there = listed(client)

    assert (here["user_agent"], here["current"]) == (FIREFOX, False)
    assert (there["user_agent"], there["current"]) == ("testclient", True)


def test_a_sign_in_that_ended_is_not_listed(
    client: TestClient,
    csrf_token: str,
    other_browser: TestClient,
    session: Session,
    settings: Settings,
) -> None:
    session.execute(
        update(UserSession)
        .where(UserSession.user_agent == FIREFOX)
        .values(last_seen_at=utcnow() - timedelta(minutes=settings.session_idle_minutes + 1))
    )
    session.commit()

    assert [row["current"] for row in listed(client)] == [True]


def test_another_browser_is_signed_out(
    client: TestClient, csrf_token: str, other_browser: TestClient, session: Session
) -> None:
    [other] = [row for row in listed(client) if not row["current"]]

    response = client.post(
        f"{BASE}/sessions/{other['id']}/end", headers={"X-CSRF-Token": csrf_token}
    )

    assert response.status_code == 204
    assert not signed_in(other_browser)
    assert signed_in(client)
    assert [row["current"] for row in listed(client)] == [True]
    [event] = audit_events(session, Action.SESSIONS_ENDED)
    assert event.detail == {"count": 1}


def test_this_browser_is_signed_out_from_the_account_menu_not_the_list(
    client: TestClient, csrf_token: str
) -> None:
    [this] = listed(client)

    response = client.post(
        f"{BASE}/sessions/{this['id']}/end", headers={"X-CSRF-Token": csrf_token}
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "That's the browser you're using. Sign out instead."}
    assert signed_in(client)


def test_a_sign_in_that_is_not_there_is_said_to_have_ended_already(
    client: TestClient, csrf_token: str
) -> None:
    response = client.post(
        f"{BASE}/sessions/{UNKNOWN}/end",
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "That sign-in has already ended."}


def test_every_other_browser_is_signed_out_at_once(
    client: TestClient, csrf_token: str, other_browser: TestClient, session: Session
) -> None:
    response = client.post(f"{BASE}/sessions/end-others", headers={"X-CSRF-Token": csrf_token})

    assert response.status_code == 200
    assert response.json() == {"ended": 1}
    assert not signed_in(other_browser)
    assert signed_in(client)
    [event] = audit_events(session, Action.SESSIONS_ENDED)
    assert event.detail == {"count": 1}


def test_signing_out_the_others_with_none_to_sign_out_says_so_and_records_nothing(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    response = client.post(f"{BASE}/sessions/end-others", headers={"X-CSRF-Token": csrf_token})

    assert response.json() == {"ended": 0}
    assert audit_events(session, Action.SESSIONS_ENDED) == []


SIGN_INS = [
    ("GET", f"{BASE}/sessions"),
    ("POST", f"{BASE}/sessions/end-others"),
    ("POST", f"{BASE}/sessions/{UNKNOWN}/end"),
]


@pytest.mark.parametrize(("method", "path"), SIGN_INS)
def test_the_sign_ins_need_a_sign_in(
    client: TestClient, account: User, method: str, path: str
) -> None:
    assert client.request(method, path).status_code == 401


@pytest.mark.parametrize(("method", "path"), SIGN_INS[1:])
def test_changing_the_sign_ins_needs_the_security_token(
    client: TestClient, csrf_token: str, method: str, path: str
) -> None:
    assert client.request(method, path).status_code == 403
