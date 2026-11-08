"""The alerts log: what became of every message, kept as long as the other logs and no longer.

It is the outbox the notifier works from (``app.alerts.notify``) read the other way: each row is a
message to a destination, with where it is (waiting, sent, given up on) and why. What is still
waiting is never deleted; the rest goes once it is older than the retention period."""

from datetime import datetime, timedelta
from typing import Final

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.alerts.notify import WAITING
from app.config import Settings
from app.models import AlertDelivery, AlertDestination

# A page of the log.
PAGE: Final = 50
MAX_PAGE: Final = 200


def listing(
    db: Session,
    *,
    destination_id: int | None = None,
    state: str | None = None,
    before: int | None = None,
    limit: int = PAGE,
) -> list[tuple[AlertDelivery, str]]:
    """The newest messages first, each with the name of its destination. ``before`` is the id of
    the last one of the page before, to get the next."""
    query = (
        select(AlertDelivery, AlertDestination.name)
        .join(AlertDestination, AlertDestination.id == AlertDelivery.destination_id)
        .order_by(AlertDelivery.id.desc())
        .limit(min(limit, MAX_PAGE))
    )
    if destination_id is not None:
        query = query.where(AlertDelivery.destination_id == destination_id)
    if state is not None:
        query = query.where(AlertDelivery.state == state)
    if before is not None:
        query = query.where(AlertDelivery.id < before)
    return [(row, name) for row, name in db.execute(query)]


def counts(db: Session, destination_id: int | None = None) -> dict[str, int]:
    """How many messages are in each state."""
    query = select(AlertDelivery.state, func.count()).group_by(AlertDelivery.state)
    if destination_id is not None:
        query = query.where(AlertDelivery.destination_id == destination_id)
    return {state: total for state, total in db.execute(query)}


def purge_expired(db: Session, settings: Settings, now: datetime) -> int:
    """Deletes the messages older than the retention period, except any still waiting, and returns
    how many there were. Commits."""
    cutoff = now - timedelta(days=settings.alert_log_retention_days)
    deleted = (
        db.connection()
        .execute(
            delete(AlertDelivery).where(
                AlertDelivery.created_at < cutoff, AlertDelivery.state.not_in(WAITING)
            )
        )
        .rowcount
    )
    db.commit()
    return deleted
