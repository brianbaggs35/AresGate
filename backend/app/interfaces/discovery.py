"""Finding the feeds: the port names that integrations have stored data under, and what they list
themselves. Finding is on request, because looking through the events is work and asking
a product what it lists is a call to it, and nothing found is placed anywhere: the owner (or
a suggestion the owner takes) does that."""

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Final, NamedTuple

from psycopg.errors import QueryCanceled
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.integrations import probes
from app.integrations.client import ApiClient, CallFailed, Recorder, Target
from app.integrations.netguard import AddressPolicy
from app.models import Event, IntegrationConnection, InterfaceFeed, MetricSeries

# How far back the events are looked through. A port that has sent nothing for this long is
# found again by its metrics, or when it next does.
WINDOW: Final = timedelta(days=3)
# The most the search of the events may take before it is left out.
EVENTS_TIMEOUT_MS: Final = 5000

# Connections whose data isn't about a port, so they are one feed for the whole connection:
# CrowdSec's bans and Wazuh's alerts name no interface.
WHOLE: Final = (("crowdsec", "lapi"), ("wazuh", "indexer"))


class Found(NamedTuple):
    """One feed that was found."""

    integration: str
    connection: str
    # The name the source uses; empty for the whole connection.
    native_name: str
    # What the source says it is, and a few words about it.
    label: str = ""
    detail: str = ""


def from_events(db: Session, now: datetime) -> tuple[list[Found], bool]:
    """The ports that recent events came in on, and whether the search was complete: on a busy
    install it is given a few seconds, and what it hasn't read by then is left to the next time."""
    db.execute(select(func.set_config("statement_timeout", str(EVENTS_TIMEOUT_MS), True)))
    try:
        rows = db.execute(
            select(Event.source, Event.connection, Event.iface)
            .where(Event.occurred_at >= now - WINDOW, Event.iface.is_not(None))
            .distinct()
        ).all()
    except OperationalError as error:
        if not isinstance(error.orig, QueryCanceled):
            raise
        # Ending the transaction ends the time limit that was set for it.
        db.rollback()
        return [], False
    db.execute(select(func.set_config("statement_timeout", "0", True)))
    return [Found(source, connection, name or "") for source, connection, name in rows], True


def from_metrics(db: Session) -> list[Found]:
    """The ports that metrics are kept for. A series goes when its last sample does, so the ones
    that are there were measured within the time metrics are kept."""
    name = MetricSeries.labels["interface"].astext
    rows = db.execute(
        select(MetricSeries.source, MetricSeries.connection, name)
        .where(MetricSeries.labels.has_key("interface"))
        .distinct()
    ).all()
    return [Found(source, connection, text) for source, connection, text in rows if text]


def whole_connections(db: Session) -> list[Found]:
    """The connections that are one feed as a whole, where they are connected."""
    rows = db.execute(select(IntegrationConnection.integration, IntegrationConnection.connection))
    connected = {(integration, connection) for integration, connection in rows}
    return [Found(*pair, "") for pair in WHOLE if pair in connected]


async def ntopng_live(
    target: Target, recorder: Recorder, policy: AddressPolicy
) -> list[Found] | str:
    """The interfaces ntopng lists, named as its metrics name them, or why it couldn't be asked."""
    try:
        async with ApiClient(target, recorder, policy) as client:
            listed = await probes.ntopng_interfaces(client, target)
    except CallFailed as failure:
        return str(failure)
    if isinstance(listed, probes.Verdict):
        return listed.message
    return [
        Found(
            target.integration,
            target.connection,
            item.ifname or str(item.ifid),
            item.name if item.name != item.ifname else "",
            item.source,
        )
        for item in listed
    ]


def store(db: Session, found: Sequence[Found], now: datetime) -> int:
    """Keeps what was found: a feed seen for the first time is made (not placed), and one seen
    again is noted as seen, with what the source says it is. Says how many are new. The caller
    commits."""
    wanted = {(item.integration, item.connection, item.native_name): item for item in found}
    if not wanted:
        return 0
    known = {
        (feed.integration, feed.connection, feed.native_name): feed
        for feed in db.scalars(select(InterfaceFeed))
    }
    new = 0
    for key, item in wanted.items():
        feed = known.get(key)
        if feed is None:
            db.add(
                InterfaceFeed(
                    integration=item.integration,
                    connection=item.connection,
                    native_name=item.native_name,
                    label=item.label,
                    detail=item.detail,
                    last_seen_at=now,
                    created_at=now,
                )
            )
            new += 1
            continue
        feed.last_seen_at = now
        # What the source says about itself is kept up to date, but never blanked by a source
        # that said less this time.
        feed.label = item.label or feed.label
        feed.detail = item.detail or feed.detail
    db.flush()
    return new
