import math
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fido2.utils import websafe_decode, websafe_encode
from fido2.webauthn import AttestedCredentialData
from httpx2 import Response
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.audit import Action, Outcome
from app.config import Settings, get_settings
from app.models import LoginThrottle, Passkey, PasskeyChallenge, User, utcnow
from app.security import passkeys as passkeys_module
from app.security import sessions
from e2e import factories
from tests.helpers import (
    ACCOUNT_PASSWORD,
    ACCOUNT_USERNAME,
    ORIGIN,
    OTHER_ORIGIN,
    SERVER_NAME,
    turn_on_two_factor,
)
from tests.soft_authenticator import Algorithm, SoftAuthenticator
from tests.test_two_factor_api import audit_events

BASE = "/api/auth"
COOKIE = sessions.COOKIE_NAME
SIGN_IN_FAILED = "That passkey didn't work."
TIMED_OUT = "Your sign-in timed out. Try again."


def start_adding(client: TestClient, token: str, password: str = ACCOUNT_PASSWORD) -> Response:
    return client.post(
        f"{BASE}/passkeys/options", json={"password": password}, headers={"X-CSRF-Token": token}
    )


def add(
    client: TestClient,
    token: str,
    device: SoftAuthenticator,
    *,
    name: str = "Laptop",
    **answer: Any,
) -> Response:
    """Adds the device's passkey, the way the web app does: ask for options, then answer."""
    started = start_adding(client, token)
    assert started.status_code == 200
    return client.post(
        f"{BASE}/passkeys",
        json={
            "challenge_id": started.json()["challenge_id"],
            "credential": device.register(started.json()["options"], **answer),
            "name": name,
        },
        headers={"X-CSRF-Token": token},
    )


def sign_in_options(client: TestClient) -> dict[str, Any]:
    response = client.post(f"{BASE}/login/passkey/options")
    assert response.status_code == 200
    return dict(response.json())


def answer(client: TestClient, challenge_id: str, credential: dict[str, Any]) -> Response:
    return client.post(
        f"{BASE}/login/passkey", json={"challenge_id": challenge_id, "credential": credential}
    )


def sign_in(client: TestClient, device: SoftAuthenticator, **answered: Any) -> Response:
    """Signs in with the device's passkey, the way the web app does."""
    started = sign_in_options(client)
    return answer(client, started["challenge_id"], device.sign_in(started["options"], **answered))


@pytest.fixture
def device(client: TestClient, csrf_token: str) -> SoftAuthenticator:
    """A passkey on the account, and the signed-in browser signed out again."""
    device = SoftAuthenticator()
    assert add(client, csrf_token, device).status_code == 201
    client.cookies.clear()
    return device


def throttled(session: Session) -> list[tuple[str, int]]:
    session.expire_all()
    return [(row.scope, row.failures) for row in session.scalars(select(LoginThrottle))]


def stored(session: Session) -> list[Passkey]:
    session.expire_all()
    return list(session.scalars(select(Passkey).order_by(Passkey.created_at)))


def waiting(session: Session) -> list[PasskeyChallenge]:
    session.expire_all()
    return list(session.scalars(select(PasskeyChallenge)))


def other_account(session: Session) -> User:
    user = factories.account(session, username="other")
    session.commit()
    return user


# ---- Looking at them, and the routes needing a sign-in -----------------------------------


def test_there_are_no_passkeys_at_first(client: TestClient, csrf_token: str) -> None:
    response = client.get(f"{BASE}/passkeys")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/passkeys", None),
        ("/passkeys/options", {"password": "x"}),
        ("/passkeys", {"challenge_id": str(uuid4()), "credential": {}, "name": "x"}),
        (f"/passkeys/{uuid4()}/remove", {"password": "x"}),
    ],
)
def test_managing_passkeys_needs_a_sign_in(
    client: TestClient, path: str, body: dict[str, Any] | None
) -> None:
    response = (
        client.get(f"{BASE}{path}") if body is None else client.post(f"{BASE}{path}", json=body)
    )

    assert response.status_code == 401


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/passkeys/options", {"password": "x"}),
        ("/passkeys", {"challenge_id": str(uuid4()), "credential": {}, "name": "x"}),
        (f"/passkeys/{uuid4()}/remove", {"password": "x"}),
    ],
)
def test_a_change_needs_the_security_token(
    client: TestClient, csrf_token: str, path: str, body: dict[str, Any]
) -> None:
    assert client.post(f"{BASE}{path}", json=body).status_code == 403


# ---- Adding a passkey --------------------------------------------------------------------


def test_the_options_ask_for_a_passkey_the_device_unlocks_itself(
    client: TestClient, csrf_token: str, account: User
) -> None:
    response = start_adding(client, csrf_token)

    assert response.status_code == 200
    options = response.json()["options"]
    assert UUID(response.json()["challenge_id"])
    assert options["rp"] == {"id": SERVER_NAME, "name": "AresGate"}
    assert websafe_decode(options["user"]["id"]) == account.id.bytes
    assert options["user"]["name"] == ACCOUNT_USERNAME
    assert [algorithm["alg"] for algorithm in options["pubKeyCredParams"]] == [-7, -8, -257]
    assert options["authenticatorSelection"]["residentKey"] == "required"
    assert options["authenticatorSelection"]["userVerification"] == "required"
    assert options["attestation"] == "none"
    assert options["excludeCredentials"] == []
    assert len(websafe_decode(options["challenge"])) == 32


def test_the_options_leave_out_the_passkeys_the_account_has(
    client: TestClient, csrf_token: str, device: SoftAuthenticator
) -> None:
    client.post(
        "/api/auth/login", json={"username": ACCOUNT_USERNAME, "password": ACCOUNT_PASSWORD}
    )
    token = client.get(f"{BASE}/session").json()["csrf_token"]

    options = start_adding(client, token).json()["options"]

    assert [excluded["id"] for excluded in options["excludeCredentials"]] == [device.id]


def test_a_passkey_is_added_and_listed(
    client: TestClient, csrf_token: str, session: Session, account: User
) -> None:
    device = SoftAuthenticator()

    response = add(client, csrf_token, device, name="Work laptop")

    assert response.status_code == 201
    info = response.json()
    assert info["name"] == "Work laptop"
    assert info["last_used_at"] is None
    assert client.get(f"{BASE}/passkeys").json() == [info]
    [row] = stored(session)
    assert str(row.id) == info["id"]
    assert row.user_id == account.id
    assert row.credential_id == device.credential_id
    assert row.sign_count == 0
    assert AttestedCredentialData(row.credential_data).credential_id == device.credential_id
    assert waiting(session) == []
    [event] = audit_events(session, Action.PASSKEY_ADDED)
    assert event.outcome == Outcome.SUCCESS.value
    assert event.username == ACCOUNT_USERNAME
    assert event.detail == {"name": "Work laptop"}


@pytest.mark.parametrize("algorithm", ["es256", "eddsa", "rs256"])
def test_each_kind_of_key_can_be_added_and_used(
    client: TestClient, csrf_token: str, algorithm: Algorithm
) -> None:
    device = SoftAuthenticator(algorithm)
    assert add(client, csrf_token, device).status_code == 201
    client.cookies.clear()

    response = sign_in(client, device)

    assert response.status_code == 200
    assert response.json()["username"] == ACCOUNT_USERNAME


def test_a_kind_of_key_the_server_doesnt_offer_is_refused(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    response = add(client, csrf_token, SoftAuthenticator("es384"))

    assert response.status_code == 422
    assert stored(session) == []
    [event] = audit_events(session, Action.PASSKEY_ADDED)
    assert event.outcome == Outcome.FAILURE.value
    assert event.detail == {"reason": "unsupported_key"}


def test_the_name_is_tidied(client: TestClient, csrf_token: str) -> None:
    response = add(client, csrf_token, SoftAuthenticator(), name="  Work\nlaptop \x00 ")

    assert response.json()["name"] == "Work laptop"


@pytest.mark.parametrize("name", ["", "   ", "\x00\n\t", "x" * 257])
def test_a_passkey_needs_a_name(client: TestClient, csrf_token: str, name: str) -> None:
    assert add(client, csrf_token, SoftAuthenticator(), name=name).status_code == 422


def test_a_long_name_is_cut_to_fit(client: TestClient, csrf_token: str) -> None:
    response = add(client, csrf_token, SoftAuthenticator(), name="n" * 200)

    assert response.json()["name"] == "n" * 64


def test_adding_a_passkey_needs_the_password(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    response = start_adding(client, csrf_token, "not the password")

    assert response.status_code == 403
    assert response.json() == {"detail": "The password isn't right."}
    assert waiting(session) == []
    assert sorted(throttled(session)) == [("account", 1), ("address", 1)]
    [event] = audit_events(session, Action.LOGIN_FAILED)
    assert event.username == ACCOUNT_USERNAME
    assert event.detail == {"reason": "wrong_password", "while": "adding_passkey"}


def test_wrong_passwords_lock_the_account_out_of_adding_passkeys(
    client: TestClient, csrf_token: str
) -> None:
    for _ in range(5):
        assert start_adding(client, csrf_token, "not the password").status_code == 403

    response = start_adding(client, csrf_token)

    assert response.status_code == 429
    assert "Too many attempts" in response.json()["detail"]


def test_starting_again_replaces_the_attempt_before(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    device = SoftAuthenticator()
    first = start_adding(client, csrf_token).json()
    second = start_adding(client, csrf_token).json()

    assert [str(row.id) for row in waiting(session)] == [second["challenge_id"]]
    late = client.post(
        f"{BASE}/passkeys",
        json={
            "challenge_id": first["challenge_id"],
            "credential": device.register(first["options"]),
            "name": "x",
        },
        headers={"X-CSRF-Token": csrf_token},
    )
    assert late.status_code == 409


def test_a_passkey_already_added_is_refused(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    device = SoftAuthenticator()
    assert add(client, csrf_token, device).status_code == 201

    response = add(client, csrf_token, device, name="Again")

    assert response.status_code == 409
    assert len(stored(session)) == 1


def test_an_account_can_only_have_so_many_passkeys(
    client: TestClient, csrf_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(passkeys_module, "MOST_PER_ACCOUNT", 2)
    for _ in range(2):
        assert add(client, csrf_token, SoftAuthenticator()).status_code == 201

    response = start_adding(client, csrf_token)

    assert response.status_code == 409
    assert response.json() == {"detail": "An account can have 2 passkeys. Remove one first."}


# ---- Answers that aren't right when adding one -------------------------------------------


@pytest.mark.parametrize(
    "wrong",
    [
        pytest.param({"origin": OTHER_ORIGIN}, id="another-site"),
        pytest.param({"origin": "http://aresgate.test"}, id="plain-http"),
        pytest.param({"rp_id": "evil.example"}, id="another-server-name"),
        pytest.param({"type": "webauthn.get"}, id="wrong-kind"),
        pytest.param({"challenge": websafe_encode(bytes(32))}, id="wrong-challenge"),
        pytest.param({"user_present": False}, id="nobody-present"),
        pytest.param({"user_verified": False}, id="not-unlocked"),
        pytest.param({"attested": False}, id="no-key"),
    ],
)
def test_a_wrong_answer_adds_nothing_and_uses_up_the_challenge(
    client: TestClient, csrf_token: str, session: Session, wrong: dict[str, Any]
) -> None:
    device = SoftAuthenticator()
    started = start_adding(client, csrf_token).json()
    body = {"challenge_id": started["challenge_id"], "name": "x"}

    refused = client.post(
        f"{BASE}/passkeys",
        json={**body, "credential": device.register(started["options"], **wrong)},
        headers={"X-CSRF-Token": csrf_token},
    )
    retried = client.post(
        f"{BASE}/passkeys",
        json={**body, "credential": device.register(started["options"])},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert refused.status_code == 422
    assert "couldn't be added" in refused.json()["detail"]
    assert retried.status_code == 409
    assert stored(session) == []
    [event] = audit_events(session, Action.PASSKEY_ADDED)
    assert event.outcome == Outcome.FAILURE.value
    assert event.detail == {"reason": "bad_response"}


def malformed(good: dict[str, Any]) -> list[dict[str, Any]]:
    """Answers that are cut short, or have the wrong kind of value, in each place."""
    cases: list[dict[str, Any]] = [{}, {"id": 1}, {"rawId": "!"}, {**good, "id": "other"}]
    wrong_values: tuple[object, ...] = (None, 1, 10**30, "", [], {})
    for key in ("id", "rawId", "type", "response", "clientExtensionResults"):
        cases += [{**good, key: value} for value in wrong_values]
    response: dict[str, Any] = good["response"]
    for key, value in response.items():
        cases += [{**good, "response": {**response, key: bad}} for bad in (None, 1, 10**30)]
        if isinstance(value, str):
            raw = websafe_decode(value)
            cases += [
                {**good, "response": {**response, key: websafe_encode(raw[: len(raw) // size])}}
                for size in (1, 2, 3, 10)
            ]
    return cases


def test_answers_that_make_no_sense_are_refused_not_crashed_on(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    device = SoftAuthenticator()
    good = device.register(start_adding(client, csrf_token).json()["options"])

    for credential in malformed(good):
        started = start_adding(client, csrf_token).json()
        response = client.post(
            f"{BASE}/passkeys",
            json={"challenge_id": started["challenge_id"], "credential": credential, "name": "x"},
            headers={"X-CSRF-Token": csrf_token},
        )
        assert response.status_code == 422, credential

    assert stored(session) == []


def test_an_answer_that_isnt_an_object_is_refused(client: TestClient, csrf_token: str) -> None:
    started = start_adding(client, csrf_token).json()

    response = client.post(
        f"{BASE}/passkeys",
        json={"challenge_id": started["challenge_id"], "credential": None, "name": "x"},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 422


# ---- Challenges that can't be answered ---------------------------------------------------


def test_an_answer_can_only_be_sent_once(client: TestClient, csrf_token: str) -> None:
    device = SoftAuthenticator()
    started = start_adding(client, csrf_token).json()
    body = {
        "challenge_id": started["challenge_id"],
        "credential": device.register(started["options"]),
        "name": "x",
    }
    headers = {"X-CSRF-Token": csrf_token}

    first = client.post(f"{BASE}/passkeys", json=body, headers=headers)
    again = client.post(f"{BASE}/passkeys", json=body, headers=headers)

    assert first.status_code == 201
    assert again.status_code == 409
    assert again.json() == {"detail": "That took too long. Start adding the passkey again."}


def test_a_challenge_that_ran_out_is_refused(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    device = SoftAuthenticator()
    started = start_adding(client, csrf_token).json()
    session.execute(update(PasskeyChallenge).values(expires_at=utcnow() - timedelta(seconds=1)))
    session.commit()

    response = client.post(
        f"{BASE}/passkeys",
        json={
            "challenge_id": started["challenge_id"],
            "credential": device.register(started["options"]),
            "name": "x",
        },
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 409
    assert stored(session) == []
    assert waiting(session) == []


def test_a_challenge_nobody_gave_is_refused(client: TestClient, csrf_token: str) -> None:
    device = SoftAuthenticator()
    started = start_adding(client, csrf_token).json()

    response = client.post(
        f"{BASE}/passkeys",
        json={
            "challenge_id": str(uuid4()),
            "credential": device.register(started["options"]),
            "name": "x",
        },
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 409


def test_a_challenge_for_signing_in_cant_be_used_to_add_a_passkey(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    device = SoftAuthenticator()
    started = sign_in_options(client)
    options = start_adding(client, csrf_token).json()["options"]

    response = client.post(
        f"{BASE}/passkeys",
        json={
            "challenge_id": started["challenge_id"],
            "credential": device.register(options, challenge=started["options"]["challenge"]),
            "name": "x",
        },
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 409
    assert stored(session) == []


def test_another_accounts_challenge_cant_be_used(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    device = SoftAuthenticator()
    started = start_adding(client, csrf_token).json()
    session.execute(update(PasskeyChallenge).values(user_id=other_account(session).id))
    session.commit()

    response = client.post(
        f"{BASE}/passkeys",
        json={
            "challenge_id": started["challenge_id"],
            "credential": device.register(started["options"]),
            "name": "x",
        },
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 409
    assert stored(session) == []


def test_starting_clears_out_the_challenges_that_ran_out(
    client: TestClient, session: Session
) -> None:
    session.add(
        PasskeyChallenge(
            purpose="sign_in", challenge="x", expires_at=utcnow() - timedelta(minutes=1)
        )
    )
    session.commit()

    started = sign_in_options(client)

    assert [str(row.id) for row in waiting(session)] == [started["challenge_id"]]


# ---- Taking one off ----------------------------------------------------------------------


def test_a_passkey_is_removed(
    client: TestClient, csrf_token: str, session: Session, account: User
) -> None:
    info = add(client, csrf_token, SoftAuthenticator(), name="Old phone").json()

    response = client.post(
        f"{BASE}/passkeys/{info['id']}/remove",
        json={"password": ACCOUNT_PASSWORD},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 204
    assert client.get(f"{BASE}/passkeys").json() == []
    assert stored(session) == []
    [event] = audit_events(session, Action.PASSKEY_REMOVED)
    assert event.outcome == Outcome.SUCCESS.value
    assert event.username == ACCOUNT_USERNAME
    assert event.detail == {"name": "Old phone"}


def test_a_removed_passkey_no_longer_signs_in(
    client: TestClient, csrf_token: str, device: SoftAuthenticator
) -> None:
    client.post(f"{BASE}/login", json={"username": ACCOUNT_USERNAME, "password": ACCOUNT_PASSWORD})
    token = client.get(f"{BASE}/session").json()["csrf_token"]
    [info] = client.get(f"{BASE}/passkeys").json()
    client.post(
        f"{BASE}/passkeys/{info['id']}/remove",
        json={"password": ACCOUNT_PASSWORD},
        headers={"X-CSRF-Token": token},
    )
    client.cookies.clear()

    response = sign_in(client, device)

    assert response.status_code == 401
    assert response.json() == {"detail": SIGN_IN_FAILED}


def test_removing_a_passkey_needs_the_password(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    info = add(client, csrf_token, SoftAuthenticator()).json()

    response = client.post(
        f"{BASE}/passkeys/{info['id']}/remove",
        json={"password": "not the password"},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 403
    assert len(stored(session)) == 1
    [event] = audit_events(session, Action.LOGIN_FAILED)
    assert event.detail == {"reason": "wrong_password", "while": "removing_passkey"}


def test_there_is_nothing_to_remove_for_an_id_the_account_doesnt_have(
    client: TestClient, csrf_token: str, session: Session
) -> None:
    other = other_account(session)
    theirs = Passkey(
        user_id=other.id, name="Theirs", credential_id=b"theirs", credential_data=b"x", sign_count=0
    )
    session.add(theirs)
    session.commit()

    for passkey_id in (theirs.id, uuid4()):
        response = client.post(
            f"{BASE}/passkeys/{passkey_id}/remove",
            json={"password": ACCOUNT_PASSWORD},
            headers={"X-CSRF-Token": csrf_token},
        )
        assert response.status_code == 404

    assert len(stored(session)) == 1


# ---- Signing in --------------------------------------------------------------------------


def test_the_sign_in_options_need_no_sign_in_and_name_nobody(client: TestClient) -> None:
    options = sign_in_options(client)["options"]

    assert options["rpId"] == SERVER_NAME
    assert options["userVerification"] == "required"
    assert "allowCredentials" not in options
    assert len(websafe_decode(options["challenge"])) == 32


def test_a_passkey_signs_in(
    client: TestClient, session: Session, device: SoftAuthenticator
) -> None:
    response = sign_in(client, device)

    assert response.status_code == 200
    assert response.json()["username"] == ACCOUNT_USERNAME
    assert COOKIE in client.cookies
    assert client.get(f"{BASE}/session").json()["username"] == ACCOUNT_USERNAME
    [row] = stored(session)
    assert row.sign_count == 1
    assert row.last_used_at is not None
    assert waiting(session) == []
    event = audit_events(session, Action.LOGIN_SUCCEEDED)[-1]
    assert event.username == ACCOUNT_USERNAME
    assert event.detail == {"method": "passkey", "passkey": "Laptop"}
    assert client.get(f"{BASE}/passkeys").json()[0]["last_used_at"] is not None


def test_a_passkey_stands_in_for_the_authenticator_app_too(
    client: TestClient,
    session: Session,
    settings: Settings,
    account: User,
    device: SoftAuthenticator,
) -> None:
    turn_on_two_factor(session, settings, account)

    response = sign_in(client, device)

    assert response.status_code == 200
    assert "two_factor_required" not in response.json()


def test_a_sign_in_clears_the_failures_counted_against_the_address(
    client: TestClient, session: Session, device: SoftAuthenticator
) -> None:
    for _ in range(2):
        assert sign_in(client, device, sign_with=SoftAuthenticator()).status_code == 401
    assert throttled(session) == [("address", 2)]

    assert sign_in(client, device).status_code == 200
    assert throttled(session) == []


def test_devices_that_dont_count_can_keep_signing_in(
    client: TestClient, device: SoftAuthenticator
) -> None:
    for _ in range(3):
        assert sign_in(client, device, counter=0).status_code == 200


def test_the_count_has_to_go_up(
    client: TestClient, session: Session, device: SoftAuthenticator
) -> None:
    assert sign_in(client, device, counter=5).status_code == 200

    for counter in (5, 3, 0):
        response = sign_in(client, device, counter=counter)
        assert response.status_code == 401
        assert response.json() == {"detail": SIGN_IN_FAILED}

    assert sign_in(client, device, counter=6).status_code == 200
    reasons = [event.detail for event in audit_events(session, Action.LOGIN_FAILED)]
    assert reasons == [{"reason": "counter_went_back", "method": "passkey"}] * 3
    # It is the account's passkey being used twice, which is worth knowing whose.
    assert {event.username for event in audit_events(session, Action.LOGIN_FAILED)} == {
        ACCOUNT_USERNAME
    }


def test_a_passkey_cant_vouch_for_another_account(
    client: TestClient, session: Session, device: SoftAuthenticator
) -> None:
    response = sign_in(client, device, user_handle=other_account(session).id.bytes)

    assert response.status_code == 401
    [event] = audit_events(session, Action.LOGIN_FAILED)
    assert event.username == ACCOUNT_USERNAME
    assert event.detail == {"reason": "wrong_account", "method": "passkey"}


def test_a_device_that_doesnt_say_whose_passkey_it_is_can_still_sign_in(
    client: TestClient, device: SoftAuthenticator
) -> None:
    device.user_handle = None

    assert sign_in(client, device).status_code == 200


@pytest.mark.parametrize(
    ("wrong", "reason", "known"),
    [
        pytest.param({"origin": OTHER_ORIGIN}, "bad_response", True, id="another-site"),
        pytest.param({"rp_id": "evil.example"}, "bad_response", True, id="another-server-name"),
        pytest.param({"type": "webauthn.create"}, "bad_response", True, id="wrong-kind"),
        pytest.param(
            {"challenge": websafe_encode(bytes(32))}, "bad_response", True, id="wrong-challenge"
        ),
        pytest.param({"user_present": False}, "bad_response", True, id="nobody-present"),
        pytest.param({"user_verified": False}, "bad_response", True, id="not-unlocked"),
        pytest.param({"sign_with": SoftAuthenticator()}, "bad_response", True, id="wrong-key"),
        pytest.param({"credential_id": bytes(32)}, "unknown_passkey", False, id="unknown"),
    ],
)
def test_a_wrong_answer_is_refused_and_uses_up_the_challenge(
    client: TestClient,
    session: Session,
    device: SoftAuthenticator,
    wrong: dict[str, Any],
    reason: str,
    known: bool,
) -> None:
    started = sign_in_options(client)

    refused = answer(client, started["challenge_id"], device.sign_in(started["options"], **wrong))
    retried = answer(client, started["challenge_id"], device.sign_in(started["options"]))

    assert refused.status_code == 401
    assert refused.json() == {"detail": SIGN_IN_FAILED}
    assert retried.status_code == 401
    assert retried.json() == {"detail": TIMED_OUT}
    assert COOKIE not in client.cookies
    assert throttled(session) == [("address", 2)]
    first, second = audit_events(session, Action.LOGIN_FAILED)
    assert first.outcome == Outcome.FAILURE.value
    assert first.username == (ACCOUNT_USERNAME if known else None)
    assert first.detail == {"reason": reason, "method": "passkey"}
    assert second.detail == {"reason": "challenge_gone", "method": "passkey"}


def test_answers_that_make_no_sense_are_refused_not_crashed_on_when_signing_in(
    client: TestClient, session: Session, device: SoftAuthenticator
) -> None:
    good = device.sign_in(sign_in_options(client)["options"])

    for credential in malformed(good):
        # Failures lock the address after a few, which isn't what this is looking at.
        session.execute(delete(LoginThrottle))
        session.commit()
        started = sign_in_options(client)
        response = answer(client, started["challenge_id"], credential)
        assert response.status_code == 401, credential


@pytest.mark.parametrize("credential", [None, "x", [], 1])
def test_an_answer_that_isnt_an_object_is_refused_when_signing_in(
    client: TestClient, credential: object
) -> None:
    started = sign_in_options(client)

    response = client.post(
        f"{BASE}/login/passkey",
        json={"challenge_id": started["challenge_id"], "credential": credential},
    )

    assert response.status_code == 422


def test_an_answer_can_only_be_sent_once_when_signing_in(
    client: TestClient, device: SoftAuthenticator
) -> None:
    started = sign_in_options(client)
    credential = device.sign_in(started["options"])

    first = answer(client, started["challenge_id"], credential)
    client.cookies.clear()
    replayed = answer(client, started["challenge_id"], credential)

    assert first.status_code == 200
    assert replayed.status_code == 401
    assert replayed.json() == {"detail": TIMED_OUT}
    assert COOKIE not in client.cookies


def test_a_sign_in_challenge_that_ran_out_is_refused(
    client: TestClient, session: Session, device: SoftAuthenticator
) -> None:
    started = sign_in_options(client)
    session.execute(update(PasskeyChallenge).values(expires_at=utcnow() - timedelta(seconds=1)))
    session.commit()

    response = answer(client, started["challenge_id"], device.sign_in(started["options"]))

    assert response.status_code == 401
    assert response.json() == {"detail": TIMED_OUT}


def test_a_challenge_for_adding_a_passkey_cant_be_used_to_sign_in(
    client: TestClient, csrf_token: str, device: SoftAuthenticator
) -> None:
    client.post(f"{BASE}/login", json={"username": ACCOUNT_USERNAME, "password": ACCOUNT_PASSWORD})
    token = client.get(f"{BASE}/session").json()["csrf_token"]
    started = start_adding(client, token).json()
    client.cookies.clear()

    response = answer(client, started["challenge_id"], device.sign_in(started["options"]))

    assert response.status_code == 401
    assert COOKIE not in client.cookies


def test_a_challenge_nobody_gave_is_refused_when_signing_in(
    client: TestClient, device: SoftAuthenticator
) -> None:
    started = sign_in_options(client)

    response = answer(client, str(uuid4()), device.sign_in(started["options"]))

    assert response.status_code == 401
    assert response.json() == {"detail": TIMED_OUT}


# ---- Guessing ----------------------------------------------------------------------------


def test_failed_sign_ins_lock_the_address_but_not_the_account(
    app: FastAPI, client: TestClient, session: Session, device: SoftAuthenticator
) -> None:
    for _ in range(5):
        assert sign_in(client, device, sign_with=SoftAuthenticator()).status_code == 401

    options = client.post(f"{BASE}/login/passkey/options")

    assert options.status_code == 429
    assert math.ceil(int(options.headers["Retry-After"]) / 60) == 1
    assert throttled(session) == [("address", 5)]
    with TestClient(
        app, base_url=ORIGIN, headers={"Origin": ORIGIN}, client=("192.0.2.9", 50000)
    ) as elsewhere:
        password = elsewhere.post(
            f"{BASE}/login", json={"username": ACCOUNT_USERNAME, "password": ACCOUNT_PASSWORD}
        )
    assert password.status_code == 200


def test_a_locked_address_is_refused_even_a_right_passkey(
    client: TestClient, session: Session, device: SoftAuthenticator
) -> None:
    started = sign_in_options(client)
    credential = device.sign_in(started["options"])
    for _ in range(5):
        sign_in(client, device, sign_with=SoftAuthenticator())

    response = answer(client, started["challenge_id"], credential)

    assert response.status_code == 429
    assert COOKIE not in client.cookies


# ---- Where the page is served from -------------------------------------------------------


def test_the_dev_servers_address_works_away_from_production(
    client: TestClient, csrf_token: str
) -> None:
    device = SoftAuthenticator()
    assert add(client, csrf_token, device, origin="http://localhost:5173").status_code == 201
    client.cookies.clear()

    assert sign_in(client, device, origin="http://localhost:5173").status_code == 200


def test_only_the_servers_own_address_works_in_production(
    app: FastAPI, client: TestClient, csrf_token: str, settings: Settings
) -> None:
    production = settings.model_copy(update={"environment": "production"})
    app.dependency_overrides[get_settings] = lambda: production

    response = add(client, csrf_token, SoftAuthenticator(), origin="http://localhost:5173")

    assert response.status_code == 422


def test_a_passkey_made_for_another_server_name_doesnt_sign_in(
    app: FastAPI, client: TestClient, csrf_token: str, settings: Settings
) -> None:
    device = SoftAuthenticator()
    assert add(client, csrf_token, device).status_code == 201
    client.cookies.clear()
    renamed = settings.model_copy(update={"server_name": "elsewhere.test"})
    app.dependency_overrides[get_settings] = lambda: renamed
    client.headers["Origin"] = renamed.public_origin

    started = sign_in_options(client)
    response = answer(client, started["challenge_id"], device.sign_in(started["options"]))

    assert started["options"]["rpId"] == "elsewhere.test"
    assert response.status_code == 401
