"""Lets Ollama's SDK send through ``ApiClient``.

OpenAI's and Anthropic's SDKs are built on the same HTTP library as AresGate (``httpx2``), so
``ApiClient.sdk_http`` is the client they are given. Ollama's SDK is built on the older ``httpx``,
which has its own request and response types. This transport is what Ollama's SDK is given
instead: it turns each of its requests into one of ``httpx2``'s, sends that through the
``ApiClient`` (so it is kept to the addresses its provider may be at, logged without any secret
and limited in how much it reads, as every other request is) and turns the answer back.
"""

from collections.abc import AsyncIterator

import httpx
import httpx2

from app.integrations.client import ApiClient


class _Answer(httpx.AsyncByteStream):
    """The body of an answer of ``httpx2``, as ``httpx`` reads it."""

    def __init__(self, body: httpx2.Response) -> None:
        self._body = body

    async def __aiter__(self) -> AsyncIterator[bytes]:
        async for chunk in self._body.aiter_raw():
            yield chunk

    async def aclose(self) -> None:
        await self._body.aclose()


class OllamaTransport(httpx.AsyncBaseTransport):
    """The transport of Ollama's SDK. ``headers_dropped`` are names of headers it must not send:
    the SDK adds ``Authorization`` from the environment when it has no key of its own."""

    def __init__(self, api: ApiClient, headers_dropped: tuple[str, ...] = ()) -> None:
        self._api = api
        self._dropped = tuple(name.lower() for name in headers_dropped)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        content = await request.aread()
        headers = [(name, value) for name, value in request.headers.raw]
        built = httpx2.Request(
            request.method,
            str(request.url),
            headers=[
                (name, value)
                for name, value in headers
                if name.decode().lower() not in self._dropped
            ],
            content=content,
            extensions=request.extensions,
        )
        answer = await self._api.send_recorded(built)
        return httpx.Response(
            answer.status_code,
            headers=answer.headers.raw,
            stream=_Answer(answer),
            extensions={"http_version": answer.http_version.encode()},
        )
