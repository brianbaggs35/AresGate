"""Searching the logs in words: the same small language as the incidents (``app/querylang.py``),
with the fields of an event.

``severity>=high source:opnsense -dst:10.0.0.0/8 port:22 since:1h "failed password"``

Plain text is looked for in what the event says and in the rule that fired. The record the
program gave is looked through with ``raw:``, which reads far more than the rest and so is the
slowest field; with a time (``since:1h``) it is quick.
"""

from ipaddress import IPv4Network, IPv6Network
from typing import Any, Final

from sqlalchemy import ColumnElement, Text, cast, or_, select
from sqlalchemy.dialects.postgresql import INET

from app.models import Event, IncidentSignal
from app.querylang import (
    Clause,
    Compiled,
    Context,
    Field,
    Language,
    Search,
    SearchError,
    Term,
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
    "parse",
]


def _within(column: Any, net: IPv4Network | IPv6Network) -> ColumnElement[bool]:
    if net.num_addresses == 1:
        return column == net.network_address
    return column.op("<<=")(cast(str(net), INET))


def _addresses(clause: Clause, *columns: Any) -> tuple[ColumnElement[bool], str]:
    """Events that have an address in any of these columns inside any of the ranges named."""
    networks = [network(value) for value in clause.values]
    found = or_(*(_within(column, net) for column in columns for net in networks))
    return found, shown_networks(networks)


def _address(clause: Clause, _context: Context) -> Compiled:
    found, shown = _addresses(clause, Event.src_address, Event.dst_address)
    return found, f"Address: {shown}"


def _src(clause: Clause, _context: Context) -> Compiled:
    found, shown = _addresses(clause, Event.src_address)
    return found, f"From: {shown}"


def _dst(clause: Clause, _context: Context) -> Compiled:
    found, shown = _addresses(clause, Event.dst_address)
    return found, f"To: {shown}"


def _port(clause: Clause, _context: Context) -> Compiled:
    ports = port_numbers(clause)
    return Event.dst_port.in_(ports), f"Port: {', '.join(str(port) for port in ports)}"


def _sport(clause: Clause, _context: Context) -> Compiled:
    ports = port_numbers(clause)
    return Event.src_port.in_(ports), f"Source port: {', '.join(str(port) for port in ports)}"


def _source(clause: Clause, _context: Context) -> Compiled:
    keys, names = integrations(clause)
    return Event.source.in_(keys), f"Source: {', '.join(names)}"


def _words_of(clause: Clause, name: str) -> list[str]:
    """The values of a field that is matched whole and in lower case, such as ``kind:alert``."""
    chosen: list[str] = []
    for value in clause.values:
        if len(value) > 32:
            raise SearchError(f'"{name}" takes at most 32 characters.')
        if value.casefold() not in chosen:
            chosen.append(value.casefold())
    return chosen


def _connection(clause: Clause, _context: Context) -> Compiled:
    chosen = _words_of(clause, "connection")
    return Event.connection.in_(chosen), f"Connection: {', '.join(chosen)}"


def _kind(clause: Clause, _context: Context) -> Compiled:
    chosen = _words_of(clause, "kind")
    return Event.kind.in_(chosen), f"Kind: {', '.join(chosen)}"


def _protocol(clause: Clause, _context: Context) -> Compiled:
    chosen = _words_of(clause, "protocol")
    return Event.protocol.in_(chosen), f"Protocol: {', '.join(chosen)}"


def _signature(clause: Clause, _context: Context) -> Compiled:
    value = word(clause, "signature")
    return Event.signature.icontains(value, autoescape=True), f"Signature: {value}"


def _raw(clause: Clause, _context: Context) -> Compiled:
    value = word(clause, "raw")
    found = cast(Event.raw, Text).icontains(value, autoescape=True)
    return found, f"Record contains: {value}"


def _incident(clause: Clause, _context: Context) -> Compiled:
    yes = yes_or_no(clause, "incident")
    found = select(IncidentSignal.id).where(IncidentSignal.event_id == Event.id).exists()
    return found if yes else ~found, f"In an incident: {'yes' if yes else 'no'}"


def _since(clause: Clause, context: Context) -> Compiled:
    when, shown = moment(only_one(clause, "since"), context)
    return Event.occurred_at >= when, f"Since: {shown}"


def _before(clause: Clause, context: Context) -> Compiled:
    when, shown = moment(only_one(clause, "before"), context)
    return Event.occurred_at < when, f"Before: {shown}"


def _text(clause: Clause, _context: Context) -> Compiled:
    value = word(clause, "text")
    found = or_(
        Event.summary.icontains(value, autoescape=True),
        Event.signature.icontains(value, autoescape=True),
    )
    return found, f"Contains: {value}"


FIELDS: Final = (
    Field("address", _address),
    Field("src", _src),
    Field("dst", _dst),
    Field("port", _port),
    Field("sport", _sport),
    Field("source", _source),
    Field("connection", _connection),
    Field("kind", _kind),
    Field("severity", severity(Event.severity), ordered=True),
    Field("protocol", _protocol),
    Field("signature", _signature),
    Field("raw", _raw),
    Field("incident", _incident),
    Field("since", _since),
    Field("before", _before),
)
# Other names for them that people reach for.
ALIASES: Final = {
    "ip": "address",
    "from": "src",
    "to": "dst",
    "dport": "port",
    "program": "source",
    "conn": "connection",
    "sev": "severity",
    "proto": "protocol",
    "sig": "signature",
}
LANGUAGE: Final = Language.of(FIELDS, ALIASES, _text)


def parse(text: str, context: Context) -> Search:
    """The search the text asks for, or a SearchError that says what is wrong with it."""
    return _parse(text, context, LANGUAGE)
