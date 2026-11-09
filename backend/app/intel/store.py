"""What is kept of the lookups made, and the reports they brought back."""

from collections.abc import Iterable
from datetime import datetime, timedelta
from ipaddress import IPv4Address, IPv6Address

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.intel import virustotal
from app.models import IntelLookup, IntelReport

type Address = IPv4Address | IPv6Address

# How long a lookup is kept: long enough to count a month's allowance over, with some to spare.
KEEP = timedelta(days=40)

PENDING = "pending"
REPORTED = "reported"
UNKNOWN = "unknown"
FAILED = "failed"

# What a new report changes, when one for the same address is already kept.
_REFRESHED = (
    "analysed_at",
    "malicious",
    "suspicious",
    "harmless",
    "undetected",
    "reputation",
    "country",
    "owner",
    "asn",
)


def record(db: Session, provider: str, address: Address, now: datetime) -> int:
    """Keeps that a request is about to be made, before it is, so that one that fails or is cut
    short still counts toward the allowance. Returns the lookup's id."""
    row = IntelLookup(provider=provider, address=address, requested_at=now, outcome=PENDING)
    db.add(row)
    db.flush()
    return row.id


def save_report(db: Session, provider: str, address: Address, report: virustotal.Report) -> None:
    """Keeps the report of an address, replacing the one kept for it before."""
    values: dict[str, object] = {
        "provider": provider,
        "address": address,
        "analysed_at": report.analysed_at,
        "malicious": report.malicious,
        "suspicious": report.suspicious,
        "harmless": report.harmless,
        "undetected": report.undetected,
        "reputation": report.reputation,
        "country": report.country,
        "owner": report.owner,
        "asn": report.asn,
    }
    statement = insert(IntelReport).values(**values)
    db.execute(
        statement.on_conflict_do_update(
            constraint="uq_threat_intel_reports_address",
            set_={name: statement.excluded[name] for name in _REFRESHED},
        )
    )


def finish(db: Session, lookup_id: int, answer: virustotal.Answer) -> None:
    """Keeps what came of a lookup, and the report if there was one."""
    row = db.get(IntelLookup, lookup_id)
    if row is None:
        return
    if isinstance(answer, virustotal.Reported):
        row.outcome = REPORTED
        save_report(db, row.provider, row.address, answer.report)
    elif isinstance(answer, virustotal.Unknown):
        row.outcome = UNKNOWN
    else:
        row.outcome = FAILED


def report_for(db: Session, provider: str, address: Address) -> IntelReport | None:
    """The report kept for an address, if there is one."""
    return db.scalar(
        select(IntelReport).where(IntelReport.provider == provider, IntelReport.address == address)
    )


def reports_for(db: Session, provider: str, addresses: Iterable[Address]) -> list[IntelReport]:
    """The reports kept for some addresses, in no particular order."""
    found = list(addresses)
    if not found:
        return []
    return list(
        db.scalars(
            select(IntelReport).where(
                IntelReport.provider == provider, IntelReport.address.in_(found)
            )
        )
    )


def prune(db: Session, provider: str, now: datetime) -> None:
    """Forgets the lookups that are too old to count toward any allowance."""
    db.execute(
        delete(IntelLookup).where(
            IntelLookup.provider == provider, IntelLookup.requested_at < now - KEEP
        )
    )
