"""What the programs reported about an alert besides who, where and when.

Every program says more than the few facts an event keeps as columns: Suricata knows the
signature's number and what it was about (the host asked for, the application), Wazuh the rule's
groups and the MITRE ATT&CK technique, the machine and the log line, ntopng how bad it scored the
flow and what traffic it was. The event keeps that whole record (``Event.raw``), but only for as
long as events are kept and in the program's own words. An incident keeps what is worth showing,
boiled down to one shape for all of them, with each signal (``IncidentSignal.evidence``), so the
page can show what each program added in the same way and an incident that is weeks old still can.

Every program's record is read as it comes and with care: it is somebody else's data, any member
may be missing or of another type, and what is kept is cut down to a size (``LIMITS``).

Read from the documentation of each program. Wazuh: the alerts' fields (``rule.id``, ``level``,
``groups``, ``firedtimes``, ``mitre``, the compliance lists, ``agent``, ``manager``, ``decoder``,
``location``, ``full_log``, ``GeoLocation`` and ``data``; Ruleset and the alerts index template).
Suricata: its EVE JSON (``alert``, ``app_proto``, ``http``, ``dns``, ``tls`` and ``flow``), which
OPNsense returns flattened a little (see ``app/collectors/opnsense/suricata_alerts.py``), so each
member is looked for as a nested object, as a member named with underscores and as one named with
dots. ntopng: the members of its alert lists that its source names (``score``, ``alert_id``,
``l7_proto``, ``cli_name``, ``srv_name`` and the role flags); not tried against a live ntopng.
CrowdSec: the members of a decision. What a version of a program leaves out is simply not shown.
"""

from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Final, NotRequired, TypedDict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import clean
from app.integrations import probes
from app.models import Event, IncidentSignal

# How much of each kind of thing is kept, and how long each is.
MAX_FACTS: Final = 16
MAX_TAGS: Final = 12
MAX_MITRE: Final = 6
MAX_INDICATORS: Final = 10
MAX_VALUE: Final = 200
MAX_EXCERPT: Final = 400
# How many signals are read in a run of the engine.
BATCH: Final = 200


class Mitre(TypedDict):
    """A technique of the MITRE ATT&CK framework a program matched the alert to."""

    id: str
    tactic: str
    technique: str


class Indicator(TypedDict):
    """Something an alert names that can be looked up or told apart: a host name, an address
    that was asked for, a user. ``kind`` is a short word (``hostname``, ``url``, ``dns``,
    ``sni``, ``user_agent``, ``user``, ``file``, ``country``)."""

    kind: str
    value: str


class Traffic(TypedDict, total=False):
    """How much the flow the alert is about carried, from the client's side."""

    packets_out: int
    packets_in: int
    bytes_out: int
    bytes_in: int


class Evidence(TypedDict):
    """What is worth showing of what one program reported of one alert. Every member is there
    only when the program said something for it."""

    # What it said, as [label, value] pairs: the rule's number, what was done, the score.
    facts: list[list[str]]
    # Words that sort the alert, such as the groups of a Wazuh rule or an alert's category.
    tags: list[str]
    mitre: list[Mitre]
    indicators: list[Indicator]
    traffic: NotRequired[Traffic]
    # The machine it is about, such as ``web1 (192.168.1.20)``, and the application it was, such as
    # ``http`` or ``ssh``.
    host: NotRequired[str]
    app: NotRequired[str]
    # The log line it came from, where a program gives one, cut down.
    excerpt: NotRequired[str]


Raw = Mapping[str, object]


def _text(value: object, limit: int = MAX_VALUE) -> str:
    """A value as text, made safe to keep: what a program gives as a string or a number, with
    control characters taken out and cut to fit, or nothing for anything else."""
    if isinstance(value, bool) or not isinstance(value, str | int | float):
        return ""
    return clean(str(value), limit) or ""


def _pick(raw: Raw, *paths: str) -> object:
    """A member by its path, such as ``http.hostname``, however the program wrote it: nested, in
    a member named with underscores (``http_hostname``) or named with the dot itself."""
    for path in paths:
        parts = path.split(".")
        node: object = raw
        for part in parts:
            members = probes.as_object(node)
            node = members.get(part) if members is not None else None
        if node is not None:
            return node
        for joined in ("_".join(parts), path):
            if (flat := raw.get(joined)) is not None:
                return flat
    return None


def _label(value: object) -> str:
    """Text where a member is text, or where it is an object with a ``label`` or ``value`` for
    people and programs (ntopng's way of giving a member)."""
    members = probes.as_object(value)
    if members is not None:
        return _text(members.get("label")) or _text(members.get("value"))
    return _text(value)


def _number(value: object) -> int | None:
    """A whole number, as a number or as text, that is not negative."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        return int(value) if value >= 0 and value.is_integer() else None
    shown = value.strip() if isinstance(value, str) else ""
    return int(shown) if shown.isascii() and shown.isdigit() else None


def _words(value: object) -> list[str]:
    """What a program gives as a list of words, or as one."""
    items = probes.as_array(value)
    return [word for item in items or [value] if (word := _text(item, 60))]


def _facts(pairs: Iterable[tuple[str, object]]) -> list[list[str]]:
    """The pairs that have something to say, as [label, value]."""
    found = [[label, shown] for label, value in pairs if (shown := _label(value))]
    return found[:MAX_FACTS]


def _unique(words: Iterable[str], limit: int) -> list[str]:
    return list(dict.fromkeys(words))[:limit]


def _indicators(pairs: Iterable[tuple[str, object]]) -> list[Indicator]:
    found = [Indicator(kind=kind, value=shown) for kind, value in pairs if (shown := _label(value))]
    unique = list({(each["kind"], each["value"]): each for each in found}.values())
    return unique[:MAX_INDICATORS]


def _traffic(
    packets_out: object, packets_in: object, bytes_out: object, bytes_in: object
) -> Traffic | None:
    """The flow's volume, or nothing if the program gave none of it."""
    found: Traffic = {}
    for key, value in (
        ("packets_out", packets_out),
        ("packets_in", packets_in),
        ("bytes_out", bytes_out),
        ("bytes_in", bytes_in),
    ):
        if (count := _number(value)) is not None:
            found[key] = count  # type: ignore[literal-required]
    return found or None


def _finish(
    *,
    facts: list[list[str]],
    tags: Iterable[str] = (),
    mitre: Sequence[Mitre] = (),
    indicators: list[Indicator] | None = None,
    traffic: Traffic | None = None,
    host: str = "",
    app: str = "",
    excerpt: str = "",
) -> Evidence | None:
    """The evidence, or nothing if there is none."""
    found = Evidence(
        facts=facts,
        tags=_unique(tags, MAX_TAGS),
        mitre=list(mitre)[:MAX_MITRE],
        indicators=indicators or [],
    )
    if traffic:
        found["traffic"] = traffic
    if host:
        found["host"] = host
    if app:
        found["app"] = app
    if excerpt:
        found["excerpt"] = excerpt
    empty = not (facts or found["tags"] or mitre or found["indicators"] or traffic)
    return None if empty and not (host or app or excerpt) else found


def _suricata(raw: Raw) -> Evidence | None:
    """What Suricata said, as OPNsense gives it."""
    return _finish(
        facts=_facts(
            [
                ("Signature", _pick(raw, "alert_sid", "alert.signature_id")),
                ("Generation", _pick(raw, "alert_gid", "alert.gid")),
                ("Revision", _pick(raw, "alert_rev", "alert.rev")),
                ("Action", _pick(raw, "alert_action", "alert.action")),
                ("Category", _pick(raw, "alert_category", "alert.category")),
                ("Direction", _pick(raw, "direction")),
                ("Interface", _pick(raw, "in_iface")),
                ("HTTP method", _pick(raw, "http.http_method", "http.method")),
                ("HTTP status", _pick(raw, "http.status")),
                ("DNS type", _pick(raw, "dns.rrtype")),
                ("TLS version", _pick(raw, "tls.version")),
                ("Flow", _pick(raw, "flow_id")),
            ]
        ),
        tags=_words(_pick(raw, "alert_category", "alert.category")),
        indicators=_indicators(
            [
                ("hostname", _pick(raw, "http.hostname")),
                ("url", _pick(raw, "http.url")),
                ("user_agent", _pick(raw, "http.http_user_agent", "http.user_agent")),
                ("dns", _pick(raw, "dns.rrname")),
                ("sni", _pick(raw, "tls.sni")),
                ("file", _pick(raw, "fileinfo.filename")),
            ]
        ),
        traffic=_traffic(
            _pick(raw, "flow.pkts_toserver"),
            _pick(raw, "flow.pkts_toclient"),
            _pick(raw, "flow.bytes_toserver"),
            _pick(raw, "flow.bytes_toclient"),
        ),
        app=_text(_pick(raw, "app_proto"), 32).lower(),
    )


def _mitre(rule: Raw) -> list[Mitre]:
    """The techniques of a Wazuh rule. It lists their ids, their tactics and their names side by
    side, and the ids are what the others are matched to."""
    found = probes.as_object(rule.get("mitre"))
    if found is None:
        return []
    ids, tactics, names = (_words(found.get(key)) for key in ("id", "tactic", "technique"))
    return [
        Mitre(
            id=ident,
            # A rule that lists as many names as ids names them in order; otherwise the tactics
            # and names belong to the rule, not to a technique, and are said of each.
            tactic=tactics[index] if len(tactics) == len(ids) else ", ".join(tactics),
            technique=names[index] if len(names) == len(ids) else ", ".join(names),
        )
        for index, ident in enumerate(ids)
    ]


def _wazuh(raw: Raw) -> Evidence | None:
    """What Wazuh said: the rule, the machine and the log line."""
    rule = probes.as_object(raw.get("rule")) or {}
    agent_name, agent_ip = _text(_pick(raw, "agent.name"), 80), _text(_pick(raw, "agent.ip"), 45)
    host = f"{agent_name} ({agent_ip})" if agent_name and agent_ip else agent_name or agent_ip
    compliance = (
        f"{standard}: {requirement}"
        for standard in ("pci_dss", "gdpr", "hipaa", "nist_800_53", "tsc")
        for requirement in _words(rule.get(standard))[:3]
    )
    return _finish(
        facts=_facts(
            [
                ("Rule", rule.get("id")),
                ("Level", rule.get("level")),
                ("Times it fired", rule.get("firedtimes")),
                ("Decoder", _pick(raw, "decoder.name")),
                ("Log source", _pick(raw, "location")),
                ("Manager", _pick(raw, "manager.name")),
                ("File", _pick(raw, "syscheck.path")),
                ("File event", _pick(raw, "syscheck.event")),
            ]
        ),
        tags=[*_words(rule.get("groups")), *compliance],
        mitre=_mitre(rule),
        indicators=_indicators(
            [
                ("user", _pick(raw, "data.srcuser")),
                ("user", _pick(raw, "data.dstuser")),
                ("hostname", _pick(raw, "data.hostname")),
                ("url", _pick(raw, "data.url")),
                ("country", _pick(raw, "GeoLocation.country_name")),
                ("file", _pick(raw, "syscheck.path")),
            ]
        ),
        host=host,
        excerpt=_text(raw.get("full_log"), MAX_EXCERPT),
    )


def _ntopng(raw: Raw) -> Evidence | None:
    """What ntopng said: how bad it scored the flow, and what the flow was."""
    role = next(
        (
            word
            for key, word in (
                ("is_cli_attacker", "The client is the attacker"),
                ("is_srv_attacker", "The server is the attacker"),
                ("is_cli_victim", "The client is the victim"),
                ("is_srv_victim", "The server is the victim"),
            )
            if _pick(raw, key) in (True, 1, "1", "true")
        ),
        "",
    )
    return _finish(
        facts=_facts(
            [
                ("Alert type", _pick(raw, "alert_id")),
                ("Score", _pick(raw, "score")),
                ("Severity", _pick(raw, "severity")),
                ("Role", role or _pick(raw, "role")),
            ]
        ),
        tags=_words(_label(_pick(raw, "alert_id"))),
        indicators=_indicators(
            [
                ("hostname", _pick(raw, "cli_name")),
                ("hostname", _pick(raw, "srv_name")),
            ]
        ),
        app=_text(_label(_pick(raw, "l7_proto")), 32).lower(),
    )


def _crowdsec(raw: Raw) -> Evidence | None:
    """What CrowdSec said of a decision."""
    return _finish(
        facts=_facts(
            [
                ("Remedy", _pick(raw, "type")),
                ("Scenario", _pick(raw, "scenario")),
                ("Origin", _pick(raw, "origin")),
                ("For", _pick(raw, "duration")),
                ("Scope", _pick(raw, "scope")),
            ]
        ),
        tags=_words(_pick(raw, "origin")),
    )


_READERS: Final = {
    "opnsense": _suricata,
    "wazuh": _wazuh,
    "ntopng": _ntopng,
    "crowdsec": _crowdsec,
}


def extract(source: str, raw: object) -> Evidence | None:
    """What is worth showing of one event's own record, or nothing: the record is not there (it
    was too big to keep, or the program gave none), the program is not one this reads, or it said
    nothing more than the event already does."""
    reader = _READERS.get(source)
    members = probes.as_object(raw)
    if reader is None or members is None:
        return None
    return reader(members)


def kept(source: str, raw: object) -> dict[str, Any]:
    """What a signal keeps of its event's record: the evidence, or ``{}`` where there is none,
    which says it was read."""
    return dict(extract(source, raw) or {})


def load(signal: IncidentSignal) -> Evidence | None:
    """What a signal kept, or nothing if it has none or has not been read."""
    return Evidence(**signal.evidence) if signal.evidence else None  # type: ignore[typeddict-item]


def read_pending(db: Session) -> int:
    """Reads the evidence of the signals that have none yet, a batch at a time, from their events
    while those are stored. It is how signals filed before this was kept get theirs; a signal whose
    event is gone has none to read and is marked read. The caller commits. Returns how many it
    read."""
    pending = db.scalars(
        select(IncidentSignal)
        .where(IncidentSignal.evidence.is_(None))
        .order_by(IncidentSignal.id)
        .limit(BATCH)
    ).all()
    if not pending:
        return 0
    rows = db.execute(
        select(Event.id, Event.source, Event.raw).where(
            Event.id.in_([signal.event_id for signal in pending]),
            Event.occurred_at >= min(signal.occurred_at for signal in pending),
            Event.occurred_at <= max(signal.occurred_at for signal in pending),
        )
    ).all()
    records = {row.id: (row.source, row.raw) for row in rows}
    for signal in pending:
        signal.evidence = kept(*records[signal.event_id]) if signal.event_id in records else {}
    return len(pending)
