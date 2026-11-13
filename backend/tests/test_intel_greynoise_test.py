"""Testing the GreyNoise connection: a lookup through the budget for a free account's key or none,
and a ping for a subscription's, which asks about no address."""

import asyncio
from collections.abc import Callable
from datetime import timedelta
from ipaddress import ip_address

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations import netguard, probes, service
from app.integrations.client import ApiClient, Call, Target
from app.integrations.netguard import HOME_NETWORK_AND_LOOPBACK, AddressPolicy
from app.integrations.probes import Verdict
from app.intel import connection, greynoise, store
from app.models import IntegrationConnection, IntelLookup, IntelSubject
from app.models.base import utcnow
from tests.stubs import Answer, Seen, Serve
from tests.test_integrations_api import BASE, headers

GN_URL = f"{BASE}/greynoise"
FREE = {"access": "key", "plan": "free"}
NONE = {"access": "none"}
SUBSCRIPTION = {"access": "key", "plan": "subscription"}


def connect(
    session: Session, monkeypatch: pytest.MonkeyPatch, options: dict[str, str] | None = None
) -> None:
    """A GreyNoise connection that was tested before, whose key opens."""
    chosen = options or FREE
    origin = netguard.parse_origin("https://api.greynoise.io", allow_http=False)

    def load(*args: object, **kwargs: object) -> Target:
        del args, kwargs
        return Target(
            integration="greynoise",
            connection="api",
            origin=origin,
            tls_mode="system",
            tls_ca_pem=None,
            tls_fingerprint=None,
            options=chosen,
            secrets={"api_key": "gn-key"},
        )

    monkeypatch.setattr(service, "load_target", load)
    session.add(
        IntegrationConnection(
            integration="greynoise",
            connection="api",
            base_url="https://api.greynoise.io",
            tls_mode="system",
            options=chosen,
            last_success_at=utcnow() - timedelta(days=1),
        )
    )
    session.commit()


def answer_by_greynoise(monkeypatch: pytest.MonkeyPatch, answer: object) -> list[object]:
    """Makes GreyNoise answer with the answer given. Returns the requests made."""
    asked: list[object] = []

    async def look_up(*args: object) -> object:
        asked.append(args)
        return answer

    monkeypatch.setattr(greynoise, "look_up", look_up)
    return asked


def ping_with(monkeypatch: pytest.MonkeyPatch, said: Verdict) -> list[Target]:
    """Makes the ping of a subscription's key give the verdict. Returns the targets pinged."""
    pinged: list[Target] = []

    async def ping(target: Target, recorder: object) -> Verdict:
        del recorder
        pinged.append(target)
        return said

    monkeypatch.setattr(connection, "_ping", ping)
    return pinged


def test_a_free_accounts_key_is_tested_with_one_lookup_that_is_kept_as_a_test(
    client: TestClient,
    csrf_token: str,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connect(session, monkeypatch)
    asked = answer_by_greynoise(monkeypatch, greynoise.Unknown())

    response = client.post(f"{GN_URL}/test", headers=headers(csrf_token))

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["checks"][0]["message"] == (
        "GreyNoise accepted the key. The free plan allows 50 searches a week."
    )
    assert body["integration"]["status"] == "connected"
    assert len(asked) == 1
    [lookup] = session.scalars(select(IntelLookup)).all()
    assert (lookup.provider, lookup.kind, lookup.subject, lookup.outcome) == (
        "greynoise",
        "test",
        "8.8.8.8",
        store.UNKNOWN,
    )
    [kept] = session.scalars(select(IntelSubject)).all()
    assert (kept.provider, kept.subject) == ("greynoise", "8.8.8.8")


def test_a_connection_with_no_account_is_tested_with_one_lookup_and_says_what_it_allows(
    client: TestClient,
    csrf_token: str,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connect(session, monkeypatch, NONE)
    asked = answer_by_greynoise(monkeypatch, greynoise.Unknown())

    response = client.post(f"{GN_URL}/test", headers=headers(csrf_token))

    assert response.json()["checks"][0]["message"] == (
        "GreyNoise answered. With no account it allows 10 lookups a day."
    )
    assert len(asked) == 1


def test_a_key_greynoise_refuses_fails_and_says_why(
    client: TestClient,
    csrf_token: str,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connect(session, monkeypatch)
    answer_by_greynoise(monkeypatch, greynoise.Failed("GreyNoise didn't accept the key."))

    response = client.post(f"{GN_URL}/test", headers=headers(csrf_token))

    body = response.json()
    assert body["ok"] is False
    assert body["integration"]["status"] == "problem"
    assert body["integration"]["last_error"] == "GreyNoise didn't accept the key."


def test_a_test_when_greynoise_says_the_limit_is_reached_passes_and_keeps_the_pause(
    client: TestClient,
    csrf_token: str,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connect(session, monkeypatch)
    answer_by_greynoise(monkeypatch, greynoise.Throttled(until=utcnow() + greynoise.THROTTLE))

    response = client.post(f"{GN_URL}/test", headers=headers(csrf_token))

    body = response.json()
    assert body["ok"] is True
    assert body["checks"][0]["message"] == connection.GREYNOISE_THROTTLED
    assert body["integration"]["pause"]["daily"] is False
    [lookup] = session.scalars(select(IntelLookup)).all()
    assert lookup.outcome == store.THROTTLED


def test_a_test_soon_after_a_lookup_waits_and_sends_nothing(
    client: TestClient,
    csrf_token: str,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connect(session, monkeypatch)
    session.add(
        IntelLookup(
            provider="greynoise",
            kind="ip",
            address=ip_address("93.184.216.34"),
            requested_at=utcnow() - timedelta(seconds=3),
            outcome=store.REPORTED,
        )
    )
    session.commit()
    asked = answer_by_greynoise(monkeypatch, greynoise.Unknown())

    response = client.post(f"{GN_URL}/test", headers=headers(csrf_token))

    assert response.status_code == 429
    assert asked == []


def test_a_test_while_greynoise_holds_lookups_sends_nothing(
    client: TestClient,
    csrf_token: str,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connect(session, monkeypatch)
    session.add(
        IntelLookup(
            provider="greynoise",
            kind="ip",
            requested_at=utcnow() - timedelta(minutes=5),
            outcome=store.THROTTLED,
        )
    )
    session.commit()
    asked = answer_by_greynoise(monkeypatch, greynoise.Unknown())

    response = client.post(f"{GN_URL}/test", headers=headers(csrf_token))

    assert response.status_code == 429
    assert asked == []


def test_a_subscriptions_key_is_pinged_and_no_lookup_is_spent(
    client: TestClient,
    csrf_token: str,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connect(session, monkeypatch, SUBSCRIPTION)
    asked = answer_by_greynoise(monkeypatch, greynoise.Unknown())
    pinged = ping_with(monkeypatch, Verdict(True, "GreyNoise accepted the key. It is Elite."))

    response = client.post(f"{GN_URL}/test", headers=headers(csrf_token))

    body = response.json()
    assert body["ok"] is True
    assert body["checks"][0]["message"] == "GreyNoise accepted the key. It is Elite."
    assert len(pinged) == 1
    assert asked == []
    assert session.scalars(select(IntelLookup)).all() == []


def test_the_connection_is_tested_by_hand_and_never_on_the_timer() -> None:
    assert ("greynoise", "api") in probes.METERED


# -- the ping


def ping(serve: Serve, handler: Callable[[Seen], Answer]) -> tuple[Verdict, list[Call], list[Seen]]:
    server = serve(handler)
    where = Target(
        integration="greynoise",
        connection="api",
        origin=netguard.parse_origin(server.url, allow_http=True),
        tls_mode="system",
        tls_ca_pem=None,
        tls_fingerprint=None,
        options=SUBSCRIPTION,
        secrets={"api_key": "gn-key"},
    )
    calls: list[Call] = []

    async def record(call: Call) -> None:
        calls.append(call)

    async def go() -> Verdict:
        async with ApiClient(where, record, HOME_NETWORK_AND_LOOPBACK) as client:
            return await probes.run(probes.greynoise_ping, client, where)

    return asyncio.run(go()), calls, server.seen


def test_the_ping_sends_the_key_and_asks_about_no_address(serve: Serve) -> None:
    result, calls, seen = ping(
        serve, lambda seen: Answer(body='{"message": "pong", "plan": "Elite"}')
    )

    assert result == Verdict(True, "GreyNoise accepted the key. It belongs to the Elite plan.")
    [request] = seen
    assert request.target == "/ping"
    assert request.headers["key"] == "gn-key"
    assert calls[0].path == "/ping"


@pytest.mark.parametrize(
    ("answer", "message"),
    [
        (Answer(status=401), "GreyNoise didn't accept the key."),
        (Answer(status=403), "GreyNoise didn't accept the key."),
        (Answer(status=500), "GreyNoise answered HTTP 500."),
        (Answer(body="<html>"), "doesn't look like GreyNoise's"),
        (Answer(body='{"message": "nope"}'), "doesn't look like GreyNoise's"),
    ],
)
def test_a_ping_that_does_not_answer_properly_is_explained(
    serve: Serve, answer: Answer, message: str
) -> None:
    result, _, _ = ping(serve, lambda seen: answer)

    assert not result.ok
    assert message in result.message


def test_a_ping_that_names_no_plan_says_only_that_the_key_was_accepted(serve: Serve) -> None:
    result, _, _ = ping(serve, lambda seen: Answer(body='{"message": "pong"}'))

    assert result == Verdict(True, "GreyNoise accepted the key.")


def test_the_subscription_ping_goes_out_through_the_connections_own_client(
    serve: Serve, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = serve(lambda seen: Answer(body='{"message": "pong", "plan": "Advanced"}'))
    where = Target(
        integration="greynoise",
        connection="api",
        origin=netguard.parse_origin(server.url, allow_http=True),
        tls_mode="system",
        tls_ca_pem=None,
        tls_fingerprint=None,
        options=SUBSCRIPTION,
        secrets={"api_key": "gn-key"},
    )
    # The stand-in is on this machine, which the real policy for GreyNoise would refuse.

    def policy_for(*args: object) -> AddressPolicy:
        del args
        return HOME_NETWORK_AND_LOOPBACK

    monkeypatch.setattr(service, "policy_for", policy_for)

    async def record(_call: Call) -> None:
        """Keeps nothing: the test needs only the verdict."""

    result = asyncio.run(connection._ping(where, record))  # pyright: ignore[reportPrivateUsage]

    assert result == Verdict(True, "GreyNoise accepted the key. It belongs to the Advanced plan.")
    assert [request.target for request in server.seen] == ["/ping"]
