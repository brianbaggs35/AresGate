"""What was said on the wire, put together for an incident.

Suricata reads more of a connection than the alert says: the certificate a server showed, the web
request, the name that was looked up, the banners of an ssh login. Each alert keeps what it read
(``evidence.Wire``). Here the alerts of an incident are read for them: the same certificate or
request seen by many alerts is one, with how many alerts saw it, and a few plain words say what
stands out, which the page shows and the AI is told.

A self-signed certificate is the common one. It is what many cameras, doorbells and other home
devices show the service they talk to, so on its own it says little; what it says is worth the
words that put it next to who asked for it.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

from app.incidents import evidence, occurrences
from app.incidents.occurrences import Occurrence

# How many of each there is room for, and how many plain notes.
MAX_CERTIFICATES: Final = 6
MAX_REQUESTS: Final = 6
MAX_LOOKUPS: Final = 8
MAX_BANNERS: Final = 4
MAX_NOTES: Final = 5
# The ways of encrypting a connection that are out of date.
WEAK_VERSIONS: Final = frozenset({"SSLv2", "SSLv3", "TLS 1.0", "TLS 1.1"})


@dataclass(frozen=True)
class CertificateSeen:
    certificate: evidence.Certificate
    # Where it was shown from: the server's address and port.
    server: str | None
    alerts: int
    # Whether it had run out when it was seen, or None where its dates are not known.
    expired: bool | None


@dataclass(frozen=True)
class RequestSeen:
    request: evidence.Request
    server: str | None
    alerts: int


@dataclass(frozen=True)
class LookupSeen:
    lookup: evidence.Lookup
    alerts: int


@dataclass(frozen=True)
class BannerSeen:
    banner: evidence.Banner
    server: str | None
    alerts: int


@dataclass(frozen=True)
class Wire:
    """Everything said on the wire in an incident's alerts, and what stands out in it."""

    certificates: list[CertificateSeen]
    requests: list[RequestSeen]
    lookups: list[LookupSeen]
    banners: list[BannerSeen]
    # The first bytes of the packet that set an alert off, as a dump, and as text where it was
    # printable.
    dump: list[list[str]]
    payload: str
    notes: list[str]

    @property
    def empty(self) -> bool:
        return not (
            self.certificates
            or self.requests
            or self.lookups
            or self.banners
            or self.dump
            or self.payload
        )


def expired(not_after: str | None, now: datetime) -> bool | None:
    """Whether a certificate's last day had gone by, from the time Suricata writes it in (UTC)."""
    if not not_after:
        return None
    try:
        ends = datetime.fromisoformat(not_after)
    except ValueError:
        return None
    return ends.replace(tzinfo=ends.tzinfo or UTC) < now


def server_of(occurrence: Occurrence) -> str | None:
    signal = occurrence.first
    if signal.dst_address is None:
        return None
    return f"{signal.dst_address}:{signal.dst_port}" if signal.dst_port else str(signal.dst_address)


def called(certificate: evidence.Certificate) -> str:
    """What to call a certificate's server: the name asked for, or the certificate's own."""
    return certificate.get("sni") or certificate.get("subject") or "a server"


def notes_of(certificates: Sequence[CertificateSeen], requests: Sequence[RequestSeen]) -> list[str]:
    """What stands out, in a few plain words each."""
    notes: list[str] = []
    for seen in certificates:
        name = called(seen.certificate)
        if seen.certificate.get("self_signed"):
            notes.append(
                f"The certificate for {name} is self-signed: nobody else vouches for it. "
                "Cameras, doorbells and other home devices often show one to the service they "
                "talk to, so look at what asked for it before you worry."
            )
        if seen.expired:
            notes.append(
                f"The certificate for {name} ran out on {seen.certificate.get('not_after')}."
            )
        if (version := seen.certificate.get("version")) in WEAK_VERSIONS:
            notes.append(f"{name} was reached over {version}, which is out of date and weak.")
    for each in requests:
        headers = each.request.get("request_headers", [])
        if any(value == evidence.HIDDEN for _, value in headers):
            where = each.request.get("host") or each.server or "a server"
            notes.append(
                f"A login or key went to {where} as plain web traffic, where anyone on the path "
                "can read it. Its value is hidden here."
            )
    return list(dict.fromkeys(notes))[:MAX_NOTES]


def of(found: Sequence[Occurrence], now: datetime) -> Wire:
    """The wire of an incident's occurrences: what each alert read, folded into one of each, the
    most often seen first."""
    certificates: dict[tuple[str, ...], CertificateSeen] = {}
    requests: dict[tuple[str, ...], RequestSeen] = {}
    lookups: dict[tuple[str, ...], LookupSeen] = {}
    banners: dict[tuple[str, ...], BannerSeen] = {}
    dump: list[list[str]] = []
    payload = ""
    for occurrence in found:
        server = server_of(occurrence)
        for _, count, said in occurrences.reports(occurrence):
            if said is None:
                continue
            dump = dump or said.get("dump", [])
            payload = payload or said.get("payload", "")
            wire = said.get("wire")
            if wire is None:
                continue
            if certificate := wire.get("certificate"):
                key = tuple(
                    certificate.get(name, "") for name in ("subject", "issuer", "sni", "serial")
                )
                known = certificates.get(key)
                certificates[key] = CertificateSeen(
                    certificate,
                    server if known is None else known.server,
                    count + (known.alerts if known else 0),
                    expired(certificate.get("not_after"), now),
                )
            if request := wire.get("request"):
                key = (
                    request.get("method", ""),
                    request.get("host", ""),
                    request.get("url", ""),
                    str(request.get("status", "")),
                )
                known_request = requests.get(key)
                requests[key] = RequestSeen(
                    request,
                    server if known_request is None else known_request.server,
                    count + (known_request.alerts if known_request else 0),
                )
            if lookup := wire.get("lookup"):
                key = (lookup["name"], lookup.get("type", ""), lookup.get("rcode", ""))
                lookups[key] = LookupSeen(
                    lookup, count + (lookups[key].alerts if key in lookups else 0)
                )
            if banner := wire.get("ssh"):
                key = (banner.get("client", ""), banner.get("server", ""))
                banners[key] = BannerSeen(
                    banner,
                    server,
                    count + (banners[key].alerts if key in banners else 0),
                )
    seen_certificates = sorted(certificates.values(), key=lambda each: -each.alerts)
    seen_requests = sorted(requests.values(), key=lambda each: -each.alerts)
    return Wire(
        certificates=seen_certificates[:MAX_CERTIFICATES],
        requests=seen_requests[:MAX_REQUESTS],
        lookups=sorted(lookups.values(), key=lambda each: -each.alerts)[:MAX_LOOKUPS],
        banners=sorted(banners.values(), key=lambda each: -each.alerts)[:MAX_BANNERS],
        dump=dump,
        payload=payload,
        notes=notes_of(seen_certificates, seen_requests),
    )


def _certificate_line(seen: CertificateSeen) -> str:
    certificate = seen.certificate
    parts = [f"Certificate shown for {called(certificate)}"]
    if seen.server:
        parts[0] += f" by {seen.server}"
    if issuer := certificate.get("issuer"):
        parts.append("self-signed" if certificate.get("self_signed") else f"issued by {issuer}")
    if version := certificate.get("version"):
        parts.append(f"over {version}")
    if ends := certificate.get("not_after"):
        parts.append(f"{'ran out' if seen.expired else 'good until'} {ends}")
    parts.append(f"{seen.alerts} alerts")
    return "; ".join(parts)


def _request_line(seen: RequestSeen) -> str:
    request = seen.request
    target = f"{request.get('host', '')}{request.get('url', '')}" or (seen.server or "")
    line = f"Plain web request: {request.get('method', 'request')} {target}".rstrip()
    extras = [
        f"user agent {request['user_agent']}" if "user_agent" in request else "",
        f"answer {request['status']}" if "status" in request else "",
        request.get("content_type", ""),
    ]
    return "; ".join([line, *(each for each in extras if each), f"{seen.alerts} alerts"])


def prompt_lines(wire: Wire) -> list[str]:
    """What the AI is told of the wire, a line each, with what stands out. Nothing where there is
    nothing."""
    lines = [_certificate_line(each) for each in wire.certificates]
    lines += [_request_line(each) for each in wire.requests]
    for each in wire.lookups:
        answer = ", ".join(each.lookup.get("answers", [])) or each.lookup.get("rcode", "no answer")
        lines.append(f"Name looked up: {each.lookup['name']} -> {answer}; {each.alerts} alerts")
    for each in wire.banners:
        said = ", ".join(f"{who} {what}" for who, what in each.banner.items())
        lines.append(f"ssh banners: {said}")
    if wire.payload:
        lines.append(f"Start of the packet that set an alert off, as text: {wire.payload}")
    lines += [f"Note: {note}" for note in wire.notes]
    return lines
