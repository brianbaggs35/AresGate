"""What the tests of the Wazuh collectors share: a Wazuh that answers, and connections to it."""

from sqlalchemy.orm import Session

from app.config import Settings
from app.integrations import netguard, registry, service
from app.integrations.service import Submission
from app.models import utcnow
from tests.stubs import Certificate

USER, PASSWORD = "aresgate", "wazuh-password"


def connect(
    session: Session, settings: Settings, server_url: str, certificate: Certificate
) -> None:
    """Saves the manager's connection and the indexer's, both to the server at the address, which
    answers as both, pinned to its certificate."""
    submission = Submission(
        url=server_url,
        tls_mode="pinned",
        tls_ca_pem=None,
        tls_fingerprint=certificate.fingerprint,
        options={"username": USER},
        secrets={"password": PASSWORD},
    )
    service.save(
        session,
        settings,
        netguard.HOME_NETWORK_AND_LOOPBACK,
        registry.INTEGRATIONS["wazuh"],
        {"manager": submission, "indexer": submission},
        utcnow(),
    )
    session.commit()
