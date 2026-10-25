import os
import secrets
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.config import Settings
from app.events.event import NewEvent, Severity
from app.metrics.sample import NewSample
from app.models import User, utcnow
from app.security import totp, two_factor

TEST_DATABASE_URL = os.environ.get("ARESGATE_TEST_DATABASE_URL", "")
SERVER_NAME = "aresgate.test"
ORIGIN = f"https://{SERVER_NAME}"
# A fresh key for each test run: nothing here is worth keeping.
TEST_SECRET_KEY = secrets.token_urlsafe(32)

ACCOUNT_USERNAME = "brian"
ACCOUNT_PASSWORD = "a sentence nobody would guess"
OTHER_ORIGIN = "https://evil.example"


def turn_on_two_factor(
    session: Session, settings: Settings, user: User, now: datetime | None = None
) -> tuple[str, list[str]]:
    """Gives the account an authenticator app, as setting it up in the web app would. Returns
    the key the app holds and the recovery codes."""
    now = now or utcnow()
    secret, _ = two_factor.start_enrollment(session, settings, user, now)
    codes = two_factor.confirm_enrollment(
        session, settings, user, totp.code_for(secret, totp.current_period(now)), now
    )
    assert codes is not None
    session.commit()
    return secret, codes


def new_event(**changes: object) -> NewEvent:
    """An event as a collector would hand it over, with whatever is given changed."""
    fields: dict[str, Any] = {
        "source": "wazuh",
        "connection": "indexer",
        "kind": "alert",
        "severity": Severity.MEDIUM,
        "occurred_at": utcnow(),
        "identity": ("alert-1",),
        "summary": "sshd: authentication failed",
        **changes,
    }
    return NewEvent(**fields)


def new_sample(**changes: object) -> NewSample:
    """A sample as a collector would hand it over, with whatever is given changed."""
    fields: dict[str, Any] = {
        "source": "opnsense",
        "connection": "api",
        "name": "system.load_1m",
        "value": 0.42,
        "sampled_at": utcnow(),
        **changes,
    }
    return NewSample(**fields)
