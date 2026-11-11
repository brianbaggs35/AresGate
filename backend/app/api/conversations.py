"""What was sent, and between whom, as the incident page is told it.

The conversations are put together in app/incidents/conversations.py."""

from ipaddress import ip_address
from typing import Literal

from pydantic import AwareDatetime, BaseModel
from sqlalchemy.orm import Session

from app.api.dashboard import SEVERITY_NAMES, SeverityName
from app.events.event import Severity
from app.incidents import conversations, rules
from app.intel import store as intel_store
from app.intel import virustotal


class ReputationOut(BaseModel):
    """What the threat-intelligence service said of an address that was asked about."""

    judgement: Literal["malicious", "suspicious", "clean", "unknown"]
    malicious: int
    suspicious: int
    # How many engines gave a view at all.
    engines: int
    owner: str | None
    country: str | None


class EndOut(BaseModel):
    """One end of a conversation."""

    address: str
    name: str | None
    port: int | None
    service: str | None
    country: str | None
    location: Literal["local", "remote"] | None
    blacklisted: bool
    reputation: ReputationOut | None


class AskedForOut(BaseModel):
    """What the traffic asked for: a host name, a name looked up, a site, an address."""

    kind: str
    value: str


class ProgramOut(BaseModel):
    source: str
    source_name: str


class ConversationOut(BaseModel):
    client: EndOut
    server: EndOut
    protocol: str | None
    app: str | None
    alerts: int
    kinds: int
    first_at: AwareDatetime
    last_at: AwareDatetime
    severity: SeverityName
    # The biggest flow a program counted, in what the client sent and got back, and how long the
    # longest took in seconds.
    bytes_out: int | None
    bytes_in: int | None
    duration: int | None
    names: list[AskedForOut]
    programs: list[ProgramOut]


class ConversationsOut(BaseModel):
    items: list[ConversationOut]
    # How many there were, which is more than ``items`` where it is cut to fit.
    total: int


def _reputations(db: Session, found: conversations.Conversations) -> dict[str, ReputationOut]:
    """What VirusTotal said of each address of the conversations that it was asked about."""
    addresses = {
        ip_address(end.address)
        for each in found.items
        for end in (each.client, each.server)
        if ip_address(end.address).is_global
    }
    return {
        row.subject: ReputationOut(
            judgement=row.judgement,  # type: ignore[arg-type]
            malicious=row.malicious,
            suspicious=row.suspicious,
            engines=row.malicious + row.suspicious + row.harmless + row.undetected,
            owner=row.owner,
            country=row.country,
        )
        for row in intel_store.reports_for(db, virustotal.PROVIDER, addresses)
    }


def _end(end: conversations.End, reputations: dict[str, ReputationOut]) -> EndOut:
    return EndOut(
        address=end.address,
        name=end.name,
        port=end.port,
        service=end.service,
        country=end.country,
        location=end.location,  # type: ignore[arg-type]
        blacklisted=end.blacklisted,
        reputation=reputations.get(end.address),
    )


def out(db: Session, found: conversations.Conversations) -> ConversationsOut | None:
    """The conversations as they are told, or nothing where there were none."""
    if not found.items:
        return None
    reputations = _reputations(db, found)
    return ConversationsOut(
        items=[
            ConversationOut(
                client=_end(each.client, reputations),
                server=_end(each.server, reputations),
                protocol=each.protocol,
                app=each.app,
                alerts=each.alerts,
                kinds=each.kinds,
                first_at=each.first_at,
                last_at=each.last_at,
                severity=SEVERITY_NAMES[Severity(each.severity)],
                bytes_out=each.bytes_out,
                bytes_in=each.bytes_in,
                duration=each.duration,
                names=[AskedForOut(kind=name["kind"], value=name["value"]) for name in each.names],
                programs=[
                    ProgramOut(source=source, source_name=rules.name_of(source))
                    for source in each.programs
                ],
            )
            for each in found.items
        ],
        total=found.total,
    )
