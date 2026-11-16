"""What the SDKs send through: ``ApiClient.sdk_http`` and Ollama's bridge to it. Each request an
SDK makes is kept to the addresses it may be at, limited in what it reads, held to the deadline
and written to the API log without a secret, as ``ApiClient.request`` does for the others."""

import asyncio
import json
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import httpx
import httpx2
import pytest

from app.ai import bridge, catalog, wire
from app.integrations import client as client_module
from app.integrations import netguard
from app.integrations.client import ApiClient, Call, CallFailed, Target
from app.integrations.netguard import HOME_NETWORK, HOME_NETWORK_AND_LOOPBACK
from tests.stubs import Answer, Seen, Serve, StubServer

KEY = "sk-an-api-key-for-tests-0123456789"


class Log:
    def __init__(self) -> None:
        self.calls: list[Call] = []

    async def __call__(self, call: Call) -> None:
        self.calls.append(call)


def target(server: StubServer) -> Target:
    return Target(
        integration="ai",
        connection="openai",
        origin=netguard.parse_origin(server.url, allow_http=True),
        tls_mode="system",
        tls_ca_pem=None,
        tls_fingerprint=None,
        options={},
        secrets={"api_key": KEY},
    )


def through(
    server: StubServer,
    action: Callable[[ApiClient], Any],
    *,
    policy: netguard.AddressPolicy = HOME_NETWORK_AND_LOOPBACK,
    deadline: float = 20.0,
) -> tuple[Any, Log]:
    log = Log()

    async def go() -> Any:
        async with ApiClient(target(server), log, policy, deadline) as client:
            return await action(client)

    return asyncio.run(go()), log


async def get(client: ApiClient, path: str = "/v1/models", **headers: str) -> httpx2.Response:
    async with client.sdk_http() as http:
        return await http.get(f"{client.origin_url}{path}", headers=headers)


class TestTheLogOfWhatAnSdkSends:
    def test_a_request_is_logged_like_any_other_without_the_key(self, serve: Serve) -> None:
        server = serve(lambda seen: Answer(body=json.dumps({"echo": KEY, "fine": True})))

        reply, log = through(server, lambda client: get(client, Authorization=f"Bearer {KEY}"))

        [call] = log.calls
        assert reply.status_code == 200
        assert (call.integration, call.connection, call.method) == ("ai", "openai", "GET")
        assert (call.path, call.status_code, call.error) == ("/v1/models", 200, None)
        assert call.detail is not None
        assert KEY not in json.dumps(call.detail)
        assert call.excerpt is not None
        assert KEY not in call.excerpt
        assert "fine" in call.excerpt

    def test_a_status_that_is_not_a_success_is_logged_with_what_it_means(
        self, serve: Serve
    ) -> None:
        server = serve(lambda seen: Answer(status=429, body="{}"))

        reply, log = through(server, get)

        assert reply.status_code == 429
        assert [(call.status_code, call.error) for call in log.calls] == [
            (429, "Too Many Requests")
        ]

    def test_a_redirect_is_not_followed(self, serve: Serve) -> None:
        server = serve(lambda seen: Answer(status=302, headers={"Location": "http://elsewhere/"}))

        reply, log = through(server, get)

        assert reply.status_code == 302
        assert [call.error for call in log.calls] == [client_module.REDIRECTED]
        assert len(server.seen) == 1

    def test_an_address_it_may_not_use_is_refused_and_logged(self, serve: Serve) -> None:
        server = serve(lambda seen: Answer())

        with pytest.raises(CallFailed) as refused:
            through(server, get, policy=HOME_NETWORK)

        assert server.seen == []
        assert str(refused.value)

    def test_the_refusal_is_in_the_log(self, serve: Serve) -> None:
        server = serve(lambda seen: Answer())
        log = Log()

        async def go() -> None:
            async with ApiClient(target(server), log, HOME_NETWORK) as client:
                with pytest.raises(CallFailed):
                    await get(client)

        asyncio.run(go())

        [call] = log.calls
        assert (call.status_code, call.error is not None) == (None, True)

    def test_a_service_that_is_only_read_is_sent_nothing_that_changes(self, serve: Serve) -> None:
        server = serve(lambda seen: Answer())
        reading = replace(HOME_NETWORK_AND_LOOPBACK, read_only=True)

        async def post(client: ApiClient) -> None:
            async with client.sdk_http() as http:
                await http.post(f"{client.origin_url}/v1/x", json={})

        with pytest.raises(CallFailed, match="only read"):
            through(server, post, policy=reading)

        assert server.seen == []

    def test_an_answer_that_is_too_long_is_not_read(
        self, serve: Serve, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(client_module, "MAX_BODY", 100)
        server = serve(lambda seen: Answer(body="x" * 5000))
        log = Log()

        async def go() -> None:
            async with ApiClient(target(server), log, HOME_NETWORK_AND_LOOPBACK) as client:
                with pytest.raises(CallFailed, match="more than AresGate reads"):
                    await get(client)

        asyncio.run(go())

        assert "more than AresGate reads" in str(log.calls[0].error)

    def test_a_connection_that_breaks_is_said_so(self, serve: Serve) -> None:
        server = serve(lambda seen: Answer(drop=True))

        with pytest.raises(CallFailed, match="broke, or it isn't a web server"):
            through(server, get)

    def test_a_request_is_held_to_the_deadline(self, serve: Serve) -> None:
        server = serve(lambda seen: Answer(delay=2.0))

        async def slow(client: ApiClient) -> None:
            async with client.within_deadline():
                await get(client)

        with pytest.raises(CallFailed, match="didn't answer in time"):
            through(server, slow, deadline=0.3)

    def test_what_is_dropped_is_not_sent(self, serve: Serve) -> None:
        server = serve(lambda seen: Answer(body="{}"))

        async def send(client: ApiClient) -> None:
            async with client.sdk_http(("openai-organization",)) as http:
                await http.get(
                    f"{client.origin_url}/v1/models", headers={"OpenAI-Organization": "org-x"}
                )

        through(server, send)

        assert "openai-organization" not in server.seen[0].headers


class TestOllamasBridge:
    def test_what_ollamas_sdk_sends_goes_through_the_client_and_is_logged(
        self, serve: Serve
    ) -> None:
        seen: list[Seen] = []

        def handle(request: Seen) -> Answer:
            seen.append(request)
            return Answer(body=json.dumps({"models": []}))

        server = serve(handle)

        async def ask(client: ApiClient) -> list[wire.FoundModel]:
            return await wire.list_models(client, catalog.OLLAMA, None)

        found, log = through(server, ask)

        assert found == []
        assert [(call.method, call.path, call.status_code) for call in log.calls] == [
            ("GET", "/api/tags", 200)
        ]

    def test_a_key_from_the_environment_is_not_sent_when_there_is_none(
        self, serve: Serve, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OLLAMA_API_KEY", "a-key-that-is-not-for-this")
        server = serve(lambda seen: Answer(body=json.dumps({"models": []})))

        through(server, lambda client: wire.list_models(client, catalog.OLLAMA, None))

        assert "authorization" not in server.seen[0].headers

    def test_the_key_that_was_given_is_sent(
        self, serve: Serve, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OLLAMA_API_KEY", "a-key-that-is-not-for-this")
        server = serve(lambda seen: Answer(body=json.dumps({"models": []})))

        through(server, lambda client: wire.list_models(client, catalog.OLLAMA_CLOUD, KEY))

        assert server.seen[0].headers["authorization"] == f"Bearer {KEY}"

    def test_an_answer_goes_back_to_ollamas_sdk_as_it_came(self, serve: Serve) -> None:
        server = serve(lambda seen: Answer(status=404, body='{"error": "no"}'))

        async def ask(client: ApiClient) -> httpx.Response:
            transport = bridge.OllamaTransport(client)
            async with httpx.AsyncClient(transport=transport) as http:
                return await http.get(f"{client.origin_url}/api/tags")

        answer, _ = through(server, ask)

        assert (answer.status_code, answer.json()) == (404, {"error": "no"})


class _Body(httpx2.AsyncByteStream):
    """An answer's body that gives what it is told to, then raises what it is told to."""

    def __init__(self, chunks: list[bytes], then: BaseException | None = None) -> None:
        self._chunks = chunks
        self._then = then
        self.closed = 0

    async def __aiter__(self):  # type: ignore[no-untyped-def]
        for chunk in self._chunks:
            yield chunk
        if self._then is not None:
            raise self._then

    async def aclose(self) -> None:
        self.closed += 1


class TestWatchedBody:
    """What is written of an answer when its reading is cut short or closed twice."""

    @staticmethod
    def watch(body: _Body) -> tuple[client_module._Watched, list[tuple[bytes, int, str | None]]]:  # pyright: ignore[reportPrivateUsage]
        written: list[tuple[bytes, int, str | None]] = []

        async def explain(problem: BaseException) -> str:
            return f"explained {problem.__class__.__name__}"

        async def finish(kept: bytes, size: int, error: str | None) -> None:
            written.append((kept, size, error))

        return client_module._Watched(body, explain, finish), written  # pyright: ignore[reportPrivateUsage]

    def test_a_reading_that_is_stopped_is_written_as_stopped(self) -> None:
        async def go() -> list[tuple[bytes, int, str | None]]:
            body = _Body([b"ab"], asyncio.CancelledError())
            watched, written = self.watch(body)
            with pytest.raises(asyncio.CancelledError):
                async for _ in watched:
                    pass
            await watched.aclose()
            return written

        written = asyncio.run(go())

        assert written == [(b"ab", 2, "The request was stopped before it ended.")]

    def test_a_body_that_is_closed_twice_is_written_once(self) -> None:
        async def go() -> tuple[list[tuple[bytes, int, str | None]], int]:
            body = _Body([b"abc"])
            watched, written = self.watch(body)
            async for _ in watched:
                pass
            await watched.aclose()
            await watched.aclose()
            return written, body.closed

        written, closed = asyncio.run(go())

        assert written == [(b"abc", 3, None)]
        assert closed == 2

    def test_a_failure_is_explained_and_raised_as_a_failed_call(self) -> None:
        async def go() -> list[tuple[bytes, int, str | None]]:
            watched, written = self.watch(_Body([b"a"], OSError("reset")))
            with pytest.raises(CallFailed, match="explained OSError"):
                async for _ in watched:
                    pass
            return written

        assert asyncio.run(go()) == []

    def test_only_the_start_of_a_long_body_is_kept_for_the_log(self) -> None:
        size = client_module.calldetail.EXCERPT_CHARS

        async def go() -> list[tuple[bytes, int, str | None]]:
            watched, written = self.watch(_Body([b"a" * size, b"b" * 10]))
            async for _ in watched:
                pass
            await watched.aclose()
            return written

        ((kept, read, error),) = asyncio.run(go())

        assert (kept, read, error) == (b"a" * size, size + 10, None)
