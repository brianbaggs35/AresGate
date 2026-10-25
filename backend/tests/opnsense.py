"""What the tests of the OPNsense collectors share: a firewall that answers, a connection to it
and a way to run a collector against it once."""

import asyncio
import json
from collections.abc import Callable, Mapping

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.collectors.base import Collector
from app.collectors.scheduler import Scheduler
from app.config import Settings
from app.integrations import netguard, registry, service
from app.integrations.apilog import ApiLogRecorder
from app.integrations.service import Submission
from app.models import CollectorHealth, utcnow
from tests.stubs import Answer, Certificate, Seen, Serve, make_certificate

KEY, SECRET = "firewall-key", "firewall-secret"


def routed(replies: Mapping[str, object]) -> Callable[[Seen], Answer]:
    """A firewall that answers the paths given and says 404 to the others."""

    def handle(seen: Seen) -> Answer:
        if seen.path in replies:
            return Answer(status=200, body=json.dumps(replies[seen.path]))
        return Answer(status=404, body=json.dumps({"status": 404}))

    return handle


def answering(reply: object, *, status: int = 200) -> Callable[[Seen], Answer]:
    """A firewall that answers every path the same."""
    return lambda seen: Answer(status=status, body=json.dumps(reply))


def connect(
    session: Session, settings: Settings, server_url: str, certificate: Certificate
) -> None:
    """Saves a connection to the firewall at the address, pinned to its certificate."""
    submission = Submission(
        url=server_url,
        tls_mode="pinned",
        tls_ca_pem=None,
        tls_fingerprint=certificate.fingerprint,
        options={},
        secrets={"api_key": KEY, "api_secret": SECRET},
    )
    service.save(
        session,
        settings,
        netguard.HOME_NETWORK_AND_LOOPBACK,
        registry.INTEGRATIONS["opnsense"],
        {"api": submission},
        utcnow(),
    )
    session.commit()


def collect(settings: Settings, engine: Engine, collector: Collector) -> None:
    """Runs the collector once on every connection it applies to."""
    maker = sessionmaker(bind=engine, expire_on_commit=False)
    scheduler = Scheduler(
        settings,
        maker,
        ApiLogRecorder(maker),
        netguard.HOME_NETWORK_AND_LOOPBACK,
        collectors=(collector,),
    )
    asyncio.run(scheduler.run_once())


def health(session: Session) -> CollectorHealth:
    """The one collector's record of how it is doing."""
    session.expire_all()
    return session.scalars(select(CollectorHealth)).one()


def run(
    session: Session,
    settings: Settings,
    engine: Engine,
    serve: Serve,
    collector: Collector,
    handler: Callable[[Seen], Answer],
) -> None:
    """Connects to a firewall that answers with the handler, and runs the collector once."""
    certificate = make_certificate()
    connect(session, settings, serve(handler, certificate).url, certificate)
    collect(settings, engine, collector)
