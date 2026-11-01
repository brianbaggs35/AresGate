"""Deleting the record of what was asked of AI providers once it is old enough."""

from datetime import datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import AiCall


def purge_expired(db: Session, settings: Settings, now: datetime) -> int:
    """Deletes the calls older than the retention period, and returns how many there were.
    Commits. The stand-ins stay: an answer from last month still has to be readable."""
    cutoff = now - timedelta(days=settings.ai_log_retention_days)
    deleted = db.connection().execute(delete(AiCall).where(AiCall.occurred_at < cutoff)).rowcount
    db.commit()
    return deleted
