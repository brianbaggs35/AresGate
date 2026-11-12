"""How much of what the AI decides the owner wants to look at first.

Nothing is stored until the owner first saves; until then every decision of the AI waits for them.
The AI may always sound an alarm on its own, because a missed attack costs more than a look at a
false one; what waits is what would set something aside."""

from dataclasses import dataclass
from typing import Final

from sqlalchemy.orm import Session

from app.models import ReviewSettings

DEFAULT_MODE: Final = "all"
DEFAULT_AUTO_FROM: Final = 85
MIN_AUTO_FROM: Final = 50


@dataclass(frozen=True)
class Policy:
    """Which decisions wait for the owner. ``mode`` is ``all`` (every one), ``uncertain`` (those
    the AI is less than ``auto_from`` sure of) or ``auto`` (none: the AI decides on its own).
    ``learn`` is whether what the owner disagreed with goes to the AI."""

    mode: str = DEFAULT_MODE
    auto_from: int = DEFAULT_AUTO_FROM
    learn: bool = True

    def status(self, confidence: int) -> str:
        """Where a new decision of the AI starts: ``auto`` (it counts, and is listed) or
        ``pending`` (it waits for the owner)."""
        if self.mode == "auto":
            return "auto"
        if self.mode == "uncertain" and confidence >= self.auto_from:
            return "auto"
        return "pending"


def load(db: Session) -> Policy:
    """The settings as they are saved, or the defaults where nothing has been."""
    row = db.get(ReviewSettings, 1)
    if row is None:
        return Policy()
    return Policy(row.mode, row.auto_from, row.learn)


def save(db: Session, policy: Policy) -> bool:
    """Keeps the settings as they are given, and says whether that changed them. The caller
    commits."""
    row = db.get(ReviewSettings, 1)
    if row is None:
        if policy == Policy():
            return False
        row = ReviewSettings(id=1)
        db.add(row)
    elif policy == Policy(row.mode, row.auto_from, row.learn):
        return False
    row.mode = policy.mode
    row.auto_from = policy.auto_from
    row.learn = policy.learn
    db.flush()
    return True
