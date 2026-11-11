"""What was sent, and between whom, as the incident page is told it.

The conversations are put together in app/incidents/conversations.py."""

from ipaddress import ip_address
from typing import Literal

from pydantic import AwareDatetime, BaseModel
from sqlalchemy.orm import Session

from app.api.dashboard import SEVERITY_NAMES, SeverityName
from app.events.event import Severity
from app.incidents import conversations, names, purpose, rules
from app.intel import overrides, virustotal
from app.intel import store as intel_store
from app.models import IntelOverride, IntelSubject, utcnow


class ReputationOut(BaseModel):
    """What the threat-intelligence service said of an address that was asked about."""

    # What it comes to: the owner's ruling where there is one, else what the service made of it.
    judgement: Literal["malicious", "suspicious", "clean", "unknown"]
    # What the service made of it, which a ruling does not change.
    reported: Literal["malicious", "suspicious", "clean", "unknown"]
    malicious: int
    suspicious: int
    # How many engines gave a view at all.
    engines: int
    owner: str | None
    country: str | None
    # What the owner of the network ruled of the address, and why, if they did.
    ruling: Literal["safe", "suspicious"] | None
    ruling_note: str | None


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
    # Where the name came from: a program that saw it, or the address's reverse lookup (DNS).
    name_from: Literal["program", "dns"] | None


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
    # What the traffic was for, in a few plain words, where that can be told.
    purpose: str | None


class ConversationsOut(BaseModel):
    items: list[ConversationOut]
    # How many there were, which is more than ``items`` where it is cut to fit.
    total: int


def _reputations(db: Session, found: conversations.Conversations) -> dict[str, ReputationOut]:
    """What VirusTotal said of each address of the conversations that it was asked about, and what
    the owner of the network ruled of each, which stands over it."""
    addresses = {
        ip_address(end.address)
        for each in found.items
        for end in (each.client, each.server)
        if ip_address(end.address).is_global
    }
    reports = {
        row.subject: row for row in intel_store.reports_for(db, virustotal.PROVIDER, addresses)
    }
    rulings = overrides.for_addresses(db, addresses)
    return {
        address: _reputation(reports.get(address), rulings.get(address))
        for address in reports.keys() | rulings.keys()
    }


def _reputation(row: IntelSubject | None, ruling: IntelOverride | None) -> ReputationOut:
    """What is known against one address: the service's report, if it gave one, and the ruling."""
    reported = row.judgement if row else "unknown"
    verdict = ruling.verdict if ruling else None
    return ReputationOut(
        judgement=overrides.effective(reported, verdict),  # type: ignore[arg-type]
        reported=reported,  # type: ignore[arg-type]
        malicious=row.malicious if row else 0,
        suspicious=row.suspicious if row else 0,
        engines=row.malicious + row.suspicious + row.harmless + row.undetected if row else 0,
        owner=row.owner if row else None,
        country=row.country if row else None,
        ruling=verdict,  # type: ignore[arg-type]
        ruling_note=ruling.note if ruling else None,
    )


def _end(
    end: conversations.End, reputations: dict[str, ReputationOut], dns: dict[str, str]
) -> EndOut:
    name = end.name or dns.get(end.address)
    return EndOut(
        address=end.address,
        name=name,
        port=end.port,
        service=end.service,
        country=end.country,
        location=end.location,  # type: ignore[arg-type]
        blacklisted=end.blacklisted,
        reputation=reputations.get(end.address),
        name_from=("program" if end.name else "dns") if name else None,
    )


def out(db: Session, found: conversations.Conversations) -> ConversationsOut | None:
    """The conversations as they are told, or nothing where there were none."""
    if not found.items:
        return None
    reputations = _reputations(db, found)
    dns = names.lookup(
        db,
        {
            end.address
            for each in found.items
            for end in (each.client, each.server)
            if end.name is None
        },
        utcnow(),
    )
    return ConversationsOut(
        items=[
            ConversationOut(
                client=_end(each.client, reputations, dns),
                server=_end(each.server, reputations, dns),
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
                purpose=purpose.of(
                    app=each.app,
                    port=each.server.port,
                    protocol=each.protocol,
                    asked_for=each.names[0]["value"] if each.names else None,
                ),
            )
            for each in found.items
        ],
        total=found.total,
    )
