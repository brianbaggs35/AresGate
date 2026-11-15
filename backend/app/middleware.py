"""Gives every request an ID, and writes one log line for it when it's done."""

import logging
import re
import time
from uuid import uuid4

import anyio.to_thread
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app import answers
from app.logs import request_id

logger = logging.getLogger("aresgate.request")

HEADER = "X-Request-ID"
# What a trustworthy ID looks like. nginx makes one for each request (32 hex digits) and passes it
# on, replacing whatever the client sent, so a line in nginx's log and one in the API's match.
_VALID_ID = re.compile(r"[A-Za-z0-9._-]{8,64}")
_HEALTH_CHECK = "/api/health"
_LONGEST_PATH = 200


def _level(path: str, status: int) -> int:
    if status >= 500:
        return logging.ERROR
    # The container checks its health every few seconds, which isn't worth a line each.
    if path == _HEALTH_CHECK and status < 400:
        return logging.DEBUG
    return logging.INFO


class RequestContext:
    """The ID is on the response, in the header, and on every log line written while the request
    is served. The query string isn't logged, since it can carry what shouldn't be."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        sent = Headers(scope=scope).get(HEADER, "")
        identifier = sent if _VALID_ID.fullmatch(sent) else uuid4().hex
        # Not reset afterwards: each request is served in a task of its own, and the error that
        # ends a failed one is logged after this has returned, and should still have the ID.
        request_id.set(identifier)
        started = time.perf_counter()
        status = 500

        async def send_with_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                MutableHeaders(scope=message)[HEADER] = identifier
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            self._log(scope, status, time.perf_counter() - started)

    @staticmethod
    def _log(scope: Scope, status: int, seconds: float) -> None:
        method = scope["method"]
        path = str(scope["path"])[:_LONGEST_PATH]
        client = scope.get("client")
        logger.log(
            _level(path, status),
            "%s %s %d",
            method,
            path,
            status,
            extra={
                "method": method,
                "path": path,
                "status": status,
                "duration_ms": round(seconds * 1000, 1),
                "client": client[0] if client else None,
            },
        )


SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class NoteChanges:
    """Writes down, for the answers that are kept for a few seconds, that a change succeeded. It
    is written before the reply starts, so by the time the person sees that their change was made,
    the next request in any worker builds its answer afresh. A failure to write it is logged and
    changes nothing: the answers are then kept for no longer than their seconds."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] in SAFE_METHODS:
            await self.app(scope, receive, send)
            return

        async def send_after_noting(message: Message) -> None:
            if message["type"] == "http.response.start" and message["status"] < 400:
                try:
                    sessions = scope["app"].state.sessions()
                    await anyio.to_thread.run_sync(answers.stamp_change, sessions)
                except Exception:
                    logger.warning(
                        "A change could not be noted for the kept answers", exc_info=True
                    )
            await send(message)

        await self.app(scope, receive, send_after_noting)
