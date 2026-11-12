"""AlienVault OTX's report on an internet address or a domain, read from its API.

OTX is a community of researchers who share *pulses*: a report of a threat with the indicators that
belong to it, such as the addresses a botnet used. Asking about an address answers with the pulses
that name it, and with a few facts about it. The key goes in the ``X-OTX-API-KEY`` header.

A pulse naming an address is a lead, not a verdict. Researchers also list scanners, mail servers
and cloud ranges that did nothing wrong, so the counts are shown beside what is made of them, and
what is made of them is said as a judgement the AI and the owner can overrule. A pulse that also
names a malware family, an adversary or an attack technique says more than one that only lists the
address, so those count as *malicious* and the others as *suspicious* (see ``answers.Report``). An
address OTX lists as safe is clean, whatever else names it.

OTX publishes no figure for how many requests it allows, so AresGate paces itself (see
``intel.budget``). A 429 holds lookups for ``THROTTLE``, and a key that OTX refuses answers 401 or
403, which a lookup reports as a failure. An address OTX knows nothing of still answers with an
empty ``pulse_info``; 404 is taken as the same.

Only addresses and domains are asked about. A web address would have to go in the request path, and
the API log keeps that path.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import cast

from app import audit
from app.integrations.client import ApiClient, CallFailed, Recorder, Reply, Target
from app.integrations.netguard import AddressPolicy
from app.intel.answers import Answer, Failed, Judgement, Report, Reported, Throttled, Unknown
from app.intel.subjects import Subject

PROVIDER = "otx"
KEY_HEADER = "X-OTX-API-KEY"
SITE = "https://otx.alienvault.com"
# How long lookups wait after OTX answers 429. Its answer gives no time for that.
THROTTLE = timedelta(minutes=5)
MAX_COUNT = 1_000_000
MAX_ASN = 4_294_967_295
MAX_NAME = 120
MAX_COUNTRY = 8
MAX_CATEGORIES = 12
MAX_NAMED = 5
# How many pulses are looked through for what they name: OTX lists the newest few dozen.
MAX_PULSES = 50
# What the details are called, which the judgement reads too.
PULSES = "Pulses"
SAFE = "Listed as safe"
NEWEST = "Newest pulse"
MALWARE = "Malware"
ADVERSARY = "Adversary"
TECHNIQUES = "Attack techniques"

# How many pulses make an address malicious. One that also names malware or an adversary needs
# fewer, since it says more.
NAMED_MALICIOUS = 2
BARE_MALICIOUS = 5


def judge(report: Report | None) -> Judgement:
    """What OTX's report comes to. No report is unknown. An address OTX lists as safe is clean.
    Pulses that name malware or an adversary, or a good many pulses, make it malicious; any pulse
    makes it suspicious. An address no pulse names is unknown, not clean: new attackers often have
    none yet, and OTX only knows what researchers have shared."""
    if report is None:
        return "unknown"
    if any(label == SAFE for label, _ in report.details):
        return "clean"
    total = report.malicious + report.suspicious
    if report.malicious >= NAMED_MALICIOUS or total >= BARE_MALICIOUS:
        return "malicious"
    return "suspicious" if total > 0 else "unknown"


def _object(value: object) -> dict[str, object] | None:
    return cast("dict[str, object]", value) if isinstance(value, dict) else None


def _list(value: object) -> list[object]:
    return cast("list[object]", value) if isinstance(value, list) else []


def _whole(value: object, low: int, high: int) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        return None
    return value


def _text(value: object, limit: int) -> str | None:
    return audit.clean(value, limit) if isinstance(value, str) and value.strip() else None


def _names(value: object, *keys: str) -> list[str]:
    """The names in a list that holds text, or objects with a name under one of ``keys``."""
    found: list[str] = []
    for item in _list(value):
        entry = _object(item)
        raw = item if entry is None else next((entry[key] for key in keys if key in entry), None)
        if text := _text(raw, MAX_NAME):
            found.append(text)
    return found


def _split_asn(value: object) -> tuple[int | None, str | None]:
    """The number and the owner in ``AS14061 DIGITALOCEAN-ASN``."""
    text = _text(value, 160)
    if text is None:
        return None, None
    number, _, owner = text.partition(" ")
    if number[:2].upper() == "AS" and number[2:].isdigit():
        return _whole(int(number[2:]), 0, MAX_ASN), _text(owner, MAX_NAME)
    return None, text[:MAX_NAME]


def _stamp(value: object) -> datetime | None:
    """A time as OTX writes it, ``2026-03-01T10:20:30.123456`` in UTC."""
    if not isinstance(value, str):
        return None
    try:
        when = datetime.fromisoformat(value)
    except ValueError:
        return None
    return (when if when.tzinfo else when.replace(tzinfo=UTC)).astimezone(UTC)


def _safe(root: dict[str, object]) -> str | None:
    """Why OTX lists the subject as safe, from its validation notes, if it does."""
    for item in _list(root.get("validation")):
        note = _object(item)
        if note is None:
            continue
        source = _text(note.get("source"), 40) or ""
        if source.lower() in {"whitelist", "false_positive", "falsepositive"}:
            return _text(note.get("message"), 200) or _text(note.get("name"), 200) or "yes"
    return None


@dataclass
class _Named:
    """What the pulses of an answer name: the malware families, adversaries and attack techniques,
    the tags, and how many of the pulses name any of the first three."""

    malware: list[str] = field(default_factory=list[str])
    adversaries: list[str] = field(default_factory=list[str])
    techniques: list[str] = field(default_factory=list[str])
    tags: list[str] = field(default_factory=list[str])
    strong: int = 0


def _named_by(pulses: list[dict[str, object]]) -> _Named:
    """What the pulses name, read through each of them."""
    found = _Named()
    for pulse in pulses:
        families = _names(pulse.get("malware_families"), "display_name", "id")
        adversary = _text(pulse.get("adversary"), MAX_NAME)
        attacks = _names(pulse.get("attack_ids"), "id")
        found.strong += bool(families or adversary or attacks)
        found.malware += families
        found.adversaries += [adversary] if adversary else []
        found.techniques += attacks
        found.tags += _names(pulse.get("tags"))
    return found


def parse(body: object, now: datetime) -> Report | None:
    """The report in OTX's answer, or None if the answer isn't an indicator's. An indicator that
    no pulse names is a report of none."""
    root = _object(body)
    if root is None or ("pulse_info" not in root and "indicator" not in root):
        return None
    info = _object(root.get("pulse_info")) or {}
    count = _whole(info.get("count"), 0, MAX_COUNT) or 0
    pulses = [_object(item) for item in _list(info.get("pulses"))[:MAX_PULSES]]
    named = [pulse for pulse in pulses if pulse is not None]
    found = _named_by(named)
    # The pulses listed are the newest few; the count is all of them, so what is beyond the list is
    # taken as the plainer kind.
    malicious = min(found.strong, count)
    suspicious = max(count - malicious, 0)
    asn, owner = _split_asn(root.get("asn"))
    reputation = _whole(root.get("reputation"), 0, MAX_COUNT) or 0
    newest = max(
        (_stamp(pulse.get("modified")) or _stamp(pulse.get("created")) for pulse in named),
        default=None,
        key=lambda when: when or datetime.min.replace(tzinfo=UTC),
    )
    rows: list[tuple[str, str | None]] = [
        (PULSES, str(count) if count else None),
        (NEWEST, _text(named[0].get("name"), 200) if named else None),
        (MALWARE, ", ".join(dict.fromkeys(found.malware))[:200] or None),
        (ADVERSARY, ", ".join(dict.fromkeys(found.adversaries))[:200] or None),
        (TECHNIQUES, ", ".join(dict.fromkeys(found.techniques))[:200] or None),
        (SAFE, _safe(root)),
    ]
    return Report(
        malicious=malicious,
        suspicious=suspicious,
        harmless=0,
        undetected=0,
        # OTX's reputation is a score that rises with bad behaviour; the report's falls with it.
        reputation=-reputation,
        analysed_at=newest or now,
        country=_text(root.get("country_code"), MAX_COUNTRY),
        owner=owner,
        asn=asn,
        categories=tuple(dict.fromkeys([*found.malware, *found.adversaries, *found.tags]))[
            :MAX_CATEGORIES
        ],
        details=tuple((label, value) for label, value in rows if value),
    )


def _path(subject: Subject) -> str | None:
    """The page of the API about a subject, or None for one OTX isn't asked about."""
    if subject.kind == "ip":
        version = "IPv6" if ":" in subject.host else "IPv4"
        return f"/api/v1/indicators/{version}/{subject.host}/general"
    if subject.kind == "domain":
        return f"/api/v1/indicators/domain/{subject.host}/general"
    return None


def link_for(subject: Subject) -> str | None:
    """The page on OTX's website about the subject, for reading its pulses in full."""
    return link_of(subject.kind, subject.key)


def link_of(kind: str, key: str) -> str | None:
    if kind == "ip":
        return f"{SITE}/indicator/ip/{key}"
    if kind == "domain":
        return f"{SITE}/indicator/domain/{key}"
    return None


# What OTX says when it refuses a key, in words for the person who has to act on it.
_REFUSED = {
    401: "OTX didn't accept the key. Copy it again from your OTX account's settings.",
    403: "OTX refused this request with the key. Check that the key is the one for your account.",
}


async def look_up(client: ApiClient, target: Target, subject: Subject, now: datetime) -> Answer:
    """Asks for the report on one subject. Raises ``CallFailed`` if no answer came at all."""
    path = _path(subject)
    if path is None:
        return Failed("OTX is only asked about addresses and domains.")
    reply = await client.request("GET", path, headers={KEY_HEADER: target.secrets["api_key"]})
    return answer_of(reply, now)


def answer_of(reply: Reply, now: datetime) -> Answer:
    """What a reply from OTX says."""
    if reply.status == 404:
        return Unknown()
    if reply.status == 429:
        return Throttled(until=now + THROTTLE)
    if not reply.ok:
        return Failed(_REFUSED.get(reply.status, f"OTX answered HTTP {reply.status}."))
    report = parse(reply.json(), now)
    if report is None:
        return Failed("OTX's answer didn't hold an indicator.")
    return Reported(report)


async def ask(
    target: Target,
    record: Recorder,
    policy: AddressPolicy,
    subject: Subject,
    now: datetime,
) -> Answer:
    """Asks OTX about one subject over a logged connection. A request that gets no answer is a
    failure, with the reason in words."""
    try:
        async with ApiClient(target, record, policy) as client:
            return await look_up(client, target, subject, now)
    except CallFailed as failure:
        return Failed(str(failure))
