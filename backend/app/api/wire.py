"""What was said on the wire, as the incident page is told it.

It is put together in app/incidents/wire.py from what Suricata read of the connections."""

from pydantic import BaseModel

from app.incidents import wire


class CertificateOut(BaseModel):
    """A certificate a server showed, who it is for, who vouched for it and what asked for it."""

    subject: str | None
    issuer: str | None
    serial: str | None
    fingerprint: str | None
    # How the connection was encrypted, such as ``TLS 1.2``.
    version: str | None
    # The name the client asked for.
    sni: str | None
    not_before: str | None
    not_after: str | None
    self_signed: bool
    # Whether it had run out when it was seen, or None where its dates are not known.
    expired: bool | None
    ja3: str | None
    ja3s: str | None
    server: str | None
    alerts: int


class HeaderOut(BaseModel):
    name: str
    value: str
    # Whether the value is held back because it can carry a password or a key.
    hidden: bool


class RequestOut(BaseModel):
    """A web request that went without encryption."""

    method: str | None
    host: str | None
    url: str | None
    user_agent: str | None
    referer: str | None
    content_type: str | None
    status: int | None
    size: int | None
    request_headers: list[HeaderOut]
    response_headers: list[HeaderOut]
    server: str | None
    alerts: int


class LookupOut(BaseModel):
    """A name that was looked up, and what came back."""

    name: str
    type: str | None
    rcode: str | None
    answers: list[str]
    alerts: int


class BannerOut(BaseModel):
    """What the two ends of an ssh connection said they run."""

    client: str | None
    server_software: str | None
    server: str | None
    alerts: int


class DumpOut(BaseModel):
    offset: str
    hex: str
    text: str


class WireOut(BaseModel):
    """What stands out on the wire of an incident, and the details, where there are any."""

    certificates: list[CertificateOut]
    requests: list[RequestOut]
    lookups: list[LookupOut]
    banners: list[BannerOut]
    payload: str | None
    dump: list[DumpOut]
    notes: list[str]


def _headers(items: list[list[str]]) -> list[HeaderOut]:
    return [HeaderOut(name=name, value=value, hidden=value == "(hidden)") for name, value in items]


def out(found: wire.Wire) -> WireOut | None:
    """The wire as the page is told it, or nothing where nothing was said on it."""
    if found.empty:
        return None
    return WireOut(
        certificates=[
            CertificateOut(
                subject=each.certificate.get("subject"),
                issuer=each.certificate.get("issuer"),
                serial=each.certificate.get("serial"),
                fingerprint=each.certificate.get("fingerprint"),
                version=each.certificate.get("version"),
                sni=each.certificate.get("sni"),
                not_before=each.certificate.get("not_before"),
                not_after=each.certificate.get("not_after"),
                self_signed=each.certificate.get("self_signed", False),
                expired=each.expired,
                ja3=each.certificate.get("ja3"),
                ja3s=each.certificate.get("ja3s"),
                server=each.server,
                alerts=each.alerts,
            )
            for each in found.certificates
        ],
        requests=[
            RequestOut(
                method=each.request.get("method"),
                host=each.request.get("host"),
                url=each.request.get("url"),
                user_agent=each.request.get("user_agent"),
                referer=each.request.get("referer"),
                content_type=each.request.get("content_type"),
                status=each.request.get("status"),
                size=each.request.get("size"),
                request_headers=_headers(each.request.get("request_headers", [])),
                response_headers=_headers(each.request.get("response_headers", [])),
                server=each.server,
                alerts=each.alerts,
            )
            for each in found.requests
        ],
        lookups=[
            LookupOut(
                name=each.lookup["name"],
                type=each.lookup.get("type"),
                rcode=each.lookup.get("rcode"),
                answers=each.lookup.get("answers", []),
                alerts=each.alerts,
            )
            for each in found.lookups
        ],
        banners=[
            BannerOut(
                client=each.banner.get("client"),
                server_software=each.banner.get("server"),
                server=each.server,
                alerts=each.alerts,
            )
            for each in found.banners
        ],
        payload=found.payload or None,
        dump=[DumpOut(offset=row[0], hex=row[1], text=row[2]) for row in found.dump],
        notes=found.notes,
    )
