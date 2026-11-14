"""What the API log keeps of a request beyond its method, path and status, for a person who clicks
an entry to see everything about it.

None of it is a secret. A header or query parameter whose name says it holds a credential
(``Authorization``, ``X-Api-Key``, ``token``, ``password``) is kept by name and its value is
left out, and the secrets the connection holds are replaced wherever they appear, in the
address, the headers and the excerpt of the answer. The answer's excerpt is the integration's own
text, so it is kept short, with the values under keys such as ``token`` hidden, and shown as plain
text only.
"""

import contextlib
import json
import re
import ssl
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Final, cast

import httpx2

from app.integrations import netguard
from app.integrations.netguard import Origin

# How much of an answer is kept, in characters.
EXCERPT_CHARS: Final = 4096
# How many answers of requests that worked are kept for each connection. Those of requests that
# failed are all kept, until the log's retention ends them.
KEPT_WHEN_WORKED: Final = 10
MAX_VALUE: Final = 500
MAX_PAIRS: Final = 60
# A name that says what follows is a credential.
SECRET_NAME: Final = re.compile(
    r"auth|key|token|secret|cookie|passw|credential|session|signature|jwt", re.IGNORECASE
)
# A JSON web token, which a login answers with.
WEB_TOKEN: Final = re.compile(r"eyJ[\w-]{8,}\.[\w-]{8,}\.[\w-]*")
BEARER: Final = re.compile(r"(?i)\b(bearer|basic)\s+[\w.~+/=-]{6,}")
TEXTUAL: Final = ("text/", "json", "xml", "javascript", "x-www-form-urlencoded", "x-ndjson")
HIDDEN: Final = "***"

Mask = Callable[[str], str]


@dataclass(frozen=True)
class Seen:
    """What came back, as far as it is known."""

    status_line: str
    headers: tuple[tuple[str, str], ...]
    size: int
    cut: bool
    first_byte_ms: int
    address: str | None
    certificate: dict[str, str] | None
    excerpt: str | None


def is_secret_name(name: str) -> bool:
    return SECRET_NAME.search(name) is not None


def _short(value: str) -> str:
    return value if len(value) <= MAX_VALUE else value[: MAX_VALUE - 1] + "…"


def pairs(items: Iterable[tuple[str, str]], mask: Mask) -> list[dict[str, str | None]]:
    """Names and values for showing, with the value left out (None) where the name says it is a
    credential, and the connection's own secrets replaced elsewhere."""
    return [
        {"name": name[:100], "value": None if is_secret_name(name) else _short(mask(value))}
        for name, value in list(items)[:MAX_PAIRS]
    ]


def address_of(stream: object) -> str | None:
    getter = getattr(stream, "get_extra_info", None)
    server = getter("server_addr") if callable(getter) else None
    if isinstance(server, tuple) and server:
        return str(server[0])  # pyright: ignore[reportUnknownArgumentType]
    return None


def certificate_of(stream: object) -> dict[str, str] | None:
    getter = getattr(stream, "get_extra_info", None)
    secured = getter("ssl_object") if callable(getter) else None
    if not isinstance(secured, ssl.SSLObject):
        return None
    der = secured.getpeercert(binary_form=True)
    if not der:
        return None
    try:
        found = netguard.describe_certificate(der)
    except ValueError:
        return None
    return {
        "subject": found.subject,
        "issuer": found.issuer,
        "fingerprint": found.fingerprint,
        "not_after": found.not_after.isoformat(),
    }


def _redacted(value: object) -> object:
    """JSON with what is under a key that names a credential left out."""
    if isinstance(value, dict):
        items = cast("dict[object, object]", value)
        return {
            key: HIDDEN if is_secret_name(str(key)) and item else _redacted(item)
            for key, item in items.items()
        }
    if isinstance(value, list):
        return [_redacted(item) for item in cast("list[object]", value)]
    return value


def _is_text(content_type: str | None, sample: bytes) -> bool:
    if content_type:
        return any(kind in content_type.lower() for kind in TEXTUAL)
    return b"\0" not in sample


def excerpt_of(body: bytes, content_type: str | None, mask: Mask) -> str | None:
    """The start of an answer to show: JSON laid out for reading, anything else as it is, and
    nothing for what is not text. Secrets the connection holds, tokens and the values under keys
    that name a credential are left out."""
    if not body or not _is_text(content_type, body[:512]):
        return None
    text = body.decode("utf-8", errors="replace")
    if "json" in (content_type or "") or text.lstrip()[:1] in ("{", "["):
        with contextlib.suppress(ValueError):
            text = json.dumps(_redacted(json.loads(text)), indent=2, ensure_ascii=False)
    text = BEARER.sub(r"\1 " + HIDDEN, WEB_TOKEN.sub(HIDDEN, mask(text)))
    return text[: EXCERPT_CHARS - 1] + "…" if len(text) > EXCERPT_CHARS else text


def look_at(
    response: httpx2.Response, body: bytes, size: int, cut: bool, first_byte_ms: int, mask: Mask
) -> Seen:
    """What a response shows of itself. ``body`` is the start of what was read of it, which was
    ``size`` bytes."""
    kind = response.headers.get("content-type")
    stream = response.extensions.get("network_stream")
    return Seen(
        status_line=(
            f"{response.http_version} {response.status_code} {response.reason_phrase}".strip()
        ),
        headers=tuple(response.headers.multi_items()),
        size=size,
        cut=cut,
        first_byte_ms=first_byte_ms,
        address=address_of(stream),
        certificate=certificate_of(stream) if response.request.url.scheme == "https" else None,
        excerpt=excerpt_of(body, kind, mask),
    )


def describe(
    origin: Origin,
    request: httpx2.Request,
    path: str,
    caller: str | None,
    seen: Seen | None,
    mask: Mask,
) -> dict[str, Any]:
    """The detail of one request for the log: where it went, what it carried and, if it was
    answered, what the answer was."""
    detail: dict[str, Any] = {
        "scheme": origin.scheme,
        "host": origin.host,
        "port": origin.port,
        "path": path,
        "query": pairs(request.url.params.multi_items(), mask),
        "request_headers": pairs(request.headers.multi_items(), mask),
        "caller": caller,
    }
    if seen is not None:
        detail |= {
            "first_byte_ms": seen.first_byte_ms,
            "status_line": seen.status_line,
            "response_headers": pairs(seen.headers, mask),
            "size": seen.size,
            "cut": seen.cut,
            "content_type": next(
                (value for name, value in seen.headers if name.lower() == "content-type"), None
            ),
            "certificate": seen.certificate,
            "address": seen.address,
        }
    return detail
