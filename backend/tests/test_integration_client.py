import asyncio
import logging
import ssl
from dataclasses import replace
from typing import Any

import pytest

from app.integrations import client as client_module
from app.integrations import netguard
from app.integrations.client import ApiClient, Call, CallFailed, Reply, Target
from app.integrations.netguard import HOME_NETWORK, HOME_NETWORK_AND_LOOPBACK, Origin
from tests.stubs import Answer, Seen, Serve, StubServer, make_certificate


def target(
    server: StubServer,
    *,
    mode: str = "system",
    ca_pem: str | None = None,
    pin: str | None = None,
    secrets: dict[str, str] | None = None,
) -> Target:
    return Target(
        integration="opnsense",
        connection="api",
        origin=netguard.parse_origin(server.url, allow_http=True),
        tls_mode=mode,
        tls_ca_pem=ca_pem,
        tls_fingerprint=pin,
        options={},
        secrets=secrets or {},
    )


class Log:
    """What the client wrote to the API log."""

    def __init__(self) -> None:
        self.calls: list[Call] = []

    async def __call__(self, call: Call) -> None:
        self.calls.append(call)


def request(
    where: Target,
    log: Log,
    *args: Any,
    policy: netguard.AddressPolicy = HOME_NETWORK_AND_LOOPBACK,
    deadline: float = 20.0,
    hidden: str | None = None,
    **kwargs: Any,
) -> Reply:
    async def go() -> Reply:
        async with ApiClient(where, log, policy, deadline) as client:
            if hidden:
                client.hide(hidden)
            return await client.request(*args, **kwargs)

    return asyncio.run(go())


def test_a_successful_request_returns_the_reply_and_is_logged(serve: Serve) -> None:
    server = serve(lambda seen: Answer(body='{"fine": true}'))
    log = Log()

    reply = request(target(server), log, "get", "/api/status", query={"token": "abc"})

    assert reply.ok
    assert reply.status == 200
    assert reply.json() == {"fine": True}
    [call] = log.calls
    assert (call.integration, call.connection) == ("opnsense", "api")
    assert (call.method, call.path, call.status_code, call.error) == (
        "GET",
        "/api/status",
        200,
        None,
    )
    assert call.duration_ms >= 0
    assert server.seen[0].target == "/api/status?token=abc"


def test_the_query_string_and_fragment_never_reach_the_log(serve: Serve) -> None:
    server = serve(lambda seen: Answer())
    log = Log()

    request(target(server), log, "GET", "/v1/decisions?ip=1.2.3.4&key=secret#frag")
    request(target(server), log, "GET", "/lookup", query={"api_key": "hunter2hunter2"})

    assert [call.path for call in log.calls] == ["/v1/decisions", "/lookup"]
    assert "hunter2" not in repr(log.calls)


def test_control_characters_in_a_path_are_cleaned_and_a_long_one_is_cut(serve: Serve) -> None:
    server = serve(lambda seen: Answer())
    log = Log()

    request(target(server), log, "GET", "/" + "x" * 400)

    assert len(log.calls[0].path) == client_module.MAX_PATH
    assert client_module.clean_path("/a\tb\u2028c") == "/a b c"
    assert client_module.clean_path("?only=a-query") == "/"


def test_what_is_sent_reaches_the_integration(serve: Serve) -> None:
    server = serve(lambda seen: Answer())

    request(
        target(server),
        Log(),
        "post",
        "/security/user/authenticate",
        json_body={"a": 1},
        headers={"X-Api-Key": "k"},
        auth=("user", "pass"),
    )

    [seen] = server.seen
    assert seen.method == "POST"
    assert seen.body == b'{"a":1}'
    assert seen.headers["x-api-key"] == "k"
    assert seen.headers["authorization"].startswith("Basic ")
    assert seen.headers["user-agent"].startswith("AresGate/")
    assert seen.headers["accept"] == "application/json"


@pytest.mark.parametrize(
    ("status", "error"),
    [(401, "Unauthorized"), (403, "Forbidden"), (404, "Not Found"), (500, "Internal Server Error")],
)
def test_a_failure_status_is_logged_with_its_reason(serve: Serve, status: int, error: str) -> None:
    server = serve(lambda seen: Answer(status=status, body="whatever the server says"))
    log = Log()

    reply = request(target(server), log, "GET", "/x")

    assert not reply.ok
    assert reply.status == status
    assert log.calls[0].status_code == status
    assert log.calls[0].error == error


def test_an_unknown_status_is_logged_by_its_number(serve: Serve) -> None:
    server = serve(lambda seen: Answer(status=599))
    log = Log()

    request(target(server), log, "GET", "/x")

    assert log.calls[0].error == "HTTP 599"


def test_a_redirect_is_not_followed_and_is_logged_as_one(serve: Serve) -> None:
    server = serve(
        lambda seen: Answer(status=302, headers={"Location": "http://169.254.169.254/latest"})
    )
    log = Log()

    reply = request(target(server), log, "GET", "/lua/rest")

    assert reply.status == 302
    assert len(server.seen) == 1
    assert log.calls[0].status_code == 302
    assert log.calls[0].error == "Redirected to another address, which AresGate doesn't follow."


def test_a_proxy_in_the_environment_is_not_used(
    serve: Serve, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = serve(lambda seen: Answer(body="direct"))
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY"):
        monkeypatch.setenv(name, "http://127.0.0.1:9")
    monkeypatch.setenv("NO_PROXY", "")

    assert request(target(server), Log(), "GET", "/").text == "direct"


def test_an_address_outside_the_home_network_is_refused_and_logged(serve: Serve) -> None:
    server = serve(lambda seen: Answer())
    log = Log()

    with pytest.raises(CallFailed, match="isn't a private network address"):
        request(target(server), log, "GET", "/x", policy=HOME_NETWORK)

    assert server.seen == []
    assert log.calls[0].status_code is None
    assert "isn't a private network address" in str(log.calls[0].error)


def test_a_connection_that_is_refused_says_so(serve: Serve) -> None:
    server = serve(lambda seen: Answer())
    where = target(server)
    server.stop()
    log = Log()

    with pytest.raises(CallFailed) as raised:
        request(where, log, "GET", "/x")

    assert f"Couldn't connect to 127.0.0.1:{server.port}" in str(raised.value)
    assert str(raised.value) == log.calls[0].error
    assert log.calls[0].status_code is None


def test_a_server_that_does_not_answer_in_time_is_given_up_on(serve: Serve) -> None:
    server = serve(lambda seen: Answer(delay=1.0))
    log = Log()

    with pytest.raises(CallFailed, match="didn't answer in time"):
        request(target(server), log, "GET", "/x", deadline=0.2)

    assert log.calls[0].error is not None


def test_a_server_that_hangs_up_is_not_taken_for_a_web_server(serve: Serve) -> None:
    server = serve(lambda seen: Answer(drop=True))

    with pytest.raises(CallFailed, match="broke, or it isn't a web server"):
        request(target(server), Log(), "GET", "/x")


def test_an_answer_that_is_too_big_is_not_read(
    serve: Serve, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(client_module, "MAX_BODY", 1024)
    server = serve(lambda seen: Answer(body="x" * 5000))
    log = Log()

    with pytest.raises(CallFailed, match="more than AresGate reads"):
        request(target(server), log, "GET", "/x")

    assert "more than AresGate reads" in str(log.calls[0].error)


def test_an_untrusted_certificate_says_how_to_trust_it(serve: Serve) -> None:
    server = serve(lambda seen: Answer(), make_certificate())

    with pytest.raises(CallFailed, match=r"certificate isn't trusted \(.*self.signed") as raised:
        request(target(server), Log(), "GET", "/x")

    assert "pin the certificate's fingerprint" in str(raised.value)
    assert server.seen == []


def test_a_trusted_or_pinned_certificate_is_accepted(serve: Serve) -> None:
    certificate = make_certificate()
    server = serve(lambda seen: Answer(body="ok"), certificate)

    trusted = request(target(server, mode="ca", ca_pem=certificate.pem), Log(), "GET", "/")
    pinned = request(target(server, mode="pinned", pin=certificate.fingerprint), Log(), "GET", "/")

    assert (trusted.text, pinned.text) == ("ok", "ok")


def test_a_wrong_pinned_fingerprint_is_refused_and_logged(serve: Serve) -> None:
    server = serve(lambda seen: Answer(), make_certificate())
    log = Log()

    with pytest.raises(CallFailed, match="isn't the pinned one"):
        request(target(server, mode="pinned", pin=make_certificate().fingerprint), log, "GET", "/x")

    assert server.seen == []
    assert "isn't the pinned one" in str(log.calls[0].error)


def test_https_to_a_plain_server_is_a_failed_secure_connection(serve: Serve) -> None:
    server = serve(lambda seen: Answer())
    where = replace(target(server), origin=Origin("https", "127.0.0.1", server.port))

    with pytest.raises(CallFailed, match=r"The secure connection to 127\.0\.0\.1:\d+ failed"):
        request(where, Log(), "GET", "/x")


def test_secrets_are_hidden_wherever_they_turn_up_in_a_message(
    serve: Serve, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = serve(lambda seen: Answer())

    async def leaky(host: str, port: int) -> list[Any]:
        raise netguard.Refused("Couldn't find hunter2hunter2 or the token tok-123456 either")

    monkeypatch.setattr(netguard, "lookup_async", leaky)
    log = Log()

    with pytest.raises(CallFailed) as raised:
        request(
            target(server, secrets={"api_secret": "hunter2hunter2", "short": "ab"}),
            log,
            "GET",
            "/x",
            hidden="tok-123456",
        )

    assert str(raised.value) == "Couldn't find *** or the token *** either"
    assert log.calls[0].error == "Couldn't find *** or the token *** either"


def test_a_short_value_is_not_hidden(serve: Serve, monkeypatch: pytest.MonkeyPatch) -> None:
    server = serve(lambda seen: Answer())

    async def says(host: str, port: int) -> list[netguard.IPAddress]:
        raise netguard.Refused("Couldn't find abc or xy or the ab in table")

    monkeypatch.setattr(netguard, "lookup_async", says)

    with pytest.raises(CallFailed) as raised:
        request(target(server, secrets={"a": "abc"}), Log(), "GET", "/x", hidden="xy")

    assert str(raised.value) == "Couldn't find abc or xy or the ab in table"


def test_a_failed_log_entry_does_not_fail_the_request(
    serve: Serve, caplog: pytest.LogCaptureFixture
) -> None:
    server = serve(lambda seen: Answer(body="fine"))

    async def broken(call: Call) -> None:
        raise ConnectionError("the database isn't up")

    with caplog.at_level(logging.ERROR):
        reply = request(target(server), broken, "GET", "/x")  # type: ignore[arg-type]

    assert reply.text == "fine"
    assert "Couldn't write an API log entry" in caplog.text


def test_an_unexpected_error_is_logged_and_reported_without_its_details(
    serve: Serve, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    server = serve(lambda seen: Answer())

    async def broken(*_: Any, **__: Any) -> Reply:
        raise ValueError("internal detail with secret")

    monkeypatch.setattr(ApiClient, "_send", broken)
    log = Log()

    with caplog.at_level(logging.ERROR), pytest.raises(CallFailed) as raised:
        request(target(server), log, "GET", "/x")

    assert str(raised.value) == "The request failed in a way AresGate didn't expect."
    assert "internal detail" not in str(log.calls[0].error)
    assert "failed in an unexpected way" in caplog.text


def test_a_reply_that_is_not_json_has_no_json() -> None:
    assert Reply(200, "<html>").json() is None
    assert Reply(200, "null").json() is None
    assert Reply(200, "[1]").json() == [1]
    assert not Reply(302, "").ok
    assert Reply(204, "").ok


def test_the_ssl_error_of_a_chain_is_found_through_causes_and_contexts() -> None:
    inner = ssl.SSLCertVerificationError("nope")
    try:
        try:
            raise inner
        except ssl.SSLCertVerificationError:
            raise RuntimeError("outer") from None
    except RuntimeError as outer:
        assert client_module.in_chain(outer, ssl.SSLCertVerificationError) is inner
        assert client_module.in_chain(outer, KeyError) is None


def test_the_log_entry_carries_when_it_happened(serve: Serve) -> None:
    server = serve(lambda seen: Answer())
    log = Log()

    request(target(server), log, "get", "/x")

    assert log.calls[0].occurred_at.tzinfo is not None
    assert log.calls[0].method == "GET"


def test_unused_seen_helper_exposes_the_path() -> None:
    assert Seen("GET", "/a?b=1", {}, b"").path == "/a"
