"""Searching incidents in words: the small language behind the search box.

``severity>=high source:wazuh -address:10.0.0.0/8 "port scan" since:6h``

A search is terms that all have to be true. A term is plain text (it is looked for in the title,
the subject and the strongest signal), an address or a range, or a ``field:value`` such as
``source:wazuh``. A ``-`` in front turns a term around, a comma gives choices
(``status:open,investigating``), quotes keep words together, and ``>=``, ``>``, ``<=`` and ``<``
compare the fields that are amounts (severity, confidence, signals).

Every term is checked and turned into a condition here, once, so a search that cannot be
understood is refused in words before the database is asked anything, and the database is only
ever asked for what the language can say: a few terms, each of a short word. Nothing a person
types is put into a query as anything but a value.
"""

import difflib
import operator
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, tzinfo
from ipaddress import IPv4Network, IPv6Network, ip_network
from typing import Any, Final

from sqlalchemy import ColumnElement, String, cast, exists, func, or_, select
from sqlalchemy.dialects.postgresql import INET

from app.events.event import Severity
from app.incidents import rules
from app.incidents.queries import NO_VERDICT
from app.integrations import registry
from app.models import INCIDENT_STATUSES, Device, DeviceAddress, Incident, IncidentSignal

# The most a search may take, which is far more than anyone types, so what is asked of the
# database stays small whatever is sent.
MAX_LENGTH: Final = 500
MAX_TERMS: Final = 12
MAX_CHOICES: Final = 8
MAX_WORD: Final = 100
# The earliest and latest year a date may name, which keeps a typo out of the arithmetic.
YEARS: Final = (2000, 2100)

_SEVERITIES: Final = {level.name.lower(): level for level in Severity}
_VERDICTS: Final = ("threat", "not_suspicious", "low_priority", NO_VERDICT)
_ACTIVITIES: Final = ("scan", "brute_force")
_YES: Final = ("yes", "true", "1")
_NO: Final = ("no", "false", "0")

Operator = Callable[[Any, Any], ColumnElement[bool]]
_OPERATORS: Final[Mapping[str, Operator]] = {
    ":": operator.eq,
    "=": operator.eq,
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
}
_EXACT: Final = (":", "=")
_COMPARING: Final = {">": "over ", ">=": "at least ", "<": "under ", "<=": "at most "}

# One term: an optional minus, an optional ``field:`` and then a value, in quotes or not.
_CLAUSE: Final = re.compile(
    r"""
    (?P<minus>-)?
    (?:(?P<field>[A-Za-z][A-Za-z_]*)(?P<op>>=|<=|[:=<>]))?
    (?:"(?P<quoted>[^"]*)"|(?P<bare>[^\s"]+))
    """,
    re.VERBOSE,
)
_DANGLING: Final = re.compile(r"^(?P<field>[A-Za-z][A-Za-z_]*)(?:>=|<=|[:=<>])$")
_DURATION: Final = re.compile(r"^(?P<amount>\d{1,4})(?P<unit>[mhdw])$", re.IGNORECASE)
_UNITS: Final = {"m": "minutes", "h": "hours", "d": "days", "w": "weeks"}


class SearchError(ValueError):
    """Why a search can't be understood, in words for whoever typed it."""


@dataclass(frozen=True)
class Context:
    """What the words ``today`` and a date without a zone mean: where the person is, and when."""

    zone: tzinfo
    now: datetime


@dataclass(frozen=True)
class Clause:
    """A term as it was typed, before its meaning is looked up."""

    field: str | None
    op: str
    values: tuple[str, ...]
    quoted: bool
    negated: bool
    start: int
    end: int


@dataclass(frozen=True)
class Term:
    """A term that was understood: what it says, where it was, and the condition it makes."""

    # The field it is about, or None for plain text.
    field: str | None
    negated: bool
    # What it was understood as, to show: ``Source: Wazuh``, ``Not address: 10.0.0.0/8``.
    label: str
    # Where it was in the text, so it can be taken out of it.
    start: int
    end: int
    # Already turned around if it was negated.
    condition: ColumnElement[bool]


@dataclass(frozen=True)
class Search:
    terms: tuple[Term, ...]

    def conditions(self) -> list[ColumnElement[bool]]:
        return [term.condition for term in self.terms]

    def names(self, field: str) -> bool:
        """Whether any term is about this field."""
        return any(term.field == field for term in self.terms)


Compiled = tuple[ColumnElement[bool], str]
Compiler = Callable[[Clause, Context], Compiled]


@dataclass(frozen=True)
class Field:
    name: str
    compile: Compiler
    # Whether it can be compared (``>=``) as well as matched.
    ordered: bool = False


def _words(items: Sequence[str]) -> str:
    """``a or b``, ``a, b or c``: two or more."""
    return f"{', '.join(items[:-1])} or {items[-1]}"


def _quote(text: str) -> str:
    return f'"{text}"'


def _only_one(clause: Clause, name: str) -> str:
    if len(clause.values) != 1:
        raise SearchError(f"{_quote(name + clause.op)} takes one value, not a list.")
    return clause.values[0]


def _choices(clause: Clause, allowed: Sequence[str], noun: str) -> list[str]:
    """The values, each one of those allowed, in the order they were typed and without repeats."""
    chosen: list[str] = []
    for value in clause.values:
        wanted = value.casefold().replace("-", "_")
        if wanted not in allowed:
            raise SearchError(f"{_quote(value)} isn't {noun}. Use {_words(allowed)}.")
        if wanted not in chosen:
            chosen.append(wanted)
    return chosen


def _network(text: str) -> IPv4Network | IPv6Network:
    try:
        return ip_network(text, strict=False)
    except ValueError:
        raise SearchError(
            f"{_quote(text)} isn't an address or a range of them, such as 203.0.113.0/24."
        ) from None


def _inside(network: IPv4Network | IPv6Network) -> ColumnElement[bool]:
    if network.num_addresses == 1:
        return Incident.addresses.contains([network.network_address])
    member = func.unnest(Incident.addresses).column_valued("member")
    return exists().where(member.op("<<=")(cast(str(network), INET)))


def _address(clause: Clause, _context: Context) -> Compiled:
    networks = [_network(value) for value in clause.values]
    shown = [
        str(network.network_address) if network.num_addresses == 1 else str(network)
        for network in networks
    ]
    return or_(*(_inside(network) for network in networks)), f"Address: {', '.join(shown)}"


def _integration(value: str) -> tuple[str, str]:
    """The key and the name of the integration that goes by this key or name."""
    wanted = value.casefold()
    for key, item in registry.INTEGRATIONS.items():
        if wanted in (key, item.name.casefold()):
            return key, item.name
    raise SearchError(f"No integration is called {_quote(value)}. Try {_words(_sources())}.")


def _sources() -> list[str]:
    return list(registry.INTEGRATIONS)


def _source(clause: Clause, _context: Context) -> Compiled:
    found = [_integration(value) for value in clause.values]
    keys = list(dict.fromkeys(key for key, _ in found))
    names = list(dict.fromkeys(name for _, name in found))
    return Incident.sources.overlap(keys), f"Source: {', '.join(names)}"


def _severity(clause: Clause, _context: Context) -> Compiled:
    names = list(_SEVERITIES)
    if clause.op in _EXACT:
        chosen = _choices(clause, names, "a severity")
        levels = [int(_SEVERITIES[name]) for name in chosen]
        return Incident.severity.in_(levels), f"Severity: {', '.join(chosen)}"
    _only_one(clause, "severity")
    (chosen,) = _choices(clause, names, "a severity")
    condition = _OPERATORS[clause.op](Incident.severity, int(_SEVERITIES[chosen]))
    return condition, f"Severity: {_COMPARING[clause.op]}{chosen}"


def _amount(column: Any, name: str, highest: int) -> Compiler:
    """A field of whole numbers from zero to ``highest``."""

    def compile_amount(clause: Clause, _context: Context) -> Compiled:
        value = _only_one(clause, name)
        if not value.isascii() or not value.isdigit() or int(value) > highest:
            raise SearchError(
                f"{_quote(name)} is a whole number from 0 to {highest}, not {_quote(value)}."
            )
        number = int(value)
        words = _COMPARING.get(clause.op, "")
        return _OPERATORS[clause.op](column, number), f"{name.capitalize()}: {words}{number}"

    return compile_amount


def _status(clause: Clause, _context: Context) -> Compiled:
    chosen = _choices(clause, INCIDENT_STATUSES, "a status")
    return Incident.status.in_(chosen), f"Status: {', '.join(chosen)}"


def _verdict(clause: Clause, _context: Context) -> Compiled:
    chosen = _choices(clause, _VERDICTS, "something you can say of an incident")
    # An incident with no verdict is none, which the column holds as nothing at all.
    said = func.coalesce(Incident.verdict, NO_VERDICT)
    shown = [name.replace("_", " ") for name in chosen]
    return said.in_(chosen), f"Verdict: {', '.join(shown)}"


def _activity(clause: Clause, _context: Context) -> Compiled:
    chosen = _choices(clause, _ACTIVITIES, "a kind of activity")
    shown = [name.replace("_", " ") for name in chosen]
    return Incident.activities.overlap(chosen), f"Activity: {', '.join(shown)}"


def _word(clause: Clause, name: str) -> str:
    value = _only_one(clause, name)
    if len(value) > MAX_WORD:
        raise SearchError(f"{_quote(name)} takes at most {MAX_WORD} characters.")
    return value


def _signature(clause: Clause, _context: Context) -> Compiled:
    value = _word(clause, "signature")
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
    value = _word(clause, "device")
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
    ports: list[int] = []
    for value in clause.values:
        if not value.isascii() or not value.isdigit() or not 1 <= int(value) <= 65535:
            raise SearchError(f"{_quote(value)} isn't a port, which is a number from 1 to 65535.")
        if int(value) not in ports:
            ports.append(int(value))
    return Incident.ports.overlap(ports), f"Port: {', '.join(str(port) for port in ports)}"


def _banned(clause: Clause, _context: Context) -> Compiled:
    value = _only_one(clause, "banned").casefold()
    if value not in (*_YES, *_NO):
        raise SearchError(f"{_quote(value)} isn't yes or no.")
    yes = value in _YES
    return Incident.banned.is_(yes), f"Banned: {'yes' if yes else 'no'}"


def moment(value: str, context: Context) -> tuple[datetime, str]:
    """When a time, such as ``6h``, ``today`` or ``2026-10-27 08:00``, is, and how to say it."""
    found = _DURATION.match(value)
    if found:
        unit = _UNITS[found["unit"].lower()]
        return context.now - timedelta(**{unit: int(found["amount"])}), f"{value.lower()} ago"
    lowered = value.casefold()
    if lowered in ("today", "yesterday"):
        local = context.now.astimezone(context.zone)
        if lowered == "yesterday":
            local -= timedelta(days=1)
        midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
        return midnight.astimezone(UTC), lowered
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise SearchError(
            f"{_quote(value)} isn't a time. Try 6h, 2d, today, yesterday or 2026-10-27."
        ) from None
    if not YEARS[0] <= parsed.year <= YEARS[1]:
        raise SearchError(f"{_quote(value)} isn't a year from {YEARS[0]} to {YEARS[1]}.")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=context.zone)
    shown = parsed.astimezone(context.zone).strftime("%Y-%m-%d %H:%M")
    return parsed.astimezone(UTC), shown


def _since(clause: Clause, context: Context) -> Compiled:
    when, shown = moment(_only_one(clause, "since"), context)
    return Incident.last_seen_at >= when, f"Going on since: {shown}"


def _before(clause: Clause, context: Context) -> Compiled:
    when, shown = moment(_only_one(clause, "before"), context)
    return Incident.first_seen_at < when, f"Began before: {shown}"


def _text(clause: Clause, _context: Context) -> Compiled:
    value = _word(clause, "text")
    found = or_(
        Incident.title.icontains(value, autoescape=True),
        Incident.subject.icontains(value, autoescape=True),
        Incident.top_summary.icontains(value, autoescape=True),
    )
    return found, f"Contains: {value}"


def _fields() -> dict[str, Field]:
    return {
        field.name: field
        for field in (
            Field("address", _address),
            Field("source", _source),
            Field("severity", _severity, ordered=True),
            Field(
                "confidence", _amount(Incident.confidence, "confidence", rules.MAX_CONFIDENCE), True
            ),
            Field("signals", _amount(Incident.signal_count, "signals", 1_000_000), ordered=True),
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
    }


FIELDS: Final = _fields()
# Other names for them that people reach for.
ALIASES: Final = {
    "ip": "address",
    "src": "address",
    "program": "source",
    "sev": "severity",
    "conf": "confidence",
    "sig": "signature",
}


def _scan(text: str) -> list[Clause]:
    """The terms in the text, as they were typed."""
    clauses: list[Clause] = []
    position = 0
    while True:
        while position < len(text) and text[position].isspace():
            position += 1
        if position == len(text):
            return clauses
        found = _CLAUSE.match(text, position)
        if found is None or (found.end() < len(text) and not text[found.end()].isspace()):
            where = text.find('"', position) + 1
            raise SearchError(
                f"The quote at character {where} needs a space before it or a quote to close it."
            )
        clauses.append(_clause(found))
        position = found.end()


def _clause(found: re.Match[str]) -> Clause:
    """One term from what the pattern found."""
    negated = found["minus"] is not None
    quoted = found["quoted"] is not None
    start = found.start()
    # Where the word itself begins, after the minus.
    word = found.start() + int(negated)
    body = found.string[word : found.end()]
    if quoted:
        # Quotes keep a value together whole: no commas to split it at.
        field = found["field"].casefold() if found["field"] else None
        op = found["op"] or ":"
        return Clause(field, op, (found["quoted"],), True, negated, start, found.end())
    if not body or body == "-":
        raise SearchError("A minus sign turns a term around, so it needs one after it.")
    # An address is whole whatever it holds: fe80::1 is not the field fe.
    if _is_network(body):
        return Clause("address", ":", (body,), False, negated, start, found.end())
    if found["field"] is None:
        dangling = _DANGLING.match(body)
        if dangling:
            raise SearchError(
                f"{_quote(body)} needs a value right after it, such as {dangling['field']}:value. "
                "To look for the text itself, put it in quotes."
            )
        return Clause(None, ":", (body,), False, negated, start, found.end())
    values = tuple(value for value in found["bare"].split(",") if value)
    if not values:
        raise SearchError(f"{_quote(found['field'] + found['op'])} needs a value after it.")
    return Clause(
        found["field"].casefold(), found["op"], values, False, negated, start, found.end()
    )


def _is_network(text: str) -> bool:
    try:
        ip_network(text, strict=False)
    except ValueError:
        return False
    return True


def _field_of(clause: Clause) -> Field | None:
    """The field a term is about: None for text, and an error for one nobody knows."""
    if clause.field is None:
        return None
    name = ALIASES.get(clause.field, clause.field)
    field = FIELDS.get(name)
    if field is None:
        known = [*FIELDS, *ALIASES]
        near = difflib.get_close_matches(clause.field, known, n=1)
        hint = f" Did you mean {_quote(ALIASES.get(near[0], near[0]))}?" if near else ""
        raise SearchError(
            f"There's no search field called {_quote(clause.field)}.{hint} "
            "To look for the text itself, put it in quotes."
        )
    return field


def _understand(clause: Clause, context: Context) -> Term:
    field = _field_of(clause)
    if field is None:
        found, label = _text(clause, context)
    else:
        if clause.op not in _EXACT and not field.ordered:
            raise SearchError(
                f"{_quote(field.name)} is matched with {_quote(field.name + ':')}, "
                f"not {_quote(clause.op)}."
            )
        if len(clause.values) > MAX_CHOICES:
            raise SearchError(f"{_quote(field.name)} takes at most {MAX_CHOICES} choices.")
        found, label = field.compile(clause, context)
    if clause.negated:
        found = ~found
        label = f"Not {label[0].lower()}{label[1:]}"
    return Term(
        field.name if field else None, clause.negated, label, clause.start, clause.end, found
    )


def parse(text: str, context: Context) -> Search:
    """The search the text asks for, or a SearchError that says what is wrong with it."""
    if len(text) > MAX_LENGTH:
        raise SearchError(f"A search can be at most {MAX_LENGTH} characters.")
    if any(not (char.isprintable() or char.isspace()) for char in text):
        raise SearchError("A search can't hold control characters.")
    clauses = _scan(text)
    if len(clauses) > MAX_TERMS:
        raise SearchError(f"A search can have at most {MAX_TERMS} terms.")
    return Search(tuple(_understand(clause, context) for clause in clauses))
