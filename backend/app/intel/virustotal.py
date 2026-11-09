"""VirusTotal's report on one internet address, read from its API version 3.

The key goes in the ``x-apikey`` header. An address with no report answers 404, and a key that
VirusTotal refuses answers 401 or 403, which a lookup reports as a failure.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from ipaddress import IPv4Address, IPv6Address
from typing import cast

from app import audit
from app.integrations.client import ApiClient, Target

PROVIDER = "virustotal"
API_PATH = "/api/v3/ip_addresses/{address}"
KEY_HEADER = "x-apikey"
# How big the counts and the score can be, and the latest time an analysis can be dated to.
MAX_COUNT = 1_000_000
MAX_ASN = 4_294_967_295
MAX_EPOCH = 4_102_444_800
MAX_NAME = 120
MAX_COUNTRY = 8


@dataclass(frozen=True)
class Report:
    """What VirusTotal said of one address."""

    malicious: int
    suspicious: int
    harmless: int
    undetected: int
    reputation: int
    analysed_at: datetime
    country: str | None
    owner: str | None
    asn: int | None

    @property
    def engines(self) -> int:
        """How many engines gave a verdict on the address."""
        return self.malicious + self.suspicious + self.harmless + self.undetected


@dataclass(frozen=True)
class Reported:
    """VirusTotal has a report on the address."""

    report: Report


@dataclass(frozen=True)
class Unknown:
    """VirusTotal has no report on the address."""


@dataclass(frozen=True)
class Failed:
    """The lookup didn't give a report. The message says why, for the log."""

    message: str


Answer = Reported | Unknown | Failed


def _object(value: object) -> dict[str, object] | None:
    return cast("dict[str, object]", value) if isinstance(value, dict) else None


def _whole(value: object, low: int, high: int) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        return None
    return value


def _text(value: object, limit: int) -> str | None:
    return audit.clean(value, limit) if isinstance(value, str) else None


def parse(body: object, now: datetime) -> Report | None:
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
    )


async def look_up(
    client: ApiClient,
    target: Target,
    address: IPv4Address | IPv6Address,
    now: datetime,
) -> Answer:
    """Asks for the report on one address. Raises ``CallFailed`` if no answer came at all."""
    reply = await client.request(
        "GET",
        API_PATH.format(address=address),
        headers={KEY_HEADER: target.secrets["api_key"]},
    )
    if reply.status == 404:
        return Unknown()
    if not reply.ok:
        return Failed(f"VirusTotal answered HTTP {reply.status}.")
    report = parse(reply.json(), now)
    if report is None:
        return Failed("VirusTotal's answer didn't hold the counts of a report.")
    return Reported(report)
