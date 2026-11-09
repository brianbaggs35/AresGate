"""What is kept of the lookups made, and of the answers they brought back.

Every request AresGate makes is kept as a lookup, which is what the allowance is counted over. The
answer about each subject is kept once as well: a search or a background lookup of a subject that
was answered within ``FRESH`` is answered from what is kept, and VirusTotal isn't asked again.
"""

from collections.abc import Iterable
from datetime import datetime, timedelta
from ipaddress import IPv4Address, IPv6Address

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.intel import virustotal
from app.intel.subjects import Subject
from app.models import IntelLookup, IntelSubject

type Address = IPv4Address | IPv6Address
type Answered = virustotal.Reported | virustotal.Unknown

# How long a lookup is kept: long enough to count a month's allowance over, with some to spare.
KEEP = timedelta(days=40)
# How long the answer about a subject is taken as fresh, so the subject is not asked about again.
FRESH = timedelta(days=7)

PENDING = "pending"
REPORTED = "reported"
UNKNOWN = "unknown"
FAILED = "failed"
# A lookup VirusTotal held off: its daily quota is used up, or it asked for fewer requests.
LIMITED = "limited"
THROTTLED = "throttled"
# The kind of subject an internet address is.
IP = "ip"

# The columns a newer answer about the same subject replaces.
_REPLACED = (
    "checked_at",
    "outcome",
    "analysed_at",
    "malicious",
    "suspicious",
    "harmless",
    "undetected",
    "reputation",
    "country",
    "owner",
    "asn",
    "categories",
    "details",
)


def record(
    db: Session,
    provider: str,
    address: Address | None,
    now: datetime,
    *,
    kind: str = IP,
    subject: str | None = None,
) -> int:
    """Keeps that a request is about to be made, before it is, so that one that fails or is cut
    short still counts toward the allowance. Returns the lookup's id."""
    row = IntelLookup(
        provider=provider,
        address=address,
        kind=kind,
        subject=subject,
        requested_at=now,
        outcome=PENDING,
    )
    db.add(row)
    db.flush()
    return row.id


def finish(
    db: Session, lookup_id: int, subject: Subject, answer: virustotal.Answer, now: datetime
) -> None:
    """Keeps what came of a lookup. An answer, whether a report or none, is kept for its subject as
    well, so the subject isn't asked about again while the answer is fresh. A failure is kept on the
    lookup only, so it is tried again. A limit is kept on the lookup only too: it says nothing about
    the subject, and the lookup is what the pause is read from."""
    row = db.get(IntelLookup, lookup_id)
    if row is None:
        return
    if isinstance(answer, virustotal.Limited):
        row.outcome = LIMITED
    elif isinstance(answer, virustotal.Throttled):
        row.outcome = THROTTLED
    elif isinstance(answer, virustotal.Failed):
        row.outcome = FAILED
    else:
        row.outcome = REPORTED if isinstance(answer, virustotal.Reported) else UNKNOWN
        keep(db, row.provider, subject, answer, now)


def keep(db: Session, provider: str, subject: Subject, answer: Answered, now: datetime) -> None:
    """Keeps the answer about a subject, replacing the one kept before, which was asked about before
    ``now``. There is one row per subject, so a subject is never kept twice."""
    values = _values(provider, subject, answer, now)
    statement = insert(IntelSubject).values(**values)
    db.execute(
        statement.on_conflict_do_update(
            constraint="uq_threat_intel_subjects_subject",
            set_={name: statement.excluded[name] for name in _REPLACED},
        )
    )


def _values(provider: str, subject: Subject, answer: Answered, now: datetime) -> dict[str, object]:
    """The columns of a subject's answer. A subject with no report keeps no counts."""
    values: dict[str, object] = {
        "provider": provider,
        "kind": subject.kind,
        "subject": subject.key,
        "checked_at": now,
        "outcome": UNKNOWN,
        "analysed_at": None,
        "malicious": 0,
        "suspicious": 0,
        "harmless": 0,
        "undetected": 0,
        "reputation": 0,
        "country": None,
        "owner": None,
        "asn": None,
        "categories": [],
        "details": [],
    }
    if isinstance(answer, virustotal.Reported):
        report = answer.report
        values.update(
            outcome=REPORTED,
            analysed_at=report.analysed_at,
            malicious=report.malicious,
            suspicious=report.suspicious,
            harmless=report.harmless,
            undetected=report.undetected,
            reputation=report.reputation,
            country=report.country,
            owner=report.owner,
            asn=report.asn,
            categories=list(report.categories),
            details=[{"label": label, "value": value} for label, value in report.details],
        )
    return values


def cached(db: Session, provider: str, subject: Subject, now: datetime) -> IntelSubject | None:
    """The answer kept for a subject, if the subject was asked about within ``FRESH`` of ``now``."""
    return db.scalar(
        select(IntelSubject).where(
            IntelSubject.provider == provider,
            IntelSubject.kind == subject.kind,
            IntelSubject.subject == subject.key,
            IntelSubject.checked_at > now - FRESH,
        )
    )


def answer_of(kept: IntelSubject) -> Answered:
    """The answer kept for a subject, as it was given: its report, or that there was none."""
    if kept.outcome != REPORTED or kept.analysed_at is None:
        return virustotal.Unknown()
    return virustotal.Reported(
        report=virustotal.Report(
            malicious=kept.malicious,
            suspicious=kept.suspicious,
            harmless=kept.harmless,
            undetected=kept.undetected,
            reputation=kept.reputation,
            analysed_at=kept.analysed_at,
            country=kept.country,
            owner=kept.owner,
            asn=kept.asn,
            categories=tuple(kept.categories),
            details=tuple((detail["label"], detail["value"]) for detail in kept.details),
        )
    )


def report_for(db: Session, provider: str, address: Address) -> IntelSubject | None:
    """The report kept for an address, if the service has reported on it."""
    return db.scalar(
        select(IntelSubject).where(
            IntelSubject.provider == provider,
            IntelSubject.kind == IP,
            IntelSubject.subject == str(address),
            IntelSubject.outcome == REPORTED,
        )
    )


def reports_for(db: Session, provider: str, addresses: Iterable[Address]) -> list[IntelSubject]:
    """The reports kept for some addresses, in no particular order."""
    found = [str(address) for address in addresses]
    if not found:
        return []
    return list(
        db.scalars(
            select(IntelSubject).where(
                IntelSubject.provider == provider,
                IntelSubject.kind == IP,
                IntelSubject.outcome == REPORTED,
                IntelSubject.subject.in_(found),
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
