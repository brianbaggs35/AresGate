from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db import get_session
from app.models import LoginThrottle, SystemInfo, User, UserSession, utcnow
from app.security import passwords, sessions, setup_code
from tests.helpers import ORIGIN

CODE = "K7QD-3MWX-9HPA"
PASSWORD = "the quick brown fox jumps"


@pytest.fixture
def code(session: Session) -> str:
    """A setup code waiting to be used, as on a fresh install."""
    setup_code.store(session, CODE)
    session.commit()
    return CODE


def set_up(
    client: TestClient, *, code: str = CODE, username: str = "Brian", password: str = PASSWORD
) -> Response:
    return client.post(
        "/api/setup", json={"code": code, "username": username, "password": password}
    )


def users(session: Session) -> list[User]:
    return list(session.scalars(select(User)))


def test_a_fresh_install_asks_to_be_set_up(client: TestClient) -> None:
    assert client.get("/api/setup/status").json() == {"setup_required": True}


def test_an_install_with_an_account_does_not(client: TestClient, account: User) -> None:
    assert client.get("/api/setup/status").json() == {"setup_required": False}


def test_the_right_code_creates_the_account_and_signs_in(
    client: TestClient, code: str, session: Session
) -> None:
    response = set_up(client)

    assert response.status_code == 201
    assert response.json()["username"] == "brian"
    [user] = users(session)
    assert user.username == "brian"
    assert passwords.verify_password(PASSWORD, user.password_hash)
    assert PASSWORD not in user.password_hash
    assert client.get("/api/auth/session").json()["username"] == "brian"
    assert client.get("/api/setup/status").json() == {"setup_required": False}


def test_the_session_it_starts_can_be_ended(
    client: TestClient, code: str, session: Session
) -> None:
    csrf = set_up(client).json()["csrf_token"]

    assert client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 204
    assert session.scalar(select(func.count()).select_from(UserSession)) == 0


def test_it_sets_the_same_locked_down_cookie_as_signing_in(client: TestClient, code: str) -> None:
    cookie = set_up(client).headers["set-cookie"].lower()

    assert cookie.startswith(f"{sessions.COOKIE_NAME.lower()}=")
    assert all(attribute in cookie for attribute in ("httponly", "secure", "samesite=strict"))


def test_the_code_works_however_it_is_typed(client: TestClient, code: str) -> None:
    assert set_up(client, code="k7qd 3mwx 9hpa ").status_code == 201


def test_the_code_works_once(client: TestClient, code: str, session: Session) -> None:
    set_up(client)

    again = set_up(client, username="someone-else")

    assert again.status_code == 409
    assert again.json() == {"detail": "AresGate is already set up."}
    assert [user.username for user in users(session)] == ["brian"]
    assert session.get(SystemInfo, setup_code.KEY) is None


def test_a_wrong_code_is_refused_and_the_right_one_still_works(
    client: TestClient, code: str, session: Session
) -> None:
    wrong = set_up(client, code="AAAA-AAAA-AAAA")

    assert wrong.status_code == 403
    assert wrong.json() == {"detail": "That setup code isn't right."}
    assert users(session) == []
    assert sessions.COOKIE_NAME not in client.cookies
    assert set_up(client).status_code == 201


def test_five_wrong_codes_lock_the_setup_even_for_the_right_one(
    client: TestClient, code: str, session: Session
) -> None:
    for _ in range(5):
        assert set_up(client, code="AAAA-AAAA-AAAA").status_code == 403

    locked = set_up(client)

    assert locked.status_code == 429
    assert locked.headers["Retry-After"] == "60"
    assert users(session) == []


def test_the_lock_is_per_address(app: FastAPI, client: TestClient, code: str) -> None:
    for _ in range(5):
        set_up(client, code="AAAA-AAAA-AAAA")

    with TestClient(
        app, base_url=ORIGIN, headers={"Origin": ORIGIN}, client=("203.0.113.5", 50000)
    ) as elsewhere:
        assert set_up(elsewhere).status_code == 201


def test_the_right_code_forgets_the_wrong_ones_before_it(
    client: TestClient, code: str, session: Session
) -> None:
    set_up(client, code="AAAA-AAAA-AAAA")
    set_up(client)

    assert session.scalar(select(func.count()).select_from(LoginThrottle)) == 0


def test_the_lock_ends(client: TestClient, code: str, session: Session) -> None:
    for _ in range(5):
        set_up(client, code="AAAA-AAAA-AAAA")
    for row in session.scalars(select(LoginThrottle)):
        row.locked_until = utcnow() - timedelta(seconds=1)
    session.commit()

    assert set_up(client).status_code == 201


def test_without_a_code_there_is_nothing_to_set_up_with(
    client: TestClient, session: Session
) -> None:
    response = set_up(client)

    assert response.status_code == 409
    assert "no setup code" in response.json()["detail"]
    assert users(session) == []


def test_a_weak_password_is_refused_and_the_code_still_works(
    client: TestClient, code: str, session: Session
) -> None:
    weak = set_up(client, password="short")

    assert weak.status_code == 422
    assert weak.json() == {"detail": "Use at least 12 characters."}
    assert users(session) == []
    assert set_up(client).status_code == 201


def test_a_password_made_from_the_username_is_refused(client: TestClient, code: str) -> None:
    response = set_up(client, username="brian", password="my brian password")

    assert response.status_code == 422
    assert "username" in response.json()["detail"]


def test_a_password_made_from_the_servers_name_is_refused(client: TestClient, code: str) -> None:
    response = set_up(client, password="aresgate dot test")

    assert response.status_code == 422


@pytest.mark.parametrize("username", ["ab", "has space", "x" * 65, ""])
def test_a_username_that_breaks_the_rules_is_refused(
    client: TestClient, code: str, username: str
) -> None:
    response = set_up(client, username=username)

    assert response.status_code == 422
    assert "3 to 64" in response.json()["detail"]


def test_a_request_that_is_not_a_setup_is_refused(client: TestClient, code: str) -> None:
    assert client.post("/api/setup", json={"code": CODE}).status_code == 422
    assert set_up(client, password="x" * 1025).status_code == 422
    assert set_up(client, code="x" * 65).status_code == 422


def test_an_install_with_an_account_refuses_setup_whatever_the_code(
    client: TestClient, account: User, code: str, session: Session
) -> None:
    response = set_up(client, username="intruder")

    assert response.status_code == 409
    assert [user.username for user in users(session)] == [account.username]


def test_a_code_without_the_origin_is_not_even_tried(
    app: FastAPI, code: str, session: Session
) -> None:
    with TestClient(app, base_url=ORIGIN) as bare:
        response = set_up(bare)

    assert response.status_code == 403
    assert users(session) == []
    assert session.get(SystemInfo, setup_code.KEY) is not None


def test_two_people_using_the_code_at_once_make_one_account(
    app: FastAPI, engine: Engine, code: str, session: Session
) -> None:
    def own_session() -> Iterator[Session]:
        with sessionmaker(bind=engine, expire_on_commit=False)() as each:
            yield each

    # Real sessions, one for each request, so the two really do run side by side.
    app.dependency_overrides[get_session] = own_session
    start = Barrier(2)

    def try_to_set_up(username: str) -> int:
        with TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN}) as browser:
            start.wait()
            return set_up(browser, username=username).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = sorted(pool.map(try_to_set_up, ["first", "second"]))

    assert results == [201, 409]
    assert len(users(session)) == 1
