"""What the owner chose on the Retention page, and what it comes to for the clean-up.

Nothing is stored until the owner first saves, and the choices only apply once they switch
``managed`` on. Until then every kind of data is kept for the period its own setting gives, as it
always was. Once on, they either keep everything forever (no age limit and no quota, and nothing is
deleted by time at all), or set one number of days for everything that has no period of its own and,
if they want, the most the database may hold."""

from dataclasses import dataclass
from datetime import datetime
from typing import Final

from sqlalchemy.orm import Session

from app.config import Settings
from app.models import RetentionSettings

DEFAULT_DAYS: Final = 30
MIN_DAYS: Final = 1
MAX_DAYS: Final = 3650
MIN_QUOTA_GB: Final = 1
MAX_QUOTA_GB: Final = 100_000
GIGABYTE: Final = 1024**3


@dataclass(frozen=True)
class Policy:
    managed: bool = False
    keep_forever: bool = False
    days: int = DEFAULT_DAYS
    quota_gb: int | None = None

    @property
    def deletes_by_age(self) -> bool:
        """Whether anything is deleted because of how old it is."""
        return not (self.managed and self.keep_forever)

    @property
    def quota_bytes(self) -> int | None:
        """The most the database may hold, if the owner set one that is in force."""
        if not self.managed or self.keep_forever or self.quota_gb is None:
            return None
        return self.quota_gb * GIGABYTE

    def apply(self, settings: Settings) -> Settings:
        """The settings the clean-up goes by: the owner's number of days for everything that is kept
        for a time, in place of each one's own, when they manage retention."""
        if not self.managed or self.keep_forever:
            return settings
        return settings.model_copy(
            update={
                "event_retention_days": self.days,
                "metric_retention_days": self.days,
                "api_log_retention_days": self.days,
                "ai_log_retention_days": self.days,
                "alert_log_retention_days": self.days,
            }
        )


def load(db: Session) -> Policy:
    """The choices as they are saved, or none while nothing has been."""
    row = db.get(RetentionSettings, 1)
    if row is None:
        return Policy()
    return Policy(row.managed, row.keep_forever, row.days, row.quota_gb)


def save(db: Session, policy: Policy) -> bool:
    """Keeps the choices as they are given, and says whether that changed them. The caller
    commits."""
    if policy == load(db):
        return False
    row = db.get(RetentionSettings, 1)
    if row is None:
        row = RetentionSettings(id=1)
        db.add(row)
    row.managed = policy.managed
    row.keep_forever = policy.keep_forever
    row.days = policy.days
    row.quota_gb = policy.quota_gb
    db.flush()
    return True


def updated_at(db: Session) -> datetime | None:
    """When the choices were last saved, or None while nothing has been."""
    row = db.get(RetentionSettings, 1)
    return row.updated_at if row else None
