"""What is kept of NVD's answers, one row for each CVE."""

from collections.abc import Iterable
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import NvdCve
from app.nvd.lookup import Answer, Found, Record, Unknown

FOUND = "found"
UNKNOWN = "unknown"


def _fill(row: NvdCve, record: Record) -> None:
    row.status = record.status
    row.published_at = record.published_at
    row.modified_at = record.modified_at
    row.cvss_version = record.cvss_version
    row.score = record.score
    row.severity = record.severity
    row.vector = record.vector
    row.description = record.description
    row.weaknesses = list(record.weaknesses)
    row.exploited = record.exploited
    row.exploited_on = record.exploited_on
    row.action_due = record.action_due
    row.required_action = record.required_action
    row.kev_name = record.kev_name


def keep(db: Session, cve_id: str, answer: Answer, now: datetime) -> NvdCve | None:
    """Keeps what NVD said of a CVE in place of what was kept before. Only a record, or that NVD
    has none, is kept: a failure or a request to wait says nothing of the CVE. The caller
    commits."""
    if not isinstance(answer, Found | Unknown):
        return None
    row = db.get(NvdCve, cve_id) or NvdCve(cve_id=cve_id, state=UNKNOWN, checked_at=now)
    row.checked_at = now
    if isinstance(answer, Found):
        row.state = FOUND
        _fill(row, answer.record)
    else:
        # What was said before about a CVE NVD no longer has is not kept.
        row.state = UNKNOWN
        _fill(row, Record(cve_id=cve_id))
    db.add(row)
    return row


def load(db: Session, cve_ids: Iterable[str]) -> dict[str, NvdCve]:
    """What is kept of each of the CVEs, by identifier, for those that have been asked about."""
    wanted = list(dict.fromkeys(cve_ids))
    if not wanted:
        return {}
    return {row.cve_id: row for row in db.scalars(select(NvdCve).where(NvdCve.cve_id.in_(wanted)))}


def purge_expired(db: Session, days: int, now: datetime) -> int:
    """Forgets what NVD said of the CVEs last asked about more than ``days`` days ago, and returns
    how many there were. A CVE that an incident still names is asked about again. Commits."""
    deleted = (
        db.connection()
        .execute(delete(NvdCve).where(NvdCve.checked_at < now - timedelta(days=days)))
        .rowcount
    )
    db.commit()
    return deleted
