"""VirusTotal's report on an internet address, a domain or a web address, read from its API
version 3.

The key goes in the ``x-apikey`` header. Something VirusTotal has never analysed answers 404, which
is an answer rather than a failure; a key that VirusTotal refuses answers 401 or 403, which a lookup
reports as a failure. A limit answers 429: a used-up quota holds lookups until the daily reset at
midnight UTC, and any other limit holds them for a minute.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Literal, cast

from app import audit
from app.integrations.client import ApiClient, CallFailed, Recorder, Reply, Target
from app.integrations.netguard import AddressPolicy
from app.intel import subjects
from app.intel.subjects import Subject

PROVIDER = "virustotal"
KEY_HEADER = "x-apikey"
SITE = "https://www.virustotal.com"
# How big the counts and the score can be, and the latest time an analysis can be dated to.
MAX_COUNT = 1_000_000
MAX_ASN = 4_294_967_295
MAX_EPOCH = 4_102_444_800
MAX_NAME = 120
MAX_COUNTRY = 8
MAX_TITLE = 200
MAX_URL = 2048
MAX_CATEGORIES = 12
# How long lookups wait after VirusTotal asks for fewer requests. Its page gives no time for that.
THROTTLE = timedelta(minutes=1)

type Judgement = Literal["malicious", "suspicious", "clean", "unknown"]


@dataclass(frozen=True)
class Report:
    """What VirusTotal said of one subject."""

    malicious: int
    suspicious: int
    harmless: int
    undetected: int
    reputation: int
    analysed_at: datetime
    country: str | None = None
    owner: str | None = None
    asn: int | None = None
    # The categories the engines gave the subject, each once, in order.
    categories: tuple[str, ...] = ()
    # What the answer says beyond the counts, as a label and its text.
    details: tuple[tuple[str, str], ...] = ()

    @property
    def engines(self) -> int:
        """How many engines gave a verdict on the subject."""
        return self.malicious + self.suspicious + self.harmless + self.undetected


@dataclass(frozen=True)
class Reported:
    """VirusTotal has a report on the subject."""

    report: Report


@dataclass(frozen=True)
class Unknown:
    """VirusTotal has no report on the subject."""


@dataclass(frozen=True)
class Failed:
    """The lookup didn't give a report. The message says why, for the log and for the person."""

    message: str


@dataclass(frozen=True)
class Limited:
    """VirusTotal's daily quota is used up. Nothing is asked until it resets, at ``until``."""

    until: datetime


@dataclass(frozen=True)
class Throttled:
    """VirusTotal asked for fewer requests for a minute. Nothing is asked until ``until``."""

    until: datetime


Answer = Reported | Unknown | Failed | Limited | Throttled


def judge(report: Report | None) -> Judgement:
    """Whether VirusTotal reported the subject as malicious. One engine's flag can be a false
    positive, which is why the counts are shown beside the judgement and not in place of it."""
    if report is None:
        return "unknown"
    if report.malicious > 0:
        return "malicious"
    if report.suspicious > 0:
        return "suspicious"
    return "clean"


def _object(value: object) -> dict[str, object] | None:
    return cast("dict[str, object]", value) if isinstance(value, dict) else None


def _whole(value: object, low: int, high: int) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        return None
    return value


def _text(value: object, limit: int) -> str | None:
    return audit.clean(value, limit) if isinstance(value, str) else None


def _categories(value: object) -> tuple[str, ...]:
    """The categories the engines gave, once each and in order. VirusTotal keeps them by engine."""
    mapping = _object(value)
    if mapping is None:
        return ()
    names = {text for item in mapping.values() if (text := _text(item, MAX_NAME))}
    return tuple(sorted(names)[:MAX_CATEGORIES])


def _details(kind: str, attributes: dict[str, object]) -> tuple[tuple[str, str], ...]:
    """What the answer says beyond the counts, for the kind of subject looked up. A value that
    isn't there is left out rather than guessed."""
    pairs: tuple[tuple[str, str | None], ...]
    if kind == "domain":
        pairs = (("Registrar", _text(attributes.get("registrar"), MAX_NAME)),)
    elif kind == "url":
        times = _whole(attributes.get("times_submitted"), 0, MAX_COUNT)
        pairs = (
            ("Title", _text(attributes.get("title"), MAX_TITLE)),
            ("Final address", _text(attributes.get("last_final_url"), MAX_URL)),
            ("Times submitted", None if times is None else str(times)),
        )
    else:
        asn = _whole(attributes.get("asn"), 0, MAX_ASN)
        pairs = (
            ("Owner", _text(attributes.get("as_owner"), MAX_NAME)),
            ("Country", _text(attributes.get("country"), MAX_COUNTRY)),
            ("Network", None if asn is None else f"AS{asn}"),
        )
    return tuple((label, value) for label, value in pairs if value)


def parse(body: object, now: datetime, kind: str = "ip") -> Report | None:
    """The report in VirusTotal's answer, or None if the answer doesn't hold the counts of one. The
    time it was analysed is taken as the answer gives it, and ``now`` if it doesn't."""
    root = _object(body)
    data = _object(root.get("data")) if root is not None else None
    attributes = _object(data.get("attributes")) if data is not None else None
    stats = _object(attributes.get("last_analysis_stats")) if attributes is not None else None
    if attributes is None or stats is None:
        return None
    malicious = _whole(stats.get("malicious"), 0, MAX_COUNT)
    suspicious = _whole(stats.get("suspicious"), 0, MAX_COUNT)
    harmless = _whole(stats.get("harmless"), 0, MAX_COUNT)
    undetected = _whole(stats.get("undetected"), 0, MAX_COUNT)
    if malicious is None or suspicious is None or harmless is None or undetected is None:
        return None
    stamp = _whole(attributes.get("last_analysis_date"), 0, MAX_EPOCH)
    return Report(
        malicious=malicious,
        suspicious=suspicious,
        harmless=harmless,
        undetected=undetected,
        reputation=_whole(attributes.get("reputation"), -MAX_COUNT, MAX_COUNT) or 0,
        analysed_at=datetime.fromtimestamp(stamp, UTC) if stamp is not None else now,
        country=_text(attributes.get("country"), MAX_COUNTRY),
        owner=_text(attributes.get("as_owner"), MAX_NAME),
        asn=_whole(attributes.get("asn"), 0, MAX_ASN),
        categories=_categories(attributes.get("categories")),
        details=_details(kind, attributes),
    )


def url_id(url: str) -> str:
    """The identifier VirusTotal gives a web address: the SHA-256 of the address. It keeps the
    address out of the request path, which the API log holds."""
    return subjects.url_key(url)


def _path(subject: Subject) -> str:
    if subject.kind == "ip":
        return f"/api/v3/ip_addresses/{subject.host}"
    if subject.kind == "domain":
        return f"/api/v3/domains/{subject.host}"
    return f"/api/v3/urls/{url_id(subject.text)}"


def link_for(subject: Subject) -> str:
    """The page on VirusTotal's website about the subject, for reading it in full."""
    if subject.kind == "ip":
        return f"{SITE}/gui/ip-address/{subject.host}"
    if subject.kind == "domain":
        return f"{SITE}/gui/domain/{subject.host}"
    return f"{SITE}/gui/url/{url_id(subject.text)}"


def next_reset(at: datetime) -> datetime:
    """When the daily quota that ``at`` falls in resets: midnight UTC, the first one after it."""
    return datetime.combine(at.astimezone(UTC).date() + timedelta(days=1), time(), tzinfo=UTC)


# What VirusTotal says when it refuses a key, in words for the person who has to act on it.
_REFUSED = {
    401: "VirusTotal didn't accept the key. Copy it again from your VirusTotal account.",
    403: "VirusTotal refused this request with the key. Check the key's access level.",
}


def _error_code(reply: Reply) -> str | None:
    """The name VirusTotal gives the error in its answer, such as ``QuotaExceededError``."""
    root = _object(reply.json())
    error = _object(root.get("error")) if root is not None else None
    code = error.get("code") if error is not None else None
    return code if isinstance(code, str) else None


def _limit(reply: Reply, now: datetime) -> Limited | Throttled:
    """What a 429 says. ``QuotaExceededError`` is a quota used up, and the daily quotas reset at
    00:00 UTC. The page doesn't say which quota it is, so it is taken as the daily one, and nothing
    is sent until that reset. Any other 429, ``TooManyRequestsError`` included, is a short wait."""
    if _error_code(reply) == "QuotaExceededError":
        return Limited(until=next_reset(now))
    return Throttled(until=now + THROTTLE)


async def look_up(client: ApiClient, target: Target, subject: Subject, now: datetime) -> Answer:
    """Asks for the report on one subject. Raises ``CallFailed`` if no answer came at all."""
    reply = await client.request(
        "GET", _path(subject), headers={KEY_HEADER: target.secrets["api_key"]}
    )
    if reply.status == 404:
        return Unknown()
    if reply.status == 429:
        return _limit(reply, now)
    if not reply.ok:
        return Failed(_REFUSED.get(reply.status, f"VirusTotal answered HTTP {reply.status}."))
    report = parse(reply.json(), now, subject.kind)
    if report is None:
        return Failed("VirusTotal's answer didn't hold the counts of a report.")
    return Reported(report)


async def ask(
    target: Target,
    record: Recorder,
    policy: AddressPolicy,
    subject: Subject,
    now: datetime,
) -> Answer:
    """Asks VirusTotal about one subject over a logged connection. A request that gets no answer
    is a failure, with the reason in words."""
    try:
        async with ApiClient(target, record, policy) as client:
            return await look_up(client, target, subject, now)
    except CallFailed as failure:
        return Failed(str(failure))
