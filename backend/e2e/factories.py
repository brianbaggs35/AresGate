"""Makes extra records on demand, for a test that needs more than the baseline holds.

Each factory fills in whatever it isn't given, so a test only names what it cares about. They
work on any session, so the backend's own tests can use them too.
"""

from uuid import uuid4

from sqlalchemy.orm import Session

from app.models import SystemInfo, User
from app.security import passwords
from app.security.accounts import normalize_username

DEFAULT_VALUE = "an e2e value"
DEFAULT_PASSWORD = "an e2e password for testing"  # nosec B105: made up, for test accounts


def system_info(
    session: Session, *, key: str | None = None, value: str = DEFAULT_VALUE
) -> SystemInfo:
    row = SystemInfo(key=key or f"factory-{uuid4().hex[:8]}", value=value)
    session.add(row)
    session.flush()
    return row


def account(
    session: Session, *, username: str | None = None, password: str = DEFAULT_PASSWORD
) -> User:
    user = User(
        username=normalize_username(username or f"factory-{uuid4().hex[:8]}"),
        password_hash=passwords.hash_password(password),
    )
    session.add(user)
    session.flush()
    return user
