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
dots. ntopng: the members of a flow alert as its alert list gives them (``cli_ip`` and
``srv_ip`` with their ``country``, ``location`` and ``blacklisted``, the ports with the service's
name, ``proto``, ``l7_proto``, ``duration``, ``total_bytes``, ``score``, ``severity``,
``alert_category``, ``mitre_data``, ``community_id``, ``info``, ``description``, the networks, the
VLAN and the host pools); they were read from a real answer, and what a version of ntopng leaves
out is not shown. Suricata's rule metadata is the Emerging Threats rules' (``signature_severity``,
``affected_product``, ``attack_target``, ``deployment``, ``confidence`` and the ``mitre_*``
words). Wazuh's vulnerability detector's ``data.vulnerability``.
CrowdSec: the members of a decision. What a version of a program leaves out is simply not shown.
"""

import html
import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Final, NotRequired, TypedDict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import clean
from app.integrations import probes
from app.models import Event, IncidentSignal

# How much of each kind of thing is kept, and how long each is.
MAX_FACTS: Final = 20
MAX_TAGS: Final = 12
MAX_MITRE: Final = 6
MAX_INDICATORS: Final = 10
MAX_VALUE: Final = 200
MAX_EXCERPT: Final = 400
MAX_SUMMARY: Final = 300
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


class Endpoint(TypedDict, total=False):
    """One end of the flow an alert is about, as far as the program said who it is."""

    address: str
    # What it is called, where that is not the address itself.
    name: str
    port: int
    # What the port is for (``domain``, ``https``), as the program names it.
    service: str
    # A country code, as the program gives it.
    country: str
    # ``local`` where the program says the end is on your network, ``remote`` where it is not.
    location: str
    # Whether the program has the address on a blacklist.
    blacklisted: bool


class Flow(TypedDict, total=False):
    """The two ends of the flow an alert is about, and what the program knows of the flow."""

    client: Endpoint
    server: Endpoint
    # ``tcp`` or ``udp``, as the program says it.
    protocol: str
    # How long the flow went on for, in seconds.
    duration: int


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
    # What the program says of the flow in its own plain words, such as ``Low goodput ratio``.
    summary: NotRequired[str]
    # How bad the program rates it by its own score, from 0.
    score: NotRequired[int]
    # The two ends of the flow, where the program names them.
    flow: NotRequired[Flow]
    # What was sent, where the program kept the data of the packet that set the alert off.
    payload: NotRequired[str]


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


_MARKUP: Final = re.compile(r"<[^>]*>")


def _plain(value: object, limit: int = MAX_SUMMARY) -> str:
    """Words where a program gives them as HTML for its own page: the tags taken out, the
    entities read and the white space made one space."""
    if not isinstance(value, str):
        return ""
    return _text(" ".join(html.unescape(_MARKUP.sub(" ", value)).split()), limit)


def _value_of(value: object) -> object:
    """What a member says for a program: its ``value`` where it is an object, as ntopng gives
    them, and otherwise the member itself."""
    members = probes.as_object(value)
    return members.get("value") if members is not None else value


def _truthy(value: object) -> bool:
    return value is True or value in (1, "1", "true", "True")


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
    summary: str = "",
    score: int | None = None,
    flow: Flow | None = None,
    payload: str = "",
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
    if summary:
        found["summary"] = summary
    if score is not None:
        found["score"] = score
    if flow:
        found["flow"] = flow
    if payload:
        found["payload"] = payload
    empty = not (facts or found["tags"] or mitre or found["indicators"] or traffic)
    more = host or app or excerpt or summary or score is not None or flow or payload
    return None if empty and not more else found


_PRIORITY: Final = {1: "High", 2: "Medium", 3: "Low"}


def _rule_mitre(metadata: Raw) -> list[Mitre]:
    """The technique an ET rule's metadata names, which gives it as words of its own."""
    ident = _text(_first(metadata.get("mitre_technique_id")), 20)
    name = _text(_first(metadata.get("mitre_technique_name")), 80)
    if not (ident or name):
        return []
    tactic = _text(_first(metadata.get("mitre_tactic_name")), 80)
    return [Mitre(id=ident, tactic=tactic, technique=name)]


def _first(value: object) -> object:
    """The first of what a program gives as a list of words, or the word."""
    items = probes.as_array(value)
    return items[0] if items else value


def _suricata(raw: Raw) -> Evidence | None:
    """What Suricata said, as OPNsense gives it."""
    metadata = probes.as_object(_pick(raw, "alert.metadata", "alert_metadata")) or {}
    priority = _number(_pick(raw, "alert_severity", "alert.severity"))
    return _finish(
        facts=_facts(
            [
                ("Signature", _pick(raw, "alert_sid", "alert.signature_id")),
                ("Generation", _pick(raw, "alert_gid", "alert.gid")),
                ("Revision", _pick(raw, "alert_rev", "alert.rev")),
                ("Action", _pick(raw, "alert_action", "alert.action")),
                ("Category", _pick(raw, "alert_category", "alert.category")),
                ("Priority", _PRIORITY.get(priority) if priority is not None else None),
                ("Rule severity", _first(metadata.get("signature_severity"))),
                ("Rule confidence", _first(metadata.get("confidence"))),
                ("Affected product", _first(metadata.get("affected_product"))),
                ("Target", _first(metadata.get("attack_target"))),
                ("Deployment", _first(metadata.get("deployment"))),
                ("Direction", _pick(raw, "direction")),
                ("Interface", _pick(raw, "in_iface")),
                ("HTTP method", _pick(raw, "http.http_method", "http.method")),
                ("HTTP status", _pick(raw, "http.status")),
                ("HTTP content type", _pick(raw, "http.http_content_type", "http.content_type")),
                ("HTTP response size", _pick(raw, "http.length")),
                ("Redirected to", _pick(raw, "http.redirect")),
                ("DNS type", _pick(raw, "dns.rrtype")),
                ("DNS answer", _pick(raw, "dns.rcode")),
                ("TLS version", _pick(raw, "tls.version")),
                ("Certificate for", _pick(raw, "tls.subject")),
                ("Certificate issued by", _pick(raw, "tls.issuerdn")),
                ("TLS client fingerprint", _pick(raw, "tls.ja3.hash")),
                ("Flow", _pick(raw, "flow_id")),
            ]
        ),
        tags=_words(_pick(raw, "alert_category", "alert.category")),
        mitre=_rule_mitre(metadata),
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
        payload=_text(_pick(raw, "payload_printable"), MAX_EXCERPT),
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
                ("Address in the log", _pick(raw, "data.srcip")),
                ("Port in the log", _pick(raw, "data.srcport")),
                ("Destination port", _pick(raw, "data.dstport")),
                ("Protocol", _pick(raw, "data.protocol")),
                ("Command", _pick(raw, "data.command")),
                ("Windows event", _pick(raw, "data.win.system.eventID")),
                ("Vulnerability", _pick(raw, "data.vulnerability.title")),
                ("Vulnerability severity", _pick(raw, "data.vulnerability.severity")),
                ("Package", _pick(raw, "data.vulnerability.package.name")),
                ("Package version", _pick(raw, "data.vulnerability.package.version")),
                ("Fix", _pick(raw, "data.vulnerability.status")),
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
                ("cve", _pick(raw, "data.vulnerability.cve")),
            ]
        ),
        host=host,
        excerpt=_text(raw.get("full_log"), MAX_EXCERPT),
    )


_NTOPNG_SEVERITY: Final = {
    0: "None",
    1: "Debug",
    2: "Info",
    3: "Notice",
    4: "Warning",
    5: "Error",
    6: "Critical",
    8: "Emergency",
}
# What ntopng says the information of a flow is, by the kind of traffic it was.
_INFO_OF: Final = {"dns": "dns", "tls": "sni", "quic": "sni", "ssl": "sni", "http": "hostname"}


def _end(raw: Raw, who: str) -> Endpoint:
    """One end of an ntopng flow, ``cli`` for the client or ``srv`` for the server: who it is,
    where it is and whether ntopng has it on a blacklist."""
    ip = probes.as_object(_pick(raw, f"{who}_ip", f"flow.{who}_ip")) or {}
    port = probes.as_object(_pick(raw, f"{who}_port", f"flow.{who}_port")) or {}
    address = _text(ip.get("ip") or ip.get("value"), 45)
    name = _text(ip.get("name") or ip.get("label"), 80)
    number = _number(port.get("value"))
    service = _text(port.get("label"), 32).lower()
    country = _text(ip.get("country"), 8).upper()
    location = _text(ip.get("location"), 8).lower()
    found = Endpoint()
    if address:
        found["address"] = address
    if name and name != address:
        found["name"] = name
    if number is not None:
        found["port"] = number
    if service and service != str(number):
        found["service"] = service
    if country:
        found["country"] = country
    if location in ("local", "remote"):
        found["location"] = location
    if "blacklisted" in ip:
        found["blacklisted"] = _truthy(ip["blacklisted"])
    return found


def _ntopng_flow(raw: Raw) -> Flow | None:
    """Who the flow was between, over what, and for how long."""
    flow = Flow()
    if client := _end(raw, "cli"):
        flow["client"] = client
    if server := _end(raw, "srv"):
        flow["server"] = server
    if protocol := _text(_label(_pick(raw, "proto")), 16).lower():
        flow["protocol"] = protocol
    if (duration := _number(_pick(raw, "duration"))) is not None:
        flow["duration"] = duration
    return flow or None


def _ntopng_app(raw: Raw) -> str:
    """What kind of traffic it was, such as ``dns``: ntopng's own name for it, without the
    transport it labels it with (``TCP:DNS``)."""
    found = probes.as_object(_pick(raw, "l7_proto"))
    if found is None:
        return _text(_pick(raw, "l7_proto"), 32).lower()
    word = _text(found.get("l7_label"), 32) or _text(found.get("label"), 32).rpartition(":")[2]
    return word.lower()


def _ntopng_mitre(raw: Raw) -> list[Mitre]:
    found = probes.as_object(_pick(raw, "mitre_data"))
    if found is None:
        return []
    ident = _text(found.get("mitre_id"), 20)
    technique = _text(found.get("mitre_technique_i18n"), 80) or _text(
        found.get("mitre_technique"), 80
    )
    tactic = _text(found.get("mitre_tactic_i18n"), 80) or _text(found.get("mitre_tactic"), 80)
    sub = _text(found.get("mitre_subtechnique_i18n"), 80) or _text(
        found.get("mitre_subtechnique"), 80
    )
    if not (ident or technique):
        return []
    return [Mitre(id=ident, tactic=tactic, technique=f"{technique}: {sub}" if sub else technique)]


def _ntopng_role(raw: Raw) -> str:
    return next(
        (
            word
            for key, word in (
                ("is_cli_attacker", "The client is the attacker"),
                ("is_srv_attacker", "The server is the attacker"),
                ("is_cli_victim", "The client is the victim"),
                ("is_srv_victim", "The server is the victim"),
            )
            if _truthy(_pick(raw, key))
        ),
        "",
    )


def _ntopng(raw: Raw) -> Evidence | None:
    """What ntopng said: how bad it scored the flow, what the flow was and who it was between."""
    bytes_sent = probes.as_object(_pick(raw, "total_bytes")) or {}
    level = _number(_value_of(_pick(raw, "severity")))
    vlan = _number(_value_of(_pick(raw, "vlan_id")))
    pool = _label(_pick(raw, "cli_host_pool_id"))
    app = _ntopng_app(raw)
    return _finish(
        facts=_facts(
            [
                ("Alert type", _pick(raw, "alert_id")),
                ("Score", _pick(raw, "score")),
                ("Severity", _NTOPNG_SEVERITY.get(level) if level is not None else None),
                ("Category", _pick(raw, "alert_category")),
                ("Role", _ntopng_role(raw) or _pick(raw, "role")),
                ("Packets", bytes_sent.get("total_packets")),
                ("Client network", _pick(raw, "cli_network")),
                ("Server network", _pick(raw, "srv_network")),
                ("VLAN", vlan or None),
                ("Host pool", pool if pool.lower() != "default" else None),
            ]
        ),
        tags=[
            *_words(_label(_pick(raw, "alert_id"))),
            *_words(_label(_pick(raw, "alert_category"))),
        ],
        mitre=_ntopng_mitre(raw),
        indicators=_indicators(
            [
                ("hostname", _pick(raw, "cli_name")),
                ("hostname", _pick(raw, "srv_name")),
                (_INFO_OF.get(app, "info"), _pick(raw, "info")),
                ("community_id", _pick(raw, "community_id")),
            ]
        ),
        traffic=_traffic(None, None, bytes_sent.get("bytes_sent"), bytes_sent.get("bytes_rcvd")),
        app=app,
        summary=_plain(_pick(raw, "description.descr"))
        or _plain(_pick(raw, "msg.description"))
        or _plain(_pick(raw, "description")),
        score=_number(_value_of(_pick(raw, "score"))),
        flow=_ntopng_flow(raw),
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
