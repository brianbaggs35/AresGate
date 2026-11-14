"""The one way AresGate makes a request to an integration.

Every request goes through ``ApiClient``, which keeps it on the home network and checks the
certificate (see ``netguard``), never follows a redirect, limits how much it reads and how long
it waits, and writes an entry in the API log for it, whether it worked or not. The entry holds
the method, the path without its query string, the status, how long it took and a short reason
for a failure. It never holds a secret: the ones this connection uses are replaced wherever
they turn up in a message, and what the integration itself says is not quoted.

The integration pages use it to test a connection, and the collectors that read from the
integrations use it for everything else.
"""

import asyncio
import json
import logging
import ssl
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from http import HTTPStatus
from types import TracebackType
from typing import Self

import httpx2

from app import __version__, audit
from app.integrations import certdiag, netguard
from app.integrations.netguard import AddressPolicy, GuardedBackend, GuardedTransport, Origin
from app.models import utcnow

logger = logging.getLogger(__name__)

# More than any answer AresGate asks for is, so a system that never stops sending can't fill
# the memory.
MAX_BODY = 2 * 1024 * 1024
# The whole request, from connecting to the last byte.
DEADLINE = 20.0
# How long to wait for the next of an answer, which a model that is thinking takes longer to start.
READ_TIMEOUT = 10.0
MAX_PATH = 256
MAX_ERROR = 500
HIDDEN = "***"


@dataclass(frozen=True)
class Call:
    """A request that has been made, as the API log keeps it."""

    occurred_at: datetime
    integration: str
    connection: str
    method: str
    path: str
    status_code: int | None
    duration_ms: int
    error: str | None


Recorder = Callable[[Call], Awaitable[None]]


@dataclass(frozen=True)
class Target:
    """A connection ready to be used: where it is, how to check it and what it needs."""

    integration: str
    connection: str
    origin: Origin
    tls_mode: str
    tls_ca_pem: str | None
    tls_fingerprint: str | None
    options: Mapping[str, str | int]
    secrets: Mapping[str, str]


@dataclass(frozen=True)
class Reply:
    """What an integration answered."""

    status: int
    text: str
    # What it said in its headers, with the names in lower case.
    headers: Mapping[str, str] = field(default_factory=dict[str, str])
    # The body as it came, for a request that asked for bytes (a packet capture), where ``text``
    # is empty. ``cut`` says it was stopped at the most that was asked for.
    content: bytes = b""
    cut: bool = False

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    def json(self) -> object:
        """The body as JSON, or None if it isn't."""
        try:
            return json.loads(self.text)
        except ValueError:
            return None


class CallFailed(Exception):
    """No answer came. The message says why, and holds no secret."""


def in_chain[E: BaseException](error: BaseException, kind: type[E]) -> E | None:
    """The first error of a kind among this one and the errors that caused it."""
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        if isinstance(current, kind):
            return current
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return None


class ApiClient:
    """Makes requests to one connection, and logs each of them. Use it as ``async with``."""

    def __init__(
        self,
        target: Target,
        record: Recorder,
        policy: AddressPolicy = netguard.HOME_NETWORK,
        deadline: float = DEADLINE,
        read_timeout: float = READ_TIMEOUT,
    ) -> None:
        self._target = target
        self._record = record
        self._policy = policy
        self._deadline = deadline
        self._hidden = [value for value in target.secrets.values() if len(value) >= 4]
        pin = target.tls_fingerprint if target.tls_mode == "pinned" else None
        self._http = httpx2.AsyncClient(
            base_url=target.origin.url,
            transport=GuardedTransport(
                netguard.tls_context(target.tls_mode, target.tls_ca_pem),
                GuardedBackend(self._policy, pin),
            ),
            # The environment's proxy settings are for the internet: a request to a device on the
            # home network goes straight to it.
            trust_env=False,
            follow_redirects=False,
            timeout=httpx2.Timeout(read_timeout, connect=5.0),
            headers={"User-Agent": f"AresGate/{__version__}", "Accept": "application/json"},
        )

    def hide(self, value: str) -> None:
        """Keeps a value, such as a token the integration handed out, out of every message."""
        if len(value) >= 4:
            self._hidden.append(value)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self._http.aclose()

    def _scrub(self, text: str) -> str:
        for value in self._hidden:
            text = text.replace(value, HIDDEN)
        return (audit.clean(text, MAX_ERROR) or "")[:MAX_ERROR]

    async def _explain(self, error: BaseException) -> str:
        """What went wrong with a request that got no answer, in words for whoever set it up."""
        where = f"{self._target.origin.host}:{self._target.origin.port}"
        if isinstance(error, CallFailed):
            return str(error)
        if refusal := in_chain(error, netguard.Refused):
            return str(refusal)
        if untrusted := in_chain(error, ssl.SSLCertVerificationError):
            return await self._explain_certificate(untrusted)
        if failed := in_chain(error, ssl.SSLError):
            return f"The secure connection to {where} failed ({failed.reason or 'TLS error'})."
        if isinstance(error, TimeoutError | httpx2.TimeoutException):
            return f"{where} didn't answer in time."
        if refused := in_chain(error, OSError):
            return f"Couldn't connect to {where}: {refused.strerror or 'the connection failed'}."
        if isinstance(error, httpx2.HTTPError):
            return f"The connection to {where} broke, or it isn't a web server."
        logger.error("A request to %s failed in an unexpected way", where, exc_info=error)
        return "The request failed in a way AresGate didn't expect."

    async def _explain_certificate(self, untrusted: ssl.SSLCertVerificationError) -> str:
        """Why the system's certificate wasn't trusted. OpenSSL's own words are the same for a
        certificate sent without the one that signed it and one signed by an unknown authority,
        so the certificates the system presents are looked at again to tell which it is."""
        target = self._target
        try:
            der = await netguard.look_up_chain(self._policy, target.origin)
        except netguard.Refused, OSError:
            der = []
        return certdiag.explain(
            untrusted, certdiag.read_chain(der), target.tls_mode, target.origin.host
        )

    async def request(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, str] | None = None,
        json_body: object = None,
        headers: Mapping[str, str] | None = None,
        auth: tuple[str, str] | None = None,
        keep_bytes: int | None = None,
    ) -> Reply:
        """Sends a request and returns what came back, whatever its status. Raises
        ``CallFailed`` if nothing came back. Either way the call is logged. ``keep_bytes`` is for
        an answer that isn't text: the body is kept as it is in ``Reply.content``, and what comes
        after that many bytes is left unread instead of being an error."""
        started = time.monotonic()
        occurred_at = utcnow()
        status: int | None = None
        error: str | None = None
        try:
            reply = await self._send(method, path, query, json_body, headers, auth, keep_bytes)
            status = reply.status
            if 300 <= status < 400:
                error = "Redirected to another address, which AresGate doesn't follow."
            elif status >= 400:
                error = _phrase(status)
            return reply
        except Exception as problem:
            error = self._scrub(await self._explain(problem))
            raise CallFailed(error) from None
        finally:
            await self._log(
                Call(
                    occurred_at=occurred_at,
                    integration=self._target.integration,
                    connection=self._target.connection,
                    method=method.upper()[:8],
                    path=clean_path(path),
                    status_code=status,
                    duration_ms=round((time.monotonic() - started) * 1000),
                    error=error,
                )
            )

    async def _send(
        self,
        method: str,
        path: str,
        query: Mapping[str, str] | None,
        json_body: object,
        headers: Mapping[str, str] | None,
        auth: tuple[str, str] | None,
        keep_bytes: int | None,
    ) -> Reply:
        if self._policy.read_only and method.upper() != "GET":
            raise CallFailed(
                "This service is only read, so AresGate sends it nothing that changes."
            )
        async with (
            asyncio.timeout(self._deadline),
            self._http.stream(
                method, path, params=query, json=json_body, headers=headers, auth=auth
            ) as response,
        ):
            body = bytearray()
            cut = False
            limit = MAX_BODY if keep_bytes is None else keep_bytes
            async for chunk in response.aiter_bytes():
                body += chunk
                if len(body) > limit:
                    if keep_bytes is None:
                        raise CallFailed("It answered with more than AresGate reads.")
                    del body[limit:]
                    cut = True
                    break
            return Reply(
                response.status_code,
                body.decode("utf-8", errors="replace") if keep_bytes is None else "",
                {name.lower(): value for name, value in response.headers.items()},
                bytes(body) if keep_bytes is not None else b"",
                cut,
            )

    async def _log(self, call: Call) -> None:
        try:
            await self._record(call)
        except Exception:
            # The call matters more than its log entry: say so and carry on.
            logger.exception("Couldn't write an API log entry")


def _phrase(status: int) -> str:
    try:
        return HTTPStatus(status).phrase
    except ValueError:
        return f"HTTP {status}"


def clean_path(path: str) -> str:
    """A path without a query string or fragment, which is where secrets would be."""
    return audit.clean(path.partition("?")[0].partition("#")[0], MAX_PATH) or "/"
