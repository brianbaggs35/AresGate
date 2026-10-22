"""The data every end-to-end test starts from, and the named states the database can be put in.

Every table the models define is emptied first, so a state never depends on what an earlier test
left behind. Later features add their own rows here (an account to sign in with, an integration
to look at), so specs can rely on exactly what the baseline holds.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from functools import cache
from typing import Literal, NamedTuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import audit
from app.models import Base, SystemInfo, User
from app.security import passwords, setup_code

# Fixed, so a spec can assert on what it sees however long the run takes.
BASELINE_TIME = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

BASELINE_SYSTEM_INFO = {
    "install_id": "e2e-install",
    "first_started_at": BASELINE_TIME.isoformat(),
}


class Credentials(NamedTuple):
    username: str
    password: str


# The account every spec can sign in with. The password is public, since only a test server
# runs the harness.
BASELINE_ACCOUNT = Credentials("e2e-admin", "e2e correct horse battery staple")
# The setup code a fresh install starts with, in place of the one a real install prints in its
# log. It's a code the real alphabet allows.
FRESH_INSTALL_SETUP_CODE = "TEST-2222-ABCD"

FixtureName = Literal["baseline", "fresh-install"]


class Fixture(NamedTuple):
    description: str
    load: Callable[[Session], None]


def clean(session: Session) -> list[str]:
    """Empties every table the models define, keeping the migration history, and returns the
    tables' names in the order they were emptied (rows that refer to others go first)."""
    emptied: list[str] = []
    audit.allow_deletes(session)
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


@cache
def _baseline_password_hash() -> str:
    # Hashing is slow on purpose, and every spec starts from the baseline.
    return passwords.hash_password(BASELINE_ACCOUNT.password)


def load_baseline(session: Session) -> None:
    session.add_all(
        SystemInfo(key=key, value=value, updated_at=BASELINE_TIME)
        for key, value in BASELINE_SYSTEM_INFO.items()
    )
    session.add(
        User(
            username=BASELINE_ACCOUNT.username,
            password_hash=_baseline_password_hash(),
            created_at=BASELINE_TIME,
            password_changed_at=BASELINE_TIME,
        )
    )


def load_fresh_install(session: Session) -> None:
    """An install that has just started and has never been set up: no account, and a setup code
    waiting to be used."""
    setup_code.store(session, FRESH_INSTALL_SETUP_CODE)


FIXTURES: dict[FixtureName, Fixture] = {
    "baseline": Fixture("The data every spec starts from.", load_baseline),
    "fresh-install": Fixture(
        "No account yet, only the setup code, as on the very first start.", load_fresh_install
    ),
}


def load(session: Session, name: FixtureName) -> list[str]:
    """Replaces everything in the database with a named state, and returns the tables emptied."""
    emptied = clean(session)
    FIXTURES[name].load(session)
    session.flush()
    return emptied
