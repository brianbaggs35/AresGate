"""GreyNoise's report on an internet address, read from its API.

GreyNoise listens on sensors all over the Internet and records who is scanning and attacking
everything at random. Asking about an address answers one of three things. *Noise*: the address
was seen scanning the Internet, and GreyNoise classifies it as benign (a known researcher or
search engine), malicious or unknown. *RIOT*: it belongs to a common business service, such as a
public DNS resolver or a cloud provider, that does what it should. Or nothing: GreyNoise has not
seen it. Nothing says little, because an attacker who aims at one home alone shows up on no
sensor. What it does say is that an address that is noise is one of the thousands that probe
every address, which is a reason to take an alert about it less seriously, not more.

There are three ways to ask, by what the account has:

- No account: the Community API, with no key, allows 10 lookups a day.
- A free account: the Community API with the key, which allows 50 searches a week, shared with
  the GreyNoise Visualizer. Only an account made with a business email is given a key.
- A subscription (Standard, Advanced or Elite): the IP Lookup API, which also answers with the
  tags and the actor that GreyNoise attaches, the CVEs, Tor and VPN and the network's owner.

The key goes in the ``key`` header. A 429 means the allowance is used up, and holds lookups for
``THROTTLE``. GreyNoise's Community API takes only a routable IPv4 address, so nothing else is
asked about.

An answer says one thing about an address, so a report counts one source: malicious, suspicious
or harmless. The rest of what GreyNoise says is kept as details (see ``answers.Report``).
"""

from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Literal, cast

from app import audit
from app.integrations.client import ApiClient, CallFailed, Recorder, Reply, Target
from app.integrations.netguard import AddressPolicy
from app.intel.answers import Answer, Failed, Judgement, Report, Reported, Throttled, Unknown
from app.intel.subjects import Subject

PROVIDER = "greynoise"
KEY_HEADER = "key"
SITE = "https://viz.greynoise.io"
# How long lookups wait after GreyNoise answers 429. Its answer gives no time for that, and the
# allowance it counts is a day's or a week's, so an hour is a pause that spends little.
THROTTLE = timedelta(hours=1)

type Plan = Literal["anonymous", "free", "subscription"]
ANONYMOUS: Plan = "anonymous"
FREE: Plan = "free"
SUBSCRIPTION: Plan = "subscription"

MAX_NAME = 120
MAX_COUNTRY = 8
MAX_ASN = 4_294_967_295
MAX_CATEGORIES = 12
MAX_LIST = 200
# What the details are called, which the judgement and the pages that show them read too.
CLASSIFICATION = "Classification"
LAST_SEEN = "Last seen"
FIRST_SEEN = "First seen"
BUSINESS = "Business service"
ACTOR = "Actor"
TAGS = "Tags"
CVES = "CVEs"
TOR = "Tor exit node"
VPN = "VPN"
HOSTNAME = "Reverse DNS"
# What GreyNoise calls an address it classifies, which the report counts as a source of its own.
MALICIOUS = "malicious"
BENIGN = "benign"
UNCLASSIFIED = "unknown"


def plan_of(options: Mapping[str, str | int]) -> Plan:
    """What the connection's settings say the account has: no account, a free account's key or a
    subscription's. Anything else is the free account, which is the most careful."""
    if options.get("access") == "none":
        return ANONYMOUS
    return SUBSCRIPTION if options.get("plan") == "subscription" else FREE


def judge(report: Report | None) -> Judgement:
    """What GreyNoise's report comes to. No report is unknown, and so is an address GreyNoise has
    not seen: that says little. An address in RIOT or classified benign is clean, one classified
    malicious is malicious, and one seen scanning that GreyNoise doesn't classify is suspicious."""
    if report is None:
        return "unknown"
    if report.malicious:
        return "malicious"
    if report.suspicious:
        return "suspicious"
    return "clean" if report.harmless else "unknown"


def _object(value: object) -> dict[str, object] | None:
    return cast("dict[str, object]", value) if isinstance(value, dict) else None


def _list(value: object) -> list[object]:
    return cast("list[object]", value) if isinstance(value, list) else []


def _text(value: object, limit: int) -> str | None:
    """Text GreyNoise gave, cleaned, or None for none. It says ``unknown`` where it has no name."""
    cleaned = audit.clean(value, limit) if isinstance(value, str) else None
    return None if cleaned is None or cleaned.lower() == UNCLASSIFIED else cleaned


def _flag(value: object) -> bool:
    return value is True


def _stamp(value: object) -> datetime | None:
    """A time as GreyNoise writes it: a date (``2026-03-18``) or a timestamp in UTC."""
    if not isinstance(value, str):
        return None
    try:
        when = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (when if when.tzinfo else when.replace(tzinfo=UTC)).astimezone(UTC)


def _asn(value: object) -> int | None:
    """The number in ``AS14061``."""
    text = _text(value, 20)
    if text is None or text[:2].upper() != "AS" or not text[2:].isdigit():
        return None
    number = int(text[2:])
    return number if 0 <= number <= MAX_ASN else None


def _names(value: object, key: str) -> list[str]:
    """The names in a list of objects."""
    found: list[str] = []
    for item in _list(value):
        entry = _object(item)
        if entry is not None and (text := _text(entry.get(key), MAX_NAME)):
            found.append(text)
    return found


def _joined(items: list[str]) -> str | None:
    return ", ".join(dict.fromkeys(items))[:MAX_LIST] or None


def _classified(classification: object, *, riot: bool) -> tuple[int, int, int]:
    """The malicious, suspicious and harmless counts for what GreyNoise classifies the address as.
    A business service is harmless whatever else it does. Only an address that is noise or a
    business service is counted, so there is no third case to give none."""
    if riot:
        return 0, 0, 1
    if classification == MALICIOUS:
        return 1, 0, 0
    if classification == BENIGN:
        return 0, 0, 1
    return 0, 1, 0


def _report(
    counts: tuple[int, int, int],
    when: datetime | None,
    now: datetime,
    rows: list[tuple[str, str | None]],
    *,
    owner: str | None = None,
    asn: int | None = None,
    country: str | None = None,
    categories: tuple[str, ...] = (),
) -> Report:
    malicious, suspicious, harmless = counts
    return Report(
        malicious=malicious,
        suspicious=suspicious,
        harmless=harmless,
        undetected=0,
        reputation=0,
        analysed_at=when or now,
        country=country,
        owner=owner,
        asn=asn,
        categories=categories[:MAX_CATEGORIES],
        details=tuple((label, value) for label, value in rows if value),
    )


def _community(root: dict[str, object], now: datetime) -> Answer:
    """What the Community API says. ``noise`` is that the address was seen scanning, ``riot`` that
    it is a business service's."""
    noise, riot = _flag(root.get("noise")), _flag(root.get("riot"))
    if not noise and not riot:
        return Unknown()
    classification = root.get("classification")
    name = _text(root.get("name"), MAX_NAME)
    rows: list[tuple[str, str | None]] = [
        (CLASSIFICATION, classification if isinstance(classification, str) else None),
        (LAST_SEEN, _text(root.get("last_seen"), 20)),
        (BUSINESS, name if riot else None),
    ]
    return Reported(
        _report(
            _classified(classification, riot=riot),
            _stamp(root.get("last_seen")),
            now,
            rows,
            owner=name,
        )
    )


def _business(root: dict[str, object]) -> str | None:
    """Which business service an address is, and how far GreyNoise trusts it, if it is one."""
    service = _object(root.get("business_service_intelligence"))
    if service is None or not _flag(service.get("found")):
        return None
    name = _text(service.get("name"), MAX_NAME) or _text(service.get("category"), MAX_NAME)
    trust = _text(service.get("trust_level"), 4)
    if name is None:
        return "yes"
    return f"{name} (trust level {trust})" if trust else name


def _subscribed(root: dict[str, object], now: datetime) -> Answer:
    """What the IP Lookup API says, with what a plan that holds back some fields leaves out."""
    scanner = _object(root.get("internet_scanner_intelligence")) or {}
    noise = _flag(scanner.get("found"))
    business = _business(root)
    if not noise and business is None:
        return Unknown()
    classification = scanner.get("classification")
    where = _object(scanner.get("metadata")) or {}
    tags = _names(scanner.get("tags"), "name")
    cves = [text for item in _list(scanner.get("cves")) if (text := _text(item, MAX_NAME))]
    service = _text(scanner.get("vpn_service"), MAX_NAME)
    rows: list[tuple[str, str | None]] = [
        (CLASSIFICATION, classification if noise and isinstance(classification, str) else None),
        (LAST_SEEN, _text(scanner.get("last_seen"), 20)),
        (FIRST_SEEN, _text(scanner.get("first_seen"), 20)),
        (BUSINESS, business),
        (ACTOR, _text(scanner.get("actor"), MAX_NAME)),
        (TAGS, _joined(tags)),
        (CVES, _joined(cves)),
        (TOR, "yes" if _flag(scanner.get("tor")) else None),
        (VPN, service or ("yes" if _flag(scanner.get("vpn")) else None)),
        (HOSTNAME, _text(where.get("rdns"), MAX_NAME)),
    ]
    return Reported(
        _report(
            _classified(classification, riot=business is not None),
            _stamp(scanner.get("last_seen_timestamp")) or _stamp(scanner.get("last_seen")),
            now,
            rows,
            owner=_text(where.get("organization"), MAX_NAME),
            asn=_asn(where.get("asn")),
            country=_text(where.get("source_country_code"), MAX_COUNTRY),
            categories=tuple(dict.fromkeys(tags)),
        )
    )


def parse(body: object, now: datetime) -> Answer:
    """What an answer from either API says: a report, none if GreyNoise has not seen the address,
    or a failure if it is not an answer about an address."""
    root = _object(body)
    if root is None:
        return Failed("GreyNoise's answer wasn't an object.")
    if "business_service_intelligence" in root or "internet_scanner_intelligence" in root:
        return _subscribed(root, now)
    if "noise" in root or "riot" in root:
        return _community(root, now)
    return Failed("GreyNoise's answer didn't hold an address's report.")


def link_of(address: str, *, business: bool = False) -> str:
    """The page on GreyNoise's Visualizer about an address, for reading what it holds in full. A
    business service has a page of its own."""
    return f"{SITE}/{'riot' if business else 'ip'}/{address}"


def _path(subject: Subject, plan: Plan) -> str | None:
    """The page of the API about a subject, or None for one GreyNoise isn't asked about: only an
    IPv4 address is."""
    if subject.kind != "ip" or ":" in subject.host:
        return None
    return f"/v3/ip/{subject.host}" if plan == SUBSCRIPTION else f"/v3/community/{subject.host}"


# What GreyNoise says when it refuses, in words for the person who has to act on it.
_REFUSED = {
    401: "GreyNoise didn't accept the key. Copy it again from your GreyNoise account.",
    403: "GreyNoise refused this request. The plan the key belongs to may not include it.",
}


async def look_up(client: ApiClient, target: Target, subject: Subject, now: datetime) -> Answer:
    """Asks for the report on one subject. Raises ``CallFailed`` if no answer came at all."""
    plan = plan_of(target.options)
    path = _path(subject, plan)
    if path is None:
        return Failed("GreyNoise is only asked about IPv4 addresses.")
    headers = {} if plan == ANONYMOUS else {KEY_HEADER: target.secrets["api_key"]}
    reply = await client.request("GET", path, headers=headers)
    return answer_of(reply, now)


def answer_of(reply: Reply, now: datetime) -> Answer:
    """What a reply from GreyNoise says."""
    if reply.status == 404:
        return Unknown()
    if reply.status == 429:
        return Throttled(until=now + THROTTLE)
    if not reply.ok:
        return Failed(_REFUSED.get(reply.status, f"GreyNoise answered HTTP {reply.status}."))
    return parse(reply.json(), now)


async def ask(
    target: Target,
    record: Recorder,
    policy: AddressPolicy,
    subject: Subject,
    now: datetime,
) -> Answer:
    """Asks GreyNoise about one subject over a logged connection. A request that gets no answer is
    a failure, with the reason in words."""
    try:
        async with ApiClient(target, record, policy) as client:
            return await look_up(client, target, subject, now)
    except CallFailed as failure:
        return Failed(str(failure))


NOT_SEEN = (
    "GreyNoise hasn't seen it scanning the internet or listed it as a business service. That says "
    "little: an attack aimed at one network alone doesn't show on its sensors."
)


def said(
    details: Iterable[tuple[str, str]], judgement: str, text: Callable[[str, int], str]
) -> str:
    """What a report says of an address, in a sentence for the AI to read, with what GreyNoise
    gave as text passed through ``text`` (the redaction). The address is left to the caller."""
    kept = dict(details)
    if BUSINESS in kept:
        what = f"a common business service ({text(kept[BUSINESS], 80)})"
    else:
        what = f"seen scanning the internet and classified {kept.get(CLASSIFICATION, 'unknown')}"
    more = [
        f"{label.lower()} {text(kept[label], 120)}"
        for label in (ACTOR, TAGS, CVES)
        if label in kept
    ]
    more += [f"a {TOR.lower()}"] if TOR in kept else []
    more += [f"behind a VPN ({text(kept[VPN], 60)})"] if VPN in kept else []
    since = f"; last seen {kept[LAST_SEEN]}" if LAST_SEEN in kept else ""
    return f"{what}{''.join('; ' + item for item in more)}{since}; GreyNoise makes it {judgement}"
