"""What is kept of the lookups made, and of the answers they brought back.

Every request AresGate makes is kept as a lookup, which is what the allowance is counted over. The
answer about each subject is kept once as well, and for good: a search or a background lookup of a
subject whose answer is still fresh is answered from what is kept, and VirusTotal isn't asked again.
An answer that is no longer fresh is asked about again, and the newer answer takes its place. If
VirusTotal can't be asked then, the answer kept is still there to show.

How long an answer is fresh depends on what it said. VirusTotal has no cheaper way to ask whether a
report changed than to ask for the report, so the allowance goes where answers change soonest:
something engines flagged, or that has no report yet, is asked about again after ``SOONER``, and
something no engine flagged after ``FRESH``.
"""

from collections.abc import Iterable
from datetime import datetime, timedelta
from ipaddress import IPv4Address, IPv6Address

from sqlalchemy import case, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.intel import greynoise, otx, virustotal
from app.intel.subjects import Subject
from app.models import IntelLookup, IntelSubject

type Address = IPv4Address | IPv6Address
type Answered = virustotal.Reported | virustotal.Unknown

# How long a lookup is kept: long enough to count a month's allowance over, with some to spare.
KEEP = timedelta(days=40)
# How long an answer that no engine flagged is taken as fresh, so the subject is not asked about
# again. A flagged subject, or one with no report yet, is asked about again sooner: an address that
# attacks today is often cleaned up or handed to someone else within days, and a name nobody has
# analysed yet is likely to be analysed soon.
FRESH = timedelta(days=7)
SOONER = timedelta(days=2)
CLEAN = "clean"

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
    "judgement",
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
    ``now``. There is one row per subject, so a subject is never kept twice. What the row has
    gathered stays: when the subject was first asked about, how often it has been, and, if this
    answer changes the judgement, when it did and what the judgement was before."""
    values = _values(provider, subject, answer, now)
    statement = insert(IntelSubject).values(**values)
    newer = statement.excluded
    changed = IntelSubject.judgement != newer.judgement
    replaced: dict[str, object] = {name: newer[name] for name in _REPLACED}
    replaced["host"] = func.coalesce(newer.host, IntelSubject.host)
    replaced["checks"] = IntelSubject.checks + 1
    replaced["changed_at"] = case((changed, newer.checked_at), else_=IntelSubject.changed_at)
    replaced["previous_judgement"] = case(
        (changed, IntelSubject.judgement), else_=IntelSubject.previous_judgement
    )
    db.execute(
        statement.on_conflict_do_update(
            constraint="uq_threat_intel_subjects_subject", set_=replaced
        )
    )


def judge_for(provider: str, report: virustotal.Report | None) -> virustotal.Judgement:
    """What a service's report comes to, by that service's own rules."""
    if provider == otx.PROVIDER:
        return otx.judge(report)
    if provider == greynoise.PROVIDER:
        return greynoise.judge(report)
    return virustotal.judge(report)


def _values(provider: str, subject: Subject, answer: Answered, now: datetime) -> dict[str, object]:
    """The columns of a subject's answer. A subject with no report keeps no counts."""
    values: dict[str, object] = {
        "provider": provider,
        "kind": subject.kind,
        "subject": subject.key,
        "host": subject.host,
        "checked_at": now,
        "first_checked_at": now,
        "checks": 1,
        "judgement": virustotal.judge(None),
        "changed_at": None,
        "previous_judgement": None,
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
            judgement=judge_for(provider, report),
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


def fresh_for(judgement: str) -> timedelta:
    """How long an answer with this judgement is taken as fresh."""
    return FRESH if judgement == CLEAN else SOONER


def fresh_until(row: IntelSubject) -> datetime:
    """When the answer kept for a subject stops being fresh, so the subject is asked about again."""
    return row.checked_at + fresh_for(row.judgement)


def fresh(row: IntelSubject, now: datetime) -> bool:
    """Whether the answer kept for a subject is still taken as the answer at ``now``."""
    return now < fresh_until(row)


def kept(db: Session, provider: str, subject: Subject) -> IntelSubject | None:
    """The answer kept for a subject, however long ago it was given. It is read anew each time,
    since ``keep`` replaces an answer without going through the session."""
    return db.scalar(
        select(IntelSubject)
        .where(
            IntelSubject.provider == provider,
            IntelSubject.kind == subject.kind,
            IntelSubject.subject == subject.key,
        )
        .execution_options(populate_existing=True)
    )


def cached(db: Session, provider: str, subject: Subject, now: datetime) -> IntelSubject | None:
    """The answer kept for a subject, if it is still fresh at ``now``."""
    row = kept(db, provider, subject)
    return row if row is not None and fresh(row, now) else None


def answer_of(row: IntelSubject) -> Answered:
    """The answer kept for a subject, as it was given: its report, or that there was none."""
    if row.outcome != REPORTED or row.analysed_at is None:
        return virustotal.Unknown()
    return virustotal.Reported(
        report=virustotal.Report(
            malicious=row.malicious,
            suspicious=row.suspicious,
            harmless=row.harmless,
            undetected=row.undetected,
            reputation=row.reputation,
            analysed_at=row.analysed_at,
            country=row.country,
            owner=row.owner,
            asn=row.asn,
            categories=tuple(row.categories),
            details=tuple((detail["label"], detail["value"]) for detail in row.details),
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


def answers_for(
    db: Session, provider: str, addresses: Iterable[Address]
) -> dict[Address, IntelSubject]:
    """The answers kept for some addresses, whether the service had a report or none. Nothing is
    asked of the service: an address with no answer kept is left out."""
    found = {str(address): address for address in addresses}
    if not found:
        return {}
    rows = db.scalars(
        select(IntelSubject).where(
            IntelSubject.provider == provider,
            IntelSubject.kind == IP,
            IntelSubject.subject.in_(list(found)),
        )
    )
    return {found[row.subject]: row for row in rows}


def prune(db: Session, provider: str, now: datetime) -> None:
    """Forgets the lookups that are too old to count toward any allowance."""
    db.execute(
        delete(IntelLookup).where(
            IntelLookup.provider == provider, IntelLookup.requested_at < now - KEEP
        )
    )
