"""What the API log keeps of a request beyond its method, path and status, which a person opens an
entry to see: where it went, what it carried, how it was answered. None of it is a secret."""

import asyncio
import json
import ssl
from typing import Any

import pytest

from app.integrations import calldetail, netguard
from app.integrations.client import ApiClient, CallFailed, calling
from app.integrations.netguard import HOME_NETWORK_AND_LOOPBACK, Origin
from tests.stubs import Answer, Serve, make_chain
from tests.test_integration_client import Log, lines_of, request, target

SECRET = "hunter2hunter2"


def detail_of(log: Log) -> dict[str, Any]:
    detail = log.calls[-1].detail
    assert detail is not None
    return detail


def named(pairs: list[dict[str, str | None]], name: str) -> str | None:
    [found] = [pair["value"] for pair in pairs if pair["name"] == name]
    return found


def mask(text: str) -> str:
    return text.replace(SECRET, "***")


# -- which names are credentials


@pytest.mark.parametrize(
    "name",
    ["Authorization", "X-Api-Key", "apikey", "token", "Set-Cookie", "client_secret", "password"],
)
def test_a_name_that_says_it_holds_a_credential_is_one(name: str) -> None:
    assert calldetail.is_secret_name(name)


@pytest.mark.parametrize("name", ["Accept", "User-Agent", "limit", "since", "Content-Type"])
def test_other_names_are_not(name: str) -> None:
    assert not calldetail.is_secret_name(name)


def test_names_and_values_are_listed_without_the_value_of_a_credential() -> None:
    shown = calldetail.pairs(
        [("Authorization", "Bearer abc"), ("Accept", f"x {SECRET} y"), ("n", "v" * 600)], mask
    )

    assert shown[0] == {"name": "Authorization", "value": None}
    assert shown[1] == {"name": "Accept", "value": "x *** y"}
    assert shown[2]["value"] == "v" * 499 + "…"


def test_only_so_many_names_are_listed() -> None:
    shown = calldetail.pairs([(f"h{number}", "v") for number in range(100)], mask)

    assert len(shown) == calldetail.MAX_PAIRS


# -- the start of an answer


def excerpt(body: bytes | str, kind: str | None = "application/json") -> str | None:
    data = body.encode() if isinstance(body, str) else body
    return calldetail.excerpt_of(data, kind, mask)


def test_json_is_laid_out_for_reading_and_what_is_under_a_credential_is_left_out() -> None:
    shown = excerpt(
        json.dumps({"data": {"token": "abc.def", "items": [{"api_key": "k", "n": 1}], "ok": True}})
    )

    assert shown == (
        "{\n"
        '  "data": {\n'
        '    "token": "***",\n'
        '    "items": [\n'
        "      {\n"
        '        "api_key": "***",\n'
        '        "n": 1\n'
        "      }\n"
        "    ],\n"
        '    "ok": true\n'
        "  }\n"
        "}"
    )


def test_a_credential_that_is_empty_is_shown_as_it_is() -> None:
    assert excerpt('{"token": ""}') == '{\n  "token": ""\n}'


def test_secrets_the_connection_holds_are_replaced_wherever_they_are() -> None:
    assert excerpt(f"The key {SECRET} is wrong", "text/plain") == "The key *** is wrong"
    assert SECRET not in (excerpt(json.dumps({"message": f"bad {SECRET}"})) or "")


def test_web_tokens_and_bearer_credentials_in_text_are_left_out() -> None:
    web_token = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.c2lnbmF0dXJl"

    shown = excerpt(f"jwt {web_token} and Bearer abcdef123456 ok", "text/plain")

    assert shown == "jwt *** and Bearer *** ok"


def test_text_that_looks_like_json_but_is_not_is_kept_as_it_is() -> None:
    assert excerpt("{not json", "text/plain") == "{not json"


def test_json_without_a_content_type_is_still_laid_out() -> None:
    assert excerpt('{"a": 1}', None) == '{\n  "a": 1\n}'


def test_an_answer_that_is_not_text_has_no_excerpt() -> None:
    assert excerpt(b"\x00\x01\x02", "application/octet-stream") is None
    assert excerpt(b"\x00\x01\x02", None) is None
    assert excerpt(b"", "text/plain") is None


def test_a_long_answer_is_cut_where_it_says_so() -> None:
    shown = excerpt("a" * 10_000, "text/plain")

    assert shown is not None
    assert len(shown) == calldetail.EXCERPT_CHARS
    assert shown.endswith("…")


# -- how a connection looks from the outside


class Nothing:
    def get_extra_info(self, name: str) -> object:
        return None


def test_a_stream_that_says_nothing_of_itself_gives_no_address_or_certificate() -> None:
    assert calldetail.address_of(None) is None
    assert calldetail.address_of(Nothing()) is None
    assert calldetail.certificate_of(None) is None
    assert calldetail.certificate_of(Nothing()) is None


def test_the_address_is_the_one_connected_to() -> None:
    class Stream:
        def get_extra_info(self, name: str) -> object:
            return ("192.0.2.7", 443)

    assert calldetail.address_of(Stream()) == "192.0.2.7"


def test_a_certificate_that_is_not_there_or_cannot_be_read_is_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Secured(ssl.SSLObject):
        def __init__(self, der: bytes | None) -> None:
            self.der = der

        def getpeercert(self, binary_form: bool = False) -> Any:
            return self.der

    class Stream:
        def __init__(self, secured: object) -> None:
            self.secured = secured

        def get_extra_info(self, name: str) -> object:
            return self.secured

    assert calldetail.certificate_of(Stream(Secured(None))) is None
    assert calldetail.certificate_of(Stream(Secured(b"not a certificate"))) is None


# -- what the client keeps of a request


def test_where_a_request_went_and_what_it_carried_are_kept(serve: Serve) -> None:
    server = serve(lambda seen: Answer(body='{"fine": true}', headers={"X-Served-By": "stub"}))
    log = Log()

    request(
        target(server, secrets={"api_secret": SECRET}),
        log,
        "get",
        "/api/status?ignored=1",
        query={"token": "abc", "limit": "5"},
        headers={"X-Note": f"has {SECRET}", "X-Api-Key": "k"},
    )

    detail = detail_of(log)
    assert (detail["scheme"], detail["host"], detail["port"]) == ("http", "127.0.0.1", server.port)
    assert detail["path"] == "/api/status"
    assert named(detail["query"], "token") is None
    assert named(detail["query"], "limit") == "5"
    headers = detail["request_headers"]
    assert named(headers, "x-api-key") is None
    assert named(headers, "x-note") == "has ***"
    assert named(headers, "accept") == "application/json"
    assert detail["caller"] is None
    assert SECRET not in repr(log.calls)


def test_how_it_was_answered_is_kept(serve: Serve) -> None:
    server = serve(
        lambda seen: Answer(
            body='{"fine": true}',
            headers={
                "Content-Type": "application/json",
                "Set-Cookie": "session=abc",
                "X-Served-By": "stub",
            },
        )
    )
    log = Log()

    request(target(server), log, "GET", "/api/status")

    detail = detail_of(log)
    assert detail["status_line"].endswith("200 OK")
    assert detail["size"] == len('{"fine": true}')
    assert detail["cut"] is False
    assert detail["content_type"] == "application/json"
    assert detail["address"] == "127.0.0.1"
    assert detail["certificate"] is None
    assert 0 <= detail["first_byte_ms"] <= log.calls[0].duration_ms
    assert named(detail["response_headers"], "x-served-by") == "stub"
    assert named(detail["response_headers"], "set-cookie") is None
    assert log.calls[0].excerpt == '{\n  "fine": true\n}'


def test_who_made_the_request_is_kept_when_it_was_said(serve: Serve) -> None:
    server = serve(lambda seen: Answer())
    log = Log()

    with calling("Connection test"):
        request(target(server), log, "GET", "/a")
    request(target(server), log, "GET", "/b")

    assert [call.detail["caller"] for call in log.calls if call.detail] == [
        "Connection test",
        None,
    ]


def test_the_basic_credentials_of_a_request_are_never_kept(serve: Serve) -> None:
    server = serve(lambda seen: Answer())
    log = Log()

    request(target(server), log, "GET", "/a", auth=("user", SECRET))

    assert named(detail_of(log)["request_headers"], "authorization") is None
    assert SECRET not in repr(log.calls)


def test_the_certificate_a_secure_request_met_is_kept(serve: Serve) -> None:
    chain = make_chain()
    server = serve(
        lambda seen: Answer(body="ok", headers={"Content-Type": "text/plain"}), chain.full
    )
    log = Log()

    request(target(server, mode="ca", ca_pem=chain.root_pem), log, "GET", "/")

    detail = detail_of(log)
    assert detail["scheme"] == "https"
    certificate = detail["certificate"]
    assert set(certificate) == {"subject", "issuer", "fingerprint", "not_after"}
    assert certificate["fingerprint"].count(":") == 31
    assert log.calls[0].excerpt == "ok"


def test_a_request_that_got_no_answer_keeps_what_was_asked(serve: Serve) -> None:
    server = serve(lambda seen: Answer(drop=True))
    log = Log()

    with pytest.raises(CallFailed):
        request(target(server), log, "GET", "/gone", query={"limit": "5"})

    detail = detail_of(log)
    assert detail["path"] == "/gone"
    assert named(detail["query"], "limit") == "5"
    assert "status_line" not in detail
    assert log.calls[0].excerpt is None


def test_a_request_that_could_not_even_be_made_keeps_no_detail(serve: Serve) -> None:
    server = serve(lambda seen: Answer())
    log = Log()

    with pytest.raises(CallFailed):
        request(target(server), log, "GET", "/\x00")

    assert log.calls[0].detail is None


def test_the_answer_of_a_failed_request_is_kept(serve: Serve) -> None:
    server = serve(lambda seen: Answer(status=500, body="boom"))
    log = Log()

    request(target(server), log, "GET", "/x")

    assert log.calls[0].error == "Internal Server Error"
    assert log.calls[0].excerpt == "boom"
    assert detail_of(log)["status_line"].endswith("500 Internal Server Error")


def test_what_is_read_as_bytes_is_sized_and_not_given_as_text(serve: Serve) -> None:
    server = serve(
        lambda seen: Answer(
            body=bytes(range(256)) * 8, headers={"Content-Type": "application/x-pcap"}
        )
    )
    log = Log()

    request(target(server), log, "GET", "/capture", keep_bytes=100)

    detail = detail_of(log)
    assert (detail["size"], detail["cut"]) == (100, True)
    assert log.calls[0].excerpt is None


# -- a streamed answer


def test_a_streamed_request_keeps_the_start_of_its_answer(serve: Serve) -> None:
    server = serve(
        lambda seen: Answer(body="one\ntwo\nthree", headers={"Content-Type": "text/plain"})
    )
    log = Log()

    lines_of(target(server), log, "post", "/v1/messages", json_body={"stream": True})

    [call] = log.calls
    assert call.excerpt == "one\ntwo\nthree\n"
    assert call.detail is not None
    assert call.detail["size"] == len("one\ntwo\nthree") + 1
    assert call.detail["status_line"].endswith("200 OK")


def test_a_streamed_answer_is_kept_only_to_a_point(serve: Serve) -> None:
    line = "x" * 1000
    server = serve(
        lambda seen: Answer(body="\n".join([line] * 20), headers={"Content-Type": "text/plain"})
    )
    log = Log()

    lines_of(target(server), log, "GET", "/long")

    assert log.calls[0].excerpt is not None
    assert len(log.calls[0].excerpt) <= calldetail.EXCERPT_CHARS


def test_a_streamed_request_that_is_refused_keeps_how(serve: Serve) -> None:
    server = serve(lambda seen: Answer(status=401, body="no"))
    log = Log()

    with pytest.raises(client_not_success()):
        lines_of(target(server), log, "GET", "/x")

    assert detail_of(log)["status_line"].endswith("401 Unauthorized")


def client_not_success() -> type[Exception]:
    from app.integrations.client import NotSuccess

    return NotSuccess


def test_a_request_to_a_certificate_that_cannot_be_read_is_still_logged(
    serve: Serve, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(der: bytes) -> object:
        raise ValueError("odd")

    monkeypatch.setattr(netguard, "describe_certificate", broken)
    chain = make_chain()
    server = serve(lambda seen: Answer(body="ok"), chain.full)
    log = Log()

    request(target(server, mode="ca", ca_pem=chain.root_pem), log, "GET", "/")

    assert detail_of(log)["certificate"] is None


def test_the_client_can_be_used_without_a_recorder_that_looks(serve: Serve) -> None:
    server = serve(lambda seen: Answer(body="ok"))

    async def go() -> str:
        async with ApiClient(target(server), _nothing, HOME_NETWORK_AND_LOOPBACK, 5.0) as client:
            return (await client.request("GET", "/")).text

    assert asyncio.run(go()) == "ok"


async def _nothing(call: object) -> None:
    return None


def test_the_origin_of_the_detail_is_that_of_the_connection() -> None:
    assert Origin("https", "192.0.2.1", 8443).url == "https://192.0.2.1:8443"
