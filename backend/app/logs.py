"""Logs as one JSON object per line, each tied to its request by an ID, with anything that looks
like a secret blanked out before it is written.

Redaction is a last line of defence, not a licence to log secrets: code shouldn't put them in a
message in the first place. It catches what slips in anyway, such as the parameters in a database
error. It works by name (a value that follows ``password``, ``token``, ``cookie`` and the like),
by shape (a password hash, a bearer token, a private key, a setup code) and by value (the app
secret key, wherever it appears).
"""

import json
import logging
import re
import sys
from collections.abc import Iterable, Mapping
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any, Final, TextIO, cast, override

from app.config import Settings

REDACTED: Final = "[redacted]"

# Which request the code running now is serving. Set by the request middleware.
request_id: ContextVar[str | None] = ContextVar("request_id", default=None)

# A name that holds a secret. A few are matched whole, so that ``max_tokens`` and ``footprint``
# aren't mistaken for one.
_SENSITIVE_NAMES = (
    r"pass(?:word|wd|phrase)|secret|authorization|credential|cookie|csrf|api[-_]?key|"
    r"private[-_]?key|token(?!s)|(?<![a-z])t?otp(?![a-z])|setup[-_]?code|recovery[-_]?code|"
    r"signature"
)
_SENSITIVE_RE: Final = re.compile(_SENSITIVE_NAMES, re.IGNORECASE)

# ``name: value``, ``name=value``, and the quoted forms of both. The name can't start in the
# middle of a word, which keeps the scan linear however long the text is.
_PAIR: Final = re.compile(
    r"""(?<![\w.-])(?P<name>["']?[\w.-]+["']?)(?P<separator>\s*[:=]\s*)"""
    r"""(?P<value>"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|[^\s,;&}\]"']+)"""
)
# Headers carry the whole line, e.g. ``Cookie: a=1; b=2`` or ``Authorization: Bearer abc``.
_HEADER: Final = re.compile(
    r"(?<![\w-])(?P<name>(?:proxy-)?authorization|(?:set-)?cookie)(?P<separator>\s*:\s*)[^\r\n]+",
    re.IGNORECASE,
)
# What a secret looks like, wherever it turns up.
_SHAPES: Final = tuple(
    re.compile(pattern, flags)
    for pattern, flags in (
        (r"\$argon2(?:id|i|d)\$[^\s'\"]+", 0),
        (r"\b(?:Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
        (r"\beyJ[\w-]{5,}\.[\w-]{5,}\.[\w-]*", 0),
        (r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)", 0),
        # The setup code's alphabet and shape.
        (r"\b[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}\b", 0),
        # The user and password in a URL such as postgresql://user:password@host.
        (r"(?<=://)[^/\s:@]+:[^/\s@]+(?=@)", 0),
    )
)
# A short value would blank out ordinary words.
_SHORTEST_SECRET: Final = 8


def is_secret_name(name: str) -> bool:
    return _SENSITIVE_RE.search(name) is not None


class Redactor:
    """Blanks out secrets in text and in structured values."""

    def __init__(self, secrets: Iterable[str] = ()) -> None:
        # Longest first, so a secret that contains another is blanked out whole.
        self._secrets = sorted(
            {secret for secret in secrets if len(secret) >= _SHORTEST_SECRET},
            key=len,
            reverse=True,
        )

    def text(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, REDACTED)
        text = _PAIR.sub(self._pair, text)
        # After the pairs, which only get as far as the first word of a header's value.
        text = _HEADER.sub(lambda match: f"{match['name']}{match['separator']}{REDACTED}", text)
        for shape in _SHAPES:
            text = shape.sub(REDACTED, text)
        return text

    @staticmethod
    def _pair(match: re.Match[str]) -> str:
        if not is_secret_name(match["name"]):
            return match[0]
        return f"{match['name']}{match['separator']}{REDACTED}"

    def data(self, value: object, name: str | None = None) -> object:
        """A structured value with the secrets blanked out: everything under a secret's name, and
        the secrets in any text."""
        if name is not None and is_secret_name(name):
            return REDACTED
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, Mapping):
            mapping = cast("Mapping[object, object]", value)
            return {str(key): self.data(item, str(key)) for key, item in mapping.items()}
        if isinstance(value, (list, tuple, set, frozenset)):
            return [self.data(item) for item in cast("Iterable[object]", value)]
        return value


# What every log record has, so that anything else on one was added by the caller (``extra=``).
_STANDARD_FIELDS: Final = frozenset(
    set(vars(logging.LogRecord("", 0, "", 0, "", None, None)))
    # uvicorn adds a copy of its message with terminal colours in it.
    | {"message", "asctime", "taskName", "color_message"}
)
_OWN_FIELDS: Final = frozenset({"time", "level", "logger", "message", "request_id", "exception"})


def _extra_fields(record: logging.LogRecord) -> dict[str, object]:
    return {key: value for key, value in vars(record).items() if key not in _STANDARD_FIELDS}


class JsonFormatter(logging.Formatter):
    """One line of JSON per record, so a log can be searched and followed by a tool."""

    def __init__(self, redactor: Redactor) -> None:
        super().__init__()
        self.redactor = redactor

    @override
    def format(self, record: logging.LogRecord) -> str:
        when = datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds")
        entry: dict[str, Any] = {
            "time": when.replace("+00:00", "Z"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": self.redactor.text(record.getMessage()),
        }
        if (current := request_id.get()) is not None:
            entry["request_id"] = current
        for key, value in _extra_fields(record).items():
            # What the caller added can't replace what the line has to say for itself.
            entry[f"extra_{key}" if key in _OWN_FIELDS else key] = self.redactor.data(value, key)
        if record.exc_info:
            entry["exception"] = self.redactor.text(self.formatException(record.exc_info))
        return json.dumps(entry, default=str, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    """For reading in a terminal while developing: ``time level logger [request] message``."""

    def __init__(self, redactor: Redactor) -> None:
        super().__init__()
        self.redactor = redactor

    @override
    def format(self, record: logging.LogRecord) -> str:
        when = datetime.fromtimestamp(record.created, UTC).strftime("%Y-%m-%d %H:%M:%S")
        # A line is a line: a client can't start another one with a newline in what it sent.
        message = self.redactor.text(record.getMessage()).replace("\r", "\\r").replace("\n", "\\n")
        line = f"{when} {record.levelname.lower():<7} {record.name} {message}"
        if (current := request_id.get()) is not None:
            line = f"{line} request_id={current}"
        if record.exc_info:
            line = f"{line}\n{self.redactor.text(self.formatException(record.exc_info))}"
        return line


# Marks the handler this module added, so configuring twice replaces it and leaves any other alone.
_HANDLER_MARK: Final = "_aresgate_handler"


def configure(
    settings: Settings, secrets: Iterable[str] = (), stream: TextIO | None = None
) -> logging.Handler:
    """Sends every log, including uvicorn's, through one formatter that redacts. ``secrets`` are
    values that must never appear, such as the app secret key."""
    redactor = Redactor(secrets)
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(
        JsonFormatter(redactor) if settings.log_format == "json" else TextFormatter(redactor)
    )
    setattr(handler, _HANDLER_MARK, True)

    root = logging.getLogger()
    for existing in [h for h in root.handlers if getattr(h, _HANDLER_MARK, False)]:
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())
    # uvicorn gave its loggers handlers of their own, with their own format.
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers.clear()
        logging.getLogger(name).propagate = True
    # Each request is logged by app/middleware.py, with its ID and without its query string.
    access = logging.getLogger("uvicorn.access")
    access.handlers.clear()
    access.propagate = False
    return handler
