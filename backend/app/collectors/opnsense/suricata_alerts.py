"""Suricata's alerts, as OPNsense's intrusion detection reports them, kept as events.

``POST /api/ids/service/query_alerts`` answers with the newest alerts first, as an object whose
``rows`` are Suricata's own EVE records, flattened a little: ``alert`` is the signature's text,
``alert_sid`` its number and ``alert_action`` what Suricata did (``allowed`` or ``blocked``). The
rest is the record as Suricata wrote it, including its time with the zone it was written in.
OPNsense leaves out Suricata's own severity and category, so an alert is as serious as what was
done about it."""

import base64
import re
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Final

from app.collectors import traffic
from app.collectors.base import Collector, CollectorFailed, Context, Outcome
from app.collectors.opnsense.api import PRODUCT, read
from app.events.event import NewEvent, Severity
from app.integrations import probes

QUERY_PATH = "/api/ids/service/query_alerts"
# How many of the newest alerts each read asks for. A home network gets a few an hour.
LIMIT = 500
SOURCE = "opnsense"
CONNECTION = "api"
# What makes an alert this alert, short of the order they come in.
_IDENTITY = (
    "timestamp",
    "flow_id",
    "alert_sid",
    "in_iface",
    "proto",
    "src_ip",
    "src_port",
    "dest_ip",
    "dest_port",
)
# What the record has that is the traffic itself, which stays on the firewall: the packet that
# set the alert off, and the stream around it. And where it sits in OPNsense's file, which means
# nothing once the file is rotated. Only the start of the packet is kept (see ``_packet_start``),
# when the settings say so.
_LEFT_OUT = frozenset(
    {"payload", "payload_printable", "packet", "packet_info", "stream", "filepos", "fileid"}
)
# How much of the packet's data is kept: the first bytes, and the first characters of its text.
PACKET_BYTES: Final = 128
PACKET_TEXT: Final = 400
# What a login or a key looks like in the data of a packet. A packet that has any is not kept.
_SECRET: Final = re.compile(
    r"(?i)(authorization|cookie|passw(or)?d|pwd|secret|token|api[_-]?key|bearer)\s*[:=]"
)


class SuricataAlerts(Collector):
    key = "opnsense-suricata-alerts"
    title = "Suricata alerts"
    summary = (
        "Reads the alerts of the firewall's intrusion detection every minute and keeps each as "
        "an event: the signature, the addresses and whether Suricata blocked it."
    )
    interval = timedelta(minutes=1)
    timeout = timedelta(minutes=1)
    integration = SOURCE
    connection = CONNECTION
    module = "suricata"

    async def collect(self, context: Context) -> Outcome:
        rows = await _rows(context)
        events = parse(rows, keep_packets=context.settings.keep_packets)
        if rows and not events:
            raise CollectorFailed("It answered, but the alerts aren't in a form AresGate reads.")
        return Outcome(items=await context.record(events))


async def _rows(context: Context) -> list[object]:
    answer = await read(context, QUERY_PATH, body={"rowCount": LIMIT, "current": 1})
    data = probes.as_object(answer)
    if data is None and probes.as_array(answer) == []:
        # What OPNsense says when it couldn't ask Suricata, as it can't if it isn't installed.
        raise CollectorFailed(
            "OPNsense answered with nothing, which it does when it can't ask the intrusion "
            "detection service. Check that Suricata is installed and the user may use it."
        )
    rows = probes.as_array(data.get("rows")) if data else None
    if rows is None:
        raise CollectorFailed(probes.unexpected(PRODUCT).message)
    return rows


def parse(rows: list[object], *, keep_packets: bool = False) -> list[NewEvent]:
    """The alerts that can be read as events, in the order given. A row that isn't an object or
    has no time with a zone is left out. With ``keep_packets`` the start of the packet that set
    each alert off is kept too."""
    occurrences = traffic.Occurrences()
    events: list[NewEvent] = []
    for row in rows:
        entry = probes.as_object(row)
        occurred_at = _moment(traffic.text(entry, "timestamp")) if entry else None
        if entry is None or occurred_at is None:
            continue
        facts = tuple(traffic.text(entry, key) for key in _IDENTITY)
        events.append(_event(entry, occurred_at, occurrences.identity(facts), keep_packets))
    return events


def _moment(stamp: str) -> datetime | None:
    """Suricata's time, such as ``2026-10-23T15:01:02.123456-0300``. One that doesn't say its zone
    is no use, because the firewall's own isn't known here."""
    try:
        parsed = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _packet_start(entry: Mapping[str, object]) -> dict[str, object]:
    """The first bytes of the packet that set an alert off (Suricata gives them in base64) and the
    start of its text, to show what was sent. Nothing of a packet that looks like it carries a login
    or a key, or that has no data."""
    printable = traffic.text(entry, "payload_printable")[:PACKET_TEXT]
    encoded = entry.get("payload")
    data = b""
    if isinstance(encoded, str) and encoded:
        try:
            data = base64.b64decode(encoded, validate=True)[:PACKET_BYTES]
        except ValueError:
            data = b""
    if _SECRET.search(printable) or _SECRET.search(data.decode("latin-1")):
        return {}
    kept: dict[str, object] = {}
    if data:
        kept["payload"] = base64.b64encode(data).decode("ascii")
    if printable:
        kept["payload_printable"] = printable
    return kept


def _event(
    entry: Mapping[str, object],
    occurred_at: datetime,
    identity: tuple[str | int, ...],
    keep_packets: bool,
) -> NewEvent:
    action = traffic.text(entry, "alert_action")
    signature = traffic.text(entry, "alert")
    protocol = traffic.text(entry, "proto").lower()
    source, destination = traffic.text(entry, "src_ip"), traffic.text(entry, "dest_ip")
    source_port, destination_port = (
        traffic.number(entry, "src_port"),
        traffic.number(entry, "dest_port"),
    )
    route = traffic.route(
        traffic.endpoint(source, source_port), traffic.endpoint(destination, destination_port)
    )
    detail = " ".join(part for part in (protocol, route) if part)
    return NewEvent(
        source=SOURCE,
        connection=CONNECTION,
        kind="alert",
        # Without Suricata's own severity, an alert it stopped is the lesser worry.
        severity=Severity.LOW if action == "blocked" else Severity.MEDIUM,
        occurred_at=occurred_at,
        identity=identity,
        summary=_summary(signature, action, detail),
        signature=signature or None,
        src_address=source or None,
        src_port=source_port,
        dst_address=destination or None,
        dst_port=destination_port,
        protocol=protocol or None,
        iface=traffic.text(entry, "in_iface") or None,
        raw={
            **{key: value for key, value in entry.items() if key not in _LEFT_OUT},
            **(_packet_start(entry) if keep_packets else {}),
        },
    )


def _summary(signature: str, action: str, detail: str) -> str:
    """One line for a list: ``ET SCAN Potential SSH Scan (allowed): tcp 198.51.100.7:51514 to
    192.0.2.10:22``."""
    head = signature or "Suricata alert"
    if action:
        head = f"{head} ({action})"
    return f"{head}: {detail}" if detail else head
