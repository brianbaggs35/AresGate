"""The firewall log: what OPNsense's packet filter did with the traffic it was asked to log,
kept as events.

``GET /api/diagnostics/firewall/log`` answers with the newest lines first, each a JSON object of
strings: the time (``__timestamp__``), the interface, the action (``pass``, ``block``...), the
direction, the protocol, the addresses and ports and, if the rule has one, its description
(``label``). Reading the newest lines every half a minute covers a firewall that logs about 33
lines a second; the events' fingerprints keep a line from being stored twice by the overlap."""

from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from app.collectors.base import Collector, CollectorFailed, Context, Outcome
from app.collectors.opnsense import clock
from app.collectors.opnsense.api import PRODUCT, read
from app.events.event import NewEvent, Severity
from app.integrations import probes

LOG_PATH = "/api/diagnostics/firewall/log"
# How many of the newest lines each read asks for. OPNsense's own default.
LIMIT = 1000
SOURCE = "opnsense"
CONNECTION = "api"
# What makes a line this line, short of the order they come in: lines that agree on all of these
# are told apart by how many came before them.
_IDENTITY = (
    "__timestamp__",
    "interface",
    "action",
    "dir",
    "protoname",
    "protonum",
    "src",
    "srcport",
    "dst",
    "dstport",
    "rid",
    "rulenr",
)


class FirewallLog(Collector):
    key = "opnsense-firewall-log"
    title = "Firewall log"
    summary = (
        "Reads the firewall's log every half a minute and keeps each line as an event: what was "
        "done with it, which way, and between which addresses."
    )
    interval = timedelta(seconds=30)
    # Two requests, each with a deadline of its own.
    timeout = timedelta(minutes=1)
    integration = SOURCE
    connection = CONNECTION
    module = "firewall"

    async def collect(self, context: Context) -> Outcome:
        offset = await clock.utc_offset(context)
        lines = probes.as_array(await read(context, LOG_PATH, {"limit": str(LIMIT)}))
        if lines is None:
            raise CollectorFailed(probes.unexpected(PRODUCT).message)
        events = parse(lines, offset, context.now)
        if lines and not events:
            raise CollectorFailed(
                "It answered, but the lines of its log aren't in a form AresGate reads."
            )
        return Outcome(items=await context.record(events))


def parse(lines: list[object], offset: timedelta, now: datetime) -> list[NewEvent]:
    """The lines that can be read as events, in the order given. A line that isn't an object or
    has no readable time is left out."""
    seen: Counter[tuple[str, ...]] = Counter()
    events: list[NewEvent] = []
    for line in lines:
        entry = probes.as_object(line)
        occurred_at = _moment(_text(entry, "__timestamp__"), offset, now) if entry else None
        if entry is None or occurred_at is None:
            continue
        facts = tuple(_text(entry, key) for key in _IDENTITY)
        # Lines identical down to the second are as many events as there are lines. Counting
        # from the newest, the first of them is the same whichever window it is read in.
        events.append(_event(entry, occurred_at, (*facts, seen[facts])))
        seen[facts] += 1
    return events


def _text(entry: Mapping[str, object], key: str) -> str:
    value = entry.get(key)
    return str(value) if isinstance(value, str | int) else ""


def _number(entry: Mapping[str, object], key: str) -> int | None:
    text = _text(entry, key)
    return int(text) if text.isascii() and text.isdigit() else None


def _moment(stamp: str, offset: timedelta, now: datetime) -> datetime | None:
    """When a line was written, from its time: ``2026-10-23T15:01:02`` in the newer format, with
    or without a zone, and ``Oct 23 15:01:02`` in the older, which has no year."""
    try:
        parsed = datetime.fromisoformat(stamp)
    except ValueError:
        parsed = _without_year(stamp, now + offset)
    if parsed is None:
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(UTC)
    return (parsed - offset).replace(tzinfo=UTC)


def _without_year(stamp: str, local_now: datetime) -> datetime | None:
    """The line's time in the year that puts it in the past: this year's, or else last year's
    (a line from December, read in January)."""
    for year in (local_now.year, local_now.year - 1):
        try:
            parsed = datetime.strptime(f"{year} {stamp}", "%Y %b %d %H:%M:%S")
        except ValueError:
            continue
        if parsed <= local_now.replace(tzinfo=None) + timedelta(days=1):
            return parsed
    return None


def _event(
    entry: Mapping[str, object], occurred_at: datetime, identity: tuple[Any, ...]
) -> NewEvent:
    action = _text(entry, "action")
    protocol = (_text(entry, "protoname") or _text(entry, "protonum")).lower()
    source = _text(entry, "src")
    destination = _text(entry, "dst")
    return NewEvent(
        source=SOURCE,
        connection=CONNECTION,
        kind="firewall",
        # The firewall's blocks are the ones worth a second look; a pass is just traffic.
        severity=Severity.LOW if action == "block" else Severity.INFO,
        occurred_at=occurred_at,
        identity=identity,
        summary=_summary(entry, action, protocol),
        signature=_text(entry, "label") or None,
        src_address=source or None,
        src_port=_number(entry, "srcport"),
        dst_address=destination or None,
        dst_port=_number(entry, "dstport"),
        protocol=protocol or None,
        raw={key: value for key, value in entry.items() if key != "__spec__"},
    )


def _summary(entry: Mapping[str, object], action: str, protocol: str) -> str:
    """One line for a list: ``block in on igb0: tcp 198.51.100.7:51514 to 192.0.2.10:443``."""
    interface = _text(entry, "interface")
    where = f"{_text(entry, 'dir')} on {interface}" if interface else _text(entry, "dir")
    route = _route(_endpoint(entry, "src", "srcport"), _endpoint(entry, "dst", "dstport"))
    head = f"{action or 'logged'} {where}".strip()
    detail = " ".join(part for part in (protocol, route) if part)
    label = _text(entry, "label")
    return (f"{head}: {detail}" if detail else head) + (f" ({label})" if label else "")


def _route(source: str, destination: str) -> str:
    if source and destination:
        return f"{source} to {destination}"
    return f"to {destination}" if destination else source


def _endpoint(entry: Mapping[str, object], address: str, port: str) -> str:
    host, number = _text(entry, address), _number(entry, port)
    if not host:
        return ""
    if number is None:
        return host
    return f"[{host}]:{number}" if ":" in host else f"{host}:{number}"
