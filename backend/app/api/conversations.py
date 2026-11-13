"""What was sent, and between whom, as the incident page is told it.

The conversations are put together in app/incidents/conversations.py."""

from ipaddress import ip_address
from typing import Literal

from pydantic import AwareDatetime, BaseModel
from sqlalchemy.orm import Session

from app.api.dashboard import SEVERITY_NAMES, SeverityName
from app.events.event import Severity
from app.incidents import conversations, names, purpose, rules
from app.intel import greynoise, otx, overrides, virustotal
from app.intel import store as intel_store
from app.models import IntelOverride, IntelSubject, utcnow


class OtxOut(BaseModel):
    """What AlienVault OTX's community threat reports (pulses) say of an address."""

    judgement: Literal["malicious", "suspicious", "clean", "unknown"]
    # How many pulses name the address, and how many of them also name malware, an adversary or an
    # attack technique.
    pulses: int
    naming: int
    # The malware and adversaries those pulses name, if they do.
    names: str | None
    # Its page on OTX's website, for reading the pulses in full.
    link: str


class GreyNoiseOut(BaseModel):
    """What GreyNoise says of an address: whether it is one of the many that scan every address on
    the internet, or a common business service."""

    judgement: Literal["malicious", "suspicious", "clean", "unknown"]
    # What GreyNoise classifies the scanner as (benign, malicious or unknown), if it was seen.
    classification: str | None
    # The business service it is, if it is one.
    business: str | None
    # The actor and the tags GreyNoise attaches to it, which only a subscription's answer holds.
    actor: str | None
    tags: str | None
    # Its page on GreyNoise's Visualizer.
    link: str


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
    # What AlienVault OTX said of it, if that is connected and has something to say.
    otx: OtxOut | None = None
    # What GreyNoise said of it, if that is connected and has something to say.
    greynoise: GreyNoiseOut | None = None


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
    pulses = {
        row.subject: _otx(row)
        for row in intel_store.reports_for(db, otx.PROVIDER, addresses)
        if row.judgement != "unknown"
    }
    noise = {
        row.subject: _greynoise(row)
        for row in intel_store.reports_for(db, greynoise.PROVIDER, addresses)
        if row.judgement != "unknown"
    }
    rulings = overrides.for_addresses(db, addresses)
    return {
        address: _reputation(
            reports.get(address), rulings.get(address), pulses.get(address), noise.get(address)
        )
        for address in reports.keys() | rulings.keys() | pulses.keys() | noise.keys()
    }


def _otx(row: IntelSubject) -> OtxOut:
    """What OTX's pulses say of one address, with what they name and where to read them."""
    said = {item["label"]: item["value"] for item in row.details}
    names = [said[label] for label in (otx.MALWARE, otx.ADVERSARY) if label in said]
    return OtxOut(
        judgement=row.judgement,  # type: ignore[arg-type]
        pulses=row.malicious + row.suspicious,
        naming=row.malicious,
        names="; ".join(names) or None,
        link=f"{otx.SITE}/indicator/ip/{row.subject}",
    )


def _greynoise(row: IntelSubject) -> GreyNoiseOut:
    """What GreyNoise says of one address, with where to read more."""
    said = {item["label"]: item["value"] for item in row.details}
    business = said.get(greynoise.BUSINESS)
    return GreyNoiseOut(
        judgement=row.judgement,  # type: ignore[arg-type]
        classification=said.get(greynoise.CLASSIFICATION),
        business=business,
        actor=said.get(greynoise.ACTOR),
        tags=said.get(greynoise.TAGS),
        link=greynoise.link_of(row.subject, business=business is not None),
    )


def _reputation(
    row: IntelSubject | None,
    ruling: IntelOverride | None,
    pulses: OtxOut | None = None,
    noise: GreyNoiseOut | None = None,
) -> ReputationOut:
    """What is known against one address: the service's report, if it gave one, the pulses OTX
    names it in, what GreyNoise says of it, and the ruling."""
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
        otx=pulses,
        greynoise=noise,
    )


def _name_from(end: conversations.End, name: str | None) -> Literal["program", "dns"] | None:
    """Where a name came from: what a program told, or else a reverse lookup."""
    if not name:
        return None
    return "program" if end.name else "dns"


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
        name_from=_name_from(end, name),
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
