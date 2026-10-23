"""What an event is when a collector hands it over, before it is stored: the same few fields
whatever program it came from, and the program's own record beside them."""

import json
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum
from hashlib import sha256
from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import Any, cast

from app.audit import clean

# The most the program's own record may take up in the database. A bigger one is replaced by a
# note of its size, because the fields beside it are what pages and alerts read.
MAX_RAW_BYTES = 64 * 1024
MAX_SUMMARY = 500
MAX_SIGNATURE = 256
MAX_PROTOCOL = 16

# Lowercase words, digits and hyphens: what an integration, a connection and a kind are called.
_KEY = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


class Severity(IntEnum):
    """How serious an event is, from least to most. The web app calls them info, low, medium,
    high and critical."""

    INFO = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass(frozen=True)
class NewEvent:
    """An event as a collector found it. The key, the connection and the kind are the
    collector's own words and are checked; everything the program reported is taken as it comes
    and cleaned up on the way in, because it may hold anything."""

    # The integration and the connection it was read from, such as wazuh and indexer.
    source: str
    connection: str
    # What sort of event it is, in a word: alert, firewall, authentication.
    kind: str
    severity: Severity
    # When it happened, as the program says.
    occurred_at: datetime
    # What makes it this event at the source: its id there, or else the facts that together
    # can't be anyone else's. Reading it again later gives the same, so it is stored once.
    identity: Sequence[str | int]
    summary: str
    signature: str | None = None
    src_address: str | None = None
    src_port: int | None = None
    dst_address: str | None = None
    dst_port: int | None = None
    protocol: str | None = None
    raw: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        for name, value in (("source", self.source), ("connection", self.connection)):
            if not _KEY.match(value):
                raise ValueError(f"An event's {name} is a short lowercase name, not {value!r}.")
        if not _KEY.match(self.kind):
            raise ValueError(f"An event's kind is a short lowercase name, not {self.kind!r}.")
        if self.occurred_at.tzinfo is None:
            raise ValueError("An event's time must have a time zone.")
        if not self.identity:
            raise ValueError("An event needs something that says which event it is.")

    @property
    def fingerprint(self) -> str:
        return fingerprint(self.source, self.identity)

    def row(self, received_at: datetime) -> dict[str, Any]:
        """The event as the columns of its table."""
        return {
            "occurred_at": self.occurred_at,
            "received_at": received_at,
            "source": self.source,
            "connection": self.connection,
            "kind": self.kind,
            "severity": int(self.severity),
            "summary": _text(self.summary, MAX_SUMMARY) or "",
            "signature": _text(self.signature, MAX_SIGNATURE),
            "src_address": _address(self.src_address),
            "src_port": _port(self.src_port),
            "dst_address": _address(self.dst_address),
            "dst_port": _port(self.dst_port),
            "protocol": _protocol(self.protocol),
            "fingerprint": self.fingerprint,
            "raw": _raw(self.raw),
        }


def fingerprint(source: str, identity: Sequence[str | int]) -> str:
    """A hash of which event it is, for telling one read twice from two that look alike."""
    return sha256(json.dumps([source, *identity]).encode("ascii")).hexdigest()


def _text(value: str | None, limit: int) -> str | None:
    """Text from a program, made safe to keep: control characters become spaces, anything that
    isn't text is replaced, and it's cut to fit."""
    cleaned = clean(value, limit)
    return None if cleaned is None else cleaned.encode("utf-8", "replace").decode("utf-8")


def _address(value: str | None) -> IPv4Address | IPv6Address | None:
    """The address, or nothing for what isn't one: a program that says "unknown" or a host name
    where an address belongs shouldn't cost the event."""
    if value is None:
        return None
    try:
        # A link-local address may say which interface it was on, which the database can't hold.
        return ip_address(value.strip().partition("%")[0])
    except ValueError:
        return None


def _port(value: int | None) -> int | None:
    return value if value is not None and 0 <= value <= 65535 else None


def _protocol(value: str | None) -> str | None:
    text = _text(value, MAX_PROTOCOL)
    return None if text is None else text.lower()


def _raw(value: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    safe = _scrub(value)
    size = len(json.dumps(safe, ensure_ascii=False).encode("utf-8"))
    if size > MAX_RAW_BYTES:
        return {"truncated": True, "bytes": size}
    return safe


def _scrub(value: object) -> Any:
    """JSON the database accepts: no NUL characters or lone surrogates in text, no NaN or
    infinity, and a string for anything that isn't JSON at all."""
    if isinstance(value, str):
        return value.replace("\x00", "").encode("utf-8", "replace").decode("utf-8")
    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Mapping):
        return {
            _scrub(str(key)): _scrub(item)
            for key, item in cast(Mapping[object, object], value).items()
        }
    if isinstance(value, Sequence | set | frozenset):
        return [_scrub(item) for item in cast(Iterable[object], value)]
    return str(value)
