"""What the National Vulnerability Database says of one CVE, read from its CVE API 2.0.

NVD records every published CVE and adds what the CVE list does not say: a CVSS score and rating,
the weaknesses behind it (CWE) and, from CISA, whether the CVE is in the Known Exploited
Vulnerabilities catalog, which says someone has been seen exploiting it. A CVE published a day ago
may have no score yet, and one NVD has not received has no record at all.

One request asks about one CVE (``cveIds``). The API key goes in the ``apiKey`` header and is
optional: without one NVD allows 5 requests in a rolling 30 seconds, with one 50. An error says
why in a response header named ``message``, which is read for the person's sake. The answer is one
of a record, none, a failure or a request to wait.

NVD asks that a service that shows its data says so (``NOTICE``).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Final, Literal

from app import audit
from app.integrations.client import ApiClient, CallFailed, Recorder, Reply, Target
from app.integrations.netguard import AddressPolicy
from app.integrations.probes import as_array, as_object

PROVIDER = "nvd"
KEY_HEADER = "apiKey"
PATH = "/rest/json/cves/2.0"
SITE = "https://nvd.nist.gov/vuln/detail"
# What NVD asks a service that uses its data to say, as its Start Here page words it.
NOTICE = "This product uses data from the NVD API but is not endorsed or certified by the NVD."
# NVD's firewall counts a rolling 30 seconds. A 403 or 429 means the limit was reached or the key
# was refused, and the answer says no more than that, so lookups wait this long before trying again.
THROTTLE = timedelta(minutes=2)

type Access = Literal["key", "none"]
KEY: Access = "key"
NONE: Access = "none"

RATINGS: Final = ("NONE", "LOW", "MEDIUM", "HIGH", "CRITICAL")
MAX_DESCRIPTION = 2000
MAX_WEAKNESSES = 10
MAX_MESSAGE = 120
MAX_ACTION = 600
MAX_NAME = 200


@dataclass(frozen=True)
class Record:
    """What NVD says of one CVE."""

    cve_id: str
    status: str | None = None
    published_at: datetime | None = None
    modified_at: datetime | None = None
    cvss_version: str | None = None
    score: float | None = None
    severity: str | None = None
    vector: str | None = None
    description: str | None = None
    weaknesses: tuple[str, ...] = ()
    exploited: bool = False
    exploited_on: date | None = None
    action_due: date | None = None
    required_action: str | None = None
    kev_name: str | None = None


@dataclass(frozen=True)
class Found:
    """NVD has a record of the CVE."""

    record: Record


@dataclass(frozen=True)
class Unknown:
    """NVD has no record of the CVE, which is so for one it has not received yet."""


@dataclass(frozen=True)
class Failed:
    """The lookup didn't give a record. The message says why."""

    message: str


@dataclass(frozen=True)
class Throttled:
    """NVD turned the request away. Nothing is asked until ``until``."""

    until: datetime


type Answer = Found | Unknown | Failed | Throttled


def access_of(options: Mapping[str, str | int]) -> Access:
    """How the connection asks: with a key, unless the settings say it is asked without."""
    return NONE if options.get("access") == NONE else KEY


def link_of(cve_id: str) -> str:
    """The page about a CVE on NVD's website."""
    return f"{SITE}/{cve_id}"


def _text(value: object, limit: int) -> str | None:
    return audit.clean(value, limit) if isinstance(value, str) else None


def _when(value: object) -> datetime | None:
    """A time NVD gives, which is ISO 8601 with no offset because it is in UTC."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _day(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _rating(score: float, version: float) -> str:
    """The rating a score stands for, for a record that gives the score without its rating. CVSS 2
    has no critical."""
    if score <= 0:
        return "NONE"
    if score < 4:
        return "LOW"
    if score < 7:
        return "MEDIUM"
    return "CRITICAL" if score >= 9 and version >= 3 else "HIGH"


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _metric(entry: object) -> tuple[tuple[float, bool], str, float, str, str | None] | None:
    """One CVSS entry as (how it ranks, version, score, rating, vector), or None if it isn't one."""
    metric = as_object(entry)
    data = as_object(metric.get("cvssData")) if metric else None
    if metric is None or data is None:
        return None
    version = _text(data.get("version"), 4)
    score = _number(data.get("baseScore"))
    if version is None or score is None or not 0 <= score <= 10:
        return None
    try:
        number = float(version)
    except ValueError:
        return None
    # CVSS 3 and 4 give the rating with the data, and CVSS 2 beside it.
    said = data.get("baseSeverity") or metric.get("baseSeverity")
    rating = said.upper() if isinstance(said, str) and said.upper() in RATINGS else None
    return (
        (number, metric.get("type") == "Primary"),
        version,
        score,
        rating or _rating(score, number),
        _text(data.get("vectorString"), 200),
    )


def _cvss(metrics: object) -> tuple[str, float, str, str | None] | None:
    """The newest CVSS score the record has, the NVD's own where there are two of a version."""
    members = as_object(metrics) or {}
    ranked = [
        found
        for key, entries in members.items()
        if key.startswith("cvssMetric")
        for entry in as_array(entries) or []
        if (found := _metric(entry)) is not None
    ]
    if not ranked:
        return None
    _, version, score, rating, vector = max(ranked, key=lambda found: found[0])
    return version, score, rating, vector


def _description(value: object) -> str | None:
    for item in as_array(value) or []:
        entry = as_object(item)
        if entry and entry.get("lang") == "en":
            return _text(entry.get("value"), MAX_DESCRIPTION)
    return None


def _weaknesses(value: object) -> tuple[str, ...]:
    found: dict[str, None] = {}
    for item in as_array(value) or []:
        entry = as_object(item)
        described = as_array(entry.get("description")) if entry else None
        for each in described or []:
            named = as_object(each)
            weakness = _text(named.get("value"), 24) if named else None
            if weakness and weakness.startswith(("CWE-", "NVD-CWE-")):
                found[weakness] = None
    return tuple(found)[:MAX_WEAKNESSES]


def _record(cve: dict[str, object], cve_id: str) -> Record:
    cvss = _cvss(cve.get("metrics"))
    added = _day(cve.get("cisaExploitAdd"))
    return Record(
        cve_id=cve_id,
        status=_text(cve.get("vulnStatus"), 40),
        published_at=_when(cve.get("published")),
        modified_at=_when(cve.get("lastModified")),
        cvss_version=cvss[0] if cvss else None,
        score=cvss[1] if cvss else None,
        severity=cvss[2] if cvss else None,
        vector=cvss[3] if cvss else None,
        description=_description(cve.get("descriptions")),
        weaknesses=_weaknesses(cve.get("weaknesses")),
        # CISA's fields are there only for a CVE in its catalog.
        exploited=added is not None,
        exploited_on=added,
        action_due=_day(cve.get("cisaActionDue")),
        required_action=_text(cve.get("cisaRequiredAction"), MAX_ACTION),
        kev_name=_text(cve.get("cisaVulnerabilityName"), MAX_NAME),
    )


def parse(body: object, cve_id: str) -> Answer:
    """What a CVE API answer says of the CVE asked about: its record, none if the answer lists no
    CVE, or a failure if it isn't an answer of that kind."""
    root = as_object(body)
    listed = as_array(root.get("vulnerabilities")) if root else None
    if listed is None:
        return Failed("NVD's answer didn't hold a list of CVEs.")
    for item in listed:
        entry = as_object(item)
        cve = as_object(entry.get("cve")) if entry else None
        if cve is not None and str(cve.get("id", "")).upper() == cve_id:
            return Found(_record(cve, cve_id))
    return Unknown()


def _said(reply: Reply) -> str:
    """What NVD says of a refusal in its ``message`` header, as text that is safe to show."""
    return audit.clean(reply.headers.get("message"), MAX_MESSAGE) or ""


def answer_of(reply: Reply, cve_id: str, now: datetime) -> Answer:
    """What a reply from NVD says of the CVE asked about."""
    if reply.status in (403, 429, 503):
        return Throttled(until=now + THROTTLE)
    if reply.status == 404 and "apikey" not in _said(reply).lower():
        return Unknown()
    if not reply.ok:
        said = _said(reply)
        return Failed(f"NVD answered HTTP {reply.status}{': ' + said if said else '.'}")
    return parse(reply.json(), cve_id)


async def look_up(client: ApiClient, target: Target, cve_id: str, now: datetime) -> Answer:
    """Asks for the record of one CVE. Raises ``CallFailed`` if no answer came at all."""
    key = target.secrets.get("api_key") if access_of(target.options) == KEY else None
    reply = await client.request(
        "GET", PATH, query={"cveIds": cve_id}, headers={KEY_HEADER: key} if key else None
    )
    return answer_of(reply, cve_id, now)


async def ask(
    target: Target, record: Recorder, policy: AddressPolicy, cve_id: str, now: datetime
) -> Answer:
    """Asks NVD about one CVE over a logged connection. A request that gets no answer is a failure,
    with the reason in words."""
    try:
        async with ApiClient(target, record, policy) as client:
            return await look_up(client, target, cve_id, now)
    except CallFailed as failure:
        return Failed(str(failure))
