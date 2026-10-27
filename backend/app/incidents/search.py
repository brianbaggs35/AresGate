"""Searching incidents in words: the small language behind the search box.

``severity>=high source:wazuh -address:10.0.0.0/8 "port scan" since:6h``

Plain text is looked for in the title, the subject and the strongest signal; the fields are the
ones below. How a term is read is the language in ``app/querylang.py``, which the logs share.
"""

from ipaddress import IPv4Network, IPv6Network
from typing import Final

from sqlalchemy import ColumnElement, String, cast, exists, func, or_, select
from sqlalchemy.dialects.postgresql import INET

from app.incidents import rules
from app.incidents.queries import NO_VERDICT
from app.models import INCIDENT_STATUSES, Device, DeviceAddress, Incident, IncidentSignal
from app.querylang import (
    Clause,
    Compiled,
    Context,
    Field,
    Language,
    Search,
    SearchError,
    Term,
    amount,
    choices,
    integrations,
    moment,
    network,
    only_one,
    port_numbers,
    severity,
    shown_networks,
    word,
    yes_or_no,
)
from app.querylang import parse as _parse

__all__ = [
    "ALIASES",
    "FIELDS",
    "LANGUAGE",
    "Clause",
    "Context",
    "Search",
    "SearchError",
    "Term",
    "moment",
    "parse",
]

_VERDICTS: Final = ("threat", "not_suspicious", "low_priority", NO_VERDICT)
_ACTIVITIES: Final = ("scan", "brute_force")


def _inside(net: IPv4Network | IPv6Network) -> ColumnElement[bool]:
    if net.num_addresses == 1:
        return Incident.addresses.contains([net.network_address])
    member = func.unnest(Incident.addresses).column_valued("member")
    return exists().where(member.op("<<=")(cast(str(net), INET)))


def _address(clause: Clause, _context: Context) -> Compiled:
    networks = [network(value) for value in clause.values]
    found = or_(*(_inside(net) for net in networks))
    return found, f"Address: {shown_networks(networks)}"


def _source(clause: Clause, _context: Context) -> Compiled:
    keys, names = integrations(clause)
    return Incident.sources.overlap(keys), f"Source: {', '.join(names)}"


def _status(clause: Clause, _context: Context) -> Compiled:
    chosen = choices(clause, INCIDENT_STATUSES, "a status")
    return Incident.status.in_(chosen), f"Status: {', '.join(chosen)}"


def _verdict(clause: Clause, _context: Context) -> Compiled:
    chosen = choices(clause, _VERDICTS, "something you can say of an incident")
    # An incident with no verdict is none, which the column holds as nothing at all.
    said = func.coalesce(Incident.verdict, NO_VERDICT)
    shown = [name.replace("_", " ") for name in chosen]
    return said.in_(chosen), f"Verdict: {', '.join(shown)}"


def _activity(clause: Clause, _context: Context) -> Compiled:
    chosen = choices(clause, _ACTIVITIES, "a kind of activity")
    shown = [name.replace("_", " ") for name in chosen]
    return Incident.activities.overlap(chosen), f"Activity: {', '.join(shown)}"


def _signature(clause: Clause, _context: Context) -> Compiled:
    value = word(clause, "signature")
    signal = (
        select(IncidentSignal.id)
        .where(
            IncidentSignal.incident_id == Incident.id,
            IncidentSignal.signature.icontains(value, autoescape=True),
        )
        .exists()
    )
    return signal, f"Signature: {value}"


def _device(clause: Clause, _context: Context) -> Compiled:
    value = word(clause, "device")
    found = (
        select(Device.id)
        .join(DeviceAddress, DeviceAddress.device_id == Device.id)
        .where(
            DeviceAddress.address == func.any(Incident.addresses),
            or_(
                Device.hostname.icontains(value, autoescape=True),
                Device.vendor.icontains(value, autoescape=True),
                cast(Device.mac, String).icontains(value, autoescape=True),
            ),
        )
        .exists()
    )
    return found, f"Device: {value}"


def _port(clause: Clause, _context: Context) -> Compiled:
    ports = port_numbers(clause)
    return Incident.ports.overlap(ports), f"Port: {', '.join(str(port) for port in ports)}"


def _banned(clause: Clause, _context: Context) -> Compiled:
    yes = yes_or_no(clause, "banned")
    return Incident.banned.is_(yes), f"Banned: {'yes' if yes else 'no'}"


def _since(clause: Clause, context: Context) -> Compiled:
    when, shown = moment(only_one(clause, "since"), context)
    return Incident.last_seen_at >= when, f"Going on since: {shown}"


def _before(clause: Clause, context: Context) -> Compiled:
    when, shown = moment(only_one(clause, "before"), context)
    return Incident.first_seen_at < when, f"Began before: {shown}"


def _text(clause: Clause, _context: Context) -> Compiled:
    value = word(clause, "text")
    found = or_(
        Incident.title.icontains(value, autoescape=True),
        Incident.subject.icontains(value, autoescape=True),
        Incident.top_summary.icontains(value, autoescape=True),
    )
    return found, f"Contains: {value}"


FIELDS: Final = (
    Field("address", _address),
    Field("source", _source),
    Field("severity", severity(Incident.severity), ordered=True),
    Field("confidence", amount(Incident.confidence, "confidence", rules.MAX_CONFIDENCE), True),
    Field("signals", amount(Incident.signal_count, "signals", 1_000_000), ordered=True),
    Field("status", _status),
    Field("verdict", _verdict),
    Field("activity", _activity),
    Field("signature", _signature),
    Field("device", _device),
    Field("port", _port),
    Field("banned", _banned),
    Field("since", _since),
    Field("before", _before),
)
# Other names for them that people reach for.
ALIASES: Final = {
    "ip": "address",
    "src": "address",
    "program": "source",
    "sev": "severity",
    "conf": "confidence",
    "sig": "signature",
}
LANGUAGE: Final = Language.of(FIELDS, ALIASES, _text)


def parse(text: str, context: Context) -> Search:
    """The search the text asks for, or a SearchError that says what is wrong with it."""
    return _parse(text, context, LANGUAGE)
