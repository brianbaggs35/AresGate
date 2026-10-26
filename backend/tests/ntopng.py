"""What the tests of the ntopng collectors share: a ntopng that answers, and a connection to it."""

from sqlalchemy.orm import Session

from app.config import Settings
from app.integrations import netguard, registry, service
from app.integrations.service import Submission
from app.models import utcnow

TOKEN = "a-ntopng-token"
USER, PASSWORD = "aresgate", "ntopng-password"


def connect(
    session: Session,
    settings: Settings,
    server_url: str,
    *,
    basic: bool = False,
    interface_id: int = 0,
) -> None:
    """Saves a connection to the ntopng at the address (plain http, which ntopng allows), signing
    in with a token or, if ``basic``, with a user name and password."""
    options: dict[str, str | int | None] = {"auth": "basic" if basic else "token"}
    options["interface_id"] = interface_id
    if basic:
        options["username"] = USER
    submission = Submission(
        url=server_url,
        tls_mode="system",
        tls_ca_pem=None,
        tls_fingerprint=None,
        options=options,
        secrets={"password": PASSWORD} if basic else {"token": TOKEN},
    )
    service.save(
        session,
        settings,
        netguard.HOME_NETWORK_AND_LOOPBACK,
        registry.INTEGRATIONS["ntopng"],
        {"api": submission},
        utcnow(),
    )
    session.commit()
