"""Which CVE is asked about next.

The CVEs wanted are those that recent incidents name, the most recent incident first. One that has
never been asked about comes before one whose answer has gone stale. An answer goes stale at a pace
that follows how it can change: NVD scores a new CVE some days after it is published, and CISA adds
a CVE to its exploited list whenever exploitation is seen, so a record with no score, and a CVE NVD
has not received, are asked about again after a day, a scored one that is not on CISA's list after
three, and one that is on it after two weeks, since that is not taken off.
"""

from datetime import datetime, timedelta
from typing import Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Incident, IncidentSignal, NvdCve
from app.nvd import cves, store

UNSETTLED_FRESH: Final = timedelta(days=1)
SCORED_FRESH: Final = timedelta(days=3)
EXPLOITED_FRESH: Final = timedelta(weeks=2)
# Incidents seen this recently are worth knowing the CVEs of.
RECENT: Final = timedelta(days=30)
# How many signals are read for CVEs, the most recent incident's first.
SIGNALS: Final = 2000


def stale(row: NvdCve | None, now: datetime) -> bool:
    """Whether a CVE has to be asked about: it never was, or what is kept has gone stale."""
    if row is None:
        return True
    if row.state == store.UNKNOWN or row.score is None:
        fresh = UNSETTLED_FRESH
    else:
        fresh = EXPLOITED_FRESH if row.exploited else SCORED_FRESH
    return now - row.checked_at >= fresh


def named(db: Session, now: datetime) -> list[str]:
    """The CVEs recent incidents name, the most recent first."""
    rows = db.execute(
        select(IncidentSignal.summary, IncidentSignal.signature, IncidentSignal.evidence)
        .join(Incident, Incident.id == IncidentSignal.incident_id)
        .where(Incident.last_seen_at >= now - RECENT)
        .order_by(Incident.last_seen_at.desc(), IncidentSignal.occurred_at.desc())
        .limit(SIGNALS)
    )
    return cves.merge(cves.named_by(*row) for row in rows)


def next_wanted(db: Session, now: datetime, *, skip: frozenset[str] = frozenset()) -> str | None:
    """The CVE to ask about next, or None if there is none. ``skip`` holds those that are not to be
    asked about for now."""
    ordered = [cve_id for cve_id in named(db, now) if cve_id not in skip]
    if not ordered:
        return None
    kept = store.load(db, ordered)
    due = [cve_id for cve_id in ordered if stale(kept.get(cve_id), now)]
    if not due:
        return None
    # Never asked, then stale, each in the order of the incidents that name them.
    return min(due, key=lambda cve_id: (cve_id in kept, due.index(cve_id)))
