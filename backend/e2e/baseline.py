"""The data every end-to-end test starts from, and the named states the database can be put in.

Every table the models define is emptied first, so a state never depends on what an earlier test
left behind. Later features add their own rows here (an account to sign in with, an integration
to look at), so specs can rely on exactly what the baseline holds.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal, NamedTuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Base, SystemInfo

# Fixed, so a spec can assert on what it sees however long the run takes.
BASELINE_TIME = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

BASELINE_SYSTEM_INFO = {
    "install_id": "e2e-install",
    "first_started_at": BASELINE_TIME.isoformat(),
}

FixtureName = Literal["baseline", "fresh-install"]


class Fixture(NamedTuple):
    description: str
    load: Callable[[Session], None]


def clean(session: Session) -> list[str]:
    """Empties every table the models define, keeping the migration history, and returns the
    tables' names in the order they were emptied (rows that refer to others go first)."""
    emptied: list[str] = []
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
        emptied.append(table.name)
    return emptied


def counts(session: Session) -> dict[str, int]:
    """How many rows each table the models define holds."""
    return {
        table.name: session.scalar(select(func.count()).select_from(table)) or 0
        for table in Base.metadata.sorted_tables
    }


def load_baseline(session: Session) -> None:
    session.add_all(
        SystemInfo(key=key, value=value, updated_at=BASELINE_TIME)
        for key, value in BASELINE_SYSTEM_INFO.items()
    )


def load_fresh_install(session: Session) -> None:
    """Nothing: an install that has just started and has never been set up has no rows."""


FIXTURES: dict[FixtureName, Fixture] = {
    "baseline": Fixture("The data every spec starts from.", load_baseline),
    "fresh-install": Fixture("An empty database, as on the very first start.", load_fresh_install),
}


def load(session: Session, name: FixtureName) -> list[str]:
    """Replaces everything in the database with a named state, and returns the tables emptied."""
    emptied = clean(session)
    FIXTURES[name].load(session)
    session.flush()
    return emptied
