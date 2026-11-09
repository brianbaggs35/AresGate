"""Which address the next lookup is about: an internet address that a recent incident involved, and
that no lookup has asked about lately."""

import ipaddress
from datetime import datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.intel import store
from app.models import Incident, IntelLookup, Interface

type Address = ipaddress.IPv4Address | ipaddress.IPv6Address
type Network = ipaddress.IPv4Network | ipaddress.IPv6Network

# Incidents seen this recently are worth asking about: an older one is no longer happening.
RECENT = timedelta(days=7)
# How long a report, or a lookup that found none, is taken as the answer for an address: as long as
# the answer is kept as fresh, so an address is not asked about again while it is.
ANSWER_FOR = store.FRESH
# How soon an address whose lookup failed, or was cut short, is asked about again.
RETRY = timedelta(hours=1)
# How many incidents are looked through, most recent first.
INCIDENTS = 200


def own_networks(db: Session) -> tuple[Network, ...]:
    """The home's own addresses on the internet: the networks of its interfaces on the internet
    side. An address in one of them is never sent to a service, since that would tell the service
    where the home is."""
    found: list[Network] = []
    for networks in db.scalars(select(Interface.networks).where(Interface.role == "internet")):
        for text in networks or []:
            try:
                found.append(ipaddress.ip_network(str(text), strict=False))
            except ValueError:
                continue
    return tuple(found)


def sendable(address: Address, own: tuple[Network, ...]) -> bool:
    """Whether an address may be sent to a service: it is on the internet, and it isn't the home's
    own."""
    if not address.is_global:
        return False
    return not any(address in network for network in own if network.version == address.version)


def next_address(db: Session, provider: str, now: datetime) -> Address | None:
    """The address to ask about next, the most recent incident's first, or None if there is none
    to ask about."""
    own = own_networks(db)
    groups = db.scalars(
        select(Incident.addresses)
        .where(Incident.last_seen_at >= now - RECENT)
        .order_by(Incident.last_seen_at.desc())
        .limit(INCIDENTS)
    )
    # Each address once, in the order the incidents first name it.
    ordered = dict.fromkeys(address for group in groups for address in group)
    asked = set(
        db.scalars(
            select(IntelLookup.address).where(
                IntelLookup.provider == provider,
                or_(
                    and_(
                        IntelLookup.requested_at >= now - ANSWER_FOR,
                        IntelLookup.outcome.in_((store.REPORTED, store.UNKNOWN)),
                    ),
                    IntelLookup.requested_at >= now - RETRY,
                ),
            )
        )
    )
    for address in ordered:
        if address not in asked and sendable(address, own):
            return address
    return None
