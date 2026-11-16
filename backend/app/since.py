"""What is new since the owner last looked at the dashboard: the incidents that began, what the AI
cleared and the devices that appeared. Only what happened on its own is counted: what the owner
did themselves (a verdict, a status, a rule) is not news to them."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import DashboardVisit, Device, Incident, VerdictRule


@dataclass(frozen=True)
class Since:
    """Counts of what is new, and since when. ``since`` is None on a first visit, when there is
    nothing to compare with."""

    since: datetime | None
    # By severity (0 to 4, as in app/events/event.py): incidents that began, which the owner has not
    # called not suspicious or low priority, as the incident list shows them by default.
    incidents: dict[int, int]
    cleared_by_ai: int
    new_devices: int

    @property
    def total(self) -> int:
        return sum(self.incidents.values()) + self.cleared_by_ai + self.new_devices


def _count(db: Session, since: datetime) -> Since:
    rows = db.execute(
        select(Incident.severity, func.count())
        .where(
            Incident.first_seen_at >= since,
            (Incident.verdict.is_(None)) | (Incident.verdict == "threat"),
        )
        .group_by(Incident.severity)
    )
    by_severity = {severity: count for severity, count in rows}
    cleared = db.scalar(
        select(func.count())
        .select_from(VerdictRule)
        .where(VerdictRule.given_by == "ai", VerdictRule.created_at >= since)
    )
    devices = db.scalar(
        select(func.count()).select_from(Device).where(Device.first_seen_at >= since)
    )
    return Since(since, by_severity, cleared or 0, devices or 0)


def of(db: Session, user_id: UUID, now: datetime) -> Since:
    """What is new for this account. A first visit has nothing to compare with, so it is recorded
    now and says nothing. The caller commits."""
    visit = db.get(DashboardVisit, user_id)
    if visit is None:
        db.add(DashboardVisit(user_id=user_id, viewed_at=now))
        return Since(None, {}, 0, 0)
    return _count(db, visit.viewed_at)


def seen(db: Session, user_id: UUID, now: datetime) -> None:
    """Says the owner has now looked, so the next visit is compared with this one. The caller
    commits."""
    visit = db.get(DashboardVisit, user_id)
    if visit is None:
        db.add(DashboardVisit(user_id=user_id, viewed_at=now))
    else:
        visit.viewed_at = now
