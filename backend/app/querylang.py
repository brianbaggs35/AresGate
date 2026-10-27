"""The small language behind the search boxes: what is typed, and the conditions it makes.

``severity>=high source:wazuh -address:10.0.0.0/8 "port scan" since:6h``

A search is terms that all have to be true. A term is plain text, an address or a range, or a
``field:value`` such as ``source:wazuh``. A ``-`` in front turns a term around, a comma gives
choices (``status:open,investigating``), quotes keep words together, and ``>=``, ``>``, ``<=`` and
``<`` compare the fields that are amounts (severity, confidence, signals).

What the fields are, and what they are fields of, is decided by a ``Language``: the incidents
have one (``app/incidents/search.py``) and so do the logs (``app/events/search.py``). Everything
else is shared, so both read the same words the same way and tell the person who typed them the
same things when they are wrong.

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

from sqlalchemy import ColumnElement, false, func

from app.events.event import Severity
from app.integrations import registry

# The most a search may take, which is far more than anyone types, so what is asked of the
# database stays small whatever is sent.
MAX_LENGTH: Final = 500
MAX_TERMS: Final = 12
MAX_CHOICES: Final = 8
MAX_WORD: Final = 100
# The earliest and latest year a date may name, which keeps a typo out of the arithmetic.
YEARS: Final = (2000, 2100)

SEVERITIES: Final = {level.name.lower(): level for level in Severity}
YES: Final = ("yes", "true", "1")
NO: Final = ("no", "false", "0")

Operator = Callable[[Any, Any], ColumnElement[bool]]
OPERATORS: Final[Mapping[str, Operator]] = {
    ":": operator.eq,
    "=": operator.eq,
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
}
EXACT: Final = (":", "=")
COMPARING: Final = {">": "over ", ">=": "at least ", "<": "under ", "<=": "at most "}

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


@dataclass(frozen=True)
class Language:
    """What can be searched for: the fields, other names for them that people reach for, and what
    plain text is looked for in."""

    fields: Mapping[str, Field]
    aliases: Mapping[str, str]
    text: Compiler

    @classmethod
    def of(cls, fields: Sequence[Field], aliases: Mapping[str, str], text: Compiler) -> Language:
        return cls({field.name: field for field in fields}, aliases, text)


def words(items: Sequence[str]) -> str:
    """``a or b``, ``a, b or c``: two or more."""
    return f"{', '.join(items[:-1])} or {items[-1]}"


def quote(text: str) -> str:
    return f'"{text}"'


def only_one(clause: Clause, name: str) -> str:
    if len(clause.values) != 1:
        raise SearchError(f"{quote(name + clause.op)} takes one value, not a list.")
    return clause.values[0]


def choices(clause: Clause, allowed: Sequence[str], noun: str) -> list[str]:
    """The values, each one of those allowed, in the order they were typed and without repeats."""
    chosen: list[str] = []
    for value in clause.values:
        wanted = value.casefold().replace("-", "_")
        if wanted not in allowed:
            raise SearchError(f"{quote(value)} isn't {noun}. Use {words(allowed)}.")
        if wanted not in chosen:
            chosen.append(wanted)
    return chosen


def network(text: str) -> IPv4Network | IPv6Network:
    try:
        return ip_network(text, strict=False)
    except ValueError:
        raise SearchError(
            f"{quote(text)} isn't an address or a range of them, such as 203.0.113.0/24."
        ) from None


def shown_networks(networks: Sequence[IPv4Network | IPv6Network]) -> str:
    """The addresses and ranges as they are said: an address of one needs no ``/32``."""
    return ", ".join(
        str(one.network_address) if one.num_addresses == 1 else str(one) for one in networks
    )


def sources() -> list[str]:
    """The keys of the integrations that can report something."""
    return list(registry.INTEGRATIONS)


def integration(value: str) -> tuple[str, str]:
    """The key and the name of the integration that goes by this key or name."""
    wanted = value.casefold()
    for key, item in registry.INTEGRATIONS.items():
        if wanted in (key, item.name.casefold()):
            return key, item.name
    raise SearchError(f"No integration is called {quote(value)}. Try {words(sources())}.")


def integrations(clause: Clause) -> tuple[list[str], list[str]]:
    """The keys and the names of the integrations a ``source:`` term names, without repeats."""
    found = [integration(value) for value in clause.values]
    keys = list(dict.fromkeys(key for key, _ in found))
    names = list(dict.fromkeys(name for _, name in found))
    return keys, names


def severity(column: Any) -> Compiler:
    """A field of severities, which can be matched (``severity:high,critical``) or compared
    (``severity>=high``)."""

    def compile_severity(clause: Clause, _context: Context) -> Compiled:
        names = list(SEVERITIES)
        if clause.op in EXACT:
            chosen = choices(clause, names, "a severity")
            levels = [int(SEVERITIES[name]) for name in chosen]
            return column.in_(levels), f"Severity: {', '.join(chosen)}"
        only_one(clause, "severity")
        (chosen,) = choices(clause, names, "a severity")
        condition = OPERATORS[clause.op](column, int(SEVERITIES[chosen]))
        return condition, f"Severity: {COMPARING[clause.op]}{chosen}"

    return compile_severity


def amount(column: Any, name: str, highest: int) -> Compiler:
    """A field of whole numbers from zero to ``highest``."""

    def compile_amount(clause: Clause, _context: Context) -> Compiled:
        value = only_one(clause, name)
        if not value.isascii() or not value.isdigit() or int(value) > highest:
            raise SearchError(
                f"{quote(name)} is a whole number from 0 to {highest}, not {quote(value)}."
            )
        number = int(value)
        said = COMPARING.get(clause.op, "")
        return OPERATORS[clause.op](column, number), f"{name.capitalize()}: {said}{number}"

    return compile_amount


def word(clause: Clause, name: str) -> str:
    """The one short value of a field that looks for words."""
    value = only_one(clause, name)
    if len(value) > MAX_WORD:
        raise SearchError(f"{quote(name)} takes at most {MAX_WORD} characters.")
    return value


def port_numbers(clause: Clause) -> list[int]:
    """The ports a term names, in the order they were typed and without repeats."""
    ports: list[int] = []
    for value in clause.values:
        if not value.isascii() or not value.isdigit() or not 1 <= int(value) <= 65535:
            raise SearchError(f"{quote(value)} isn't a port, which is a number from 1 to 65535.")
        if int(value) not in ports:
            ports.append(int(value))
    return ports


def yes_or_no(clause: Clause, name: str) -> bool:
    value = only_one(clause, name).casefold()
    if value not in (*YES, *NO):
        raise SearchError(f"{quote(value)} isn't yes or no.")
    return value in YES


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
            f"{quote(value)} isn't a time. Try 6h, 2d, today, yesterday or 2026-10-27."
        ) from None
    if not YEARS[0] <= parsed.year <= YEARS[1]:
        raise SearchError(f"{quote(value)} isn't a year from {YEARS[0]} to {YEARS[1]}.")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=context.zone)
    shown = parsed.astimezone(context.zone).strftime("%Y-%m-%d %H:%M")
    return parsed.astimezone(UTC), shown


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
    begins = found.start() + int(negated)
    body = found.string[begins : found.end()]
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
                f"{quote(body)} needs a value right after it, such as {dangling['field']}:value. "
                "To look for the text itself, put it in quotes."
            )
        return Clause(None, ":", (body,), False, negated, start, found.end())
    values = tuple(value for value in found["bare"].split(",") if value)
    if not values:
        raise SearchError(f"{quote(found['field'] + found['op'])} needs a value after it.")
    return Clause(
        found["field"].casefold(), found["op"], values, False, negated, start, found.end()
    )


def _is_network(text: str) -> bool:
    try:
        ip_network(text, strict=False)
    except ValueError:
        return False
    return True


def _field_of(clause: Clause, language: Language) -> Field | None:
    """The field a term is about: None for text, and an error for one nobody knows."""
    if clause.field is None:
        return None
    name = language.aliases.get(clause.field, clause.field)
    field = language.fields.get(name)
    if field is None:
        known = [*language.fields, *language.aliases]
        near = difflib.get_close_matches(clause.field, known, n=1)
        hint = f" Did you mean {quote(language.aliases.get(near[0], near[0]))}?" if near else ""
        raise SearchError(
            f"There's no search field called {quote(clause.field)}.{hint} "
            "To look for the text itself, put it in quotes."
        )
    return field


def _understand(clause: Clause, context: Context, language: Language) -> Term:
    field = _field_of(clause, language)
    if field is None:
        found, label = language.text(clause, context)
    else:
        if clause.op not in EXACT and not field.ordered:
            raise SearchError(
                f"{quote(field.name)} is matched with {quote(field.name + ':')}, "
                f"not {quote(clause.op)}."
            )
        if len(clause.values) > MAX_CHOICES:
            raise SearchError(f"{quote(field.name)} takes at most {MAX_CHOICES} choices.")
        found, label = field.compile(clause, context)
    if clause.negated:
        # Turned around, a term is true of what it was not true of, which is also what it said
        # nothing about: an event with no address is not one that names 10.0.0.1.
        found = ~func.coalesce(found, false())
        label = f"Not {label[0].lower()}{label[1:]}"
    return Term(
        field.name if field else None, clause.negated, label, clause.start, clause.end, found
    )


def parse(text: str, context: Context, language: Language) -> Search:
    """The search the text asks for, or a SearchError that says what is wrong with it."""
    if len(text) > MAX_LENGTH:
        raise SearchError(f"A search can be at most {MAX_LENGTH} characters.")
    if any(not (char.isprintable() or char.isspace()) for char in text):
        raise SearchError("A search can't hold control characters.")
    clauses = _scan(text)
    if len(clauses) > MAX_TERMS:
        raise SearchError(f"A search can have at most {MAX_TERMS} terms.")
    return Search(tuple(_understand(clause, context, language) for clause in clauses))
