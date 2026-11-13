"""Which address the next lookup is about: an internet address that a recent incident involved, and
that has no answer kept yet. Once every such address has one, the allowance goes to keeping the
answers up to date: the address whose answer stopped being fresh longest ago is asked about again.
"""

import ipaddress
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.intel import store
from app.models import Incident, IntelLookup, IntelSubject, Interface

type Address = ipaddress.IPv4Address | ipaddress.IPv6Address
type Network = ipaddress.IPv4Network | ipaddress.IPv6Network

# Incidents seen this recently are worth asking about: an older one is no longer happening.
RECENT = timedelta(days=7)
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


def next_address(
    db: Session, provider: str, now: datetime, *, ipv4_only: bool = False
) -> Address | None:
    """The address to ask about next, or None if there is none to ask about. An address with no
    answer kept comes first, the most recent incident's first. After those, the address whose
    answer stopped being fresh longest ago. One asked about within ``RETRY`` waits, whatever came
    of it, so a lookup that failed or was cut short isn't repeated at once. A service that only
    takes IPv4 addresses is never given another kind (``ipv4_only``)."""
    own = own_networks(db)
    groups = db.scalars(
        select(Incident.addresses)
        .where(Incident.last_seen_at >= now - RECENT)
        .order_by(Incident.last_seen_at.desc())
        .limit(INCIDENTS)
    )
    # Each address once, in the order the incidents first name it.
    ordered = dict.fromkeys(address for group in groups for address in group)
    retried = set(
        db.scalars(
            select(IntelLookup.address).where(
                IntelLookup.provider == provider, IntelLookup.requested_at >= now - RETRY
            )
        )
    )
    wanted = [
        address
        for address in ordered
        if address not in retried
        and sendable(address, own)
        and (address.version == 4 or not ipv4_only)
    ]
    if not wanted:
        return None
    answers = {
        row.subject: row
        for row in db.scalars(
            select(IntelSubject).where(
                IntelSubject.provider == provider,
                IntelSubject.kind == store.IP,
                IntelSubject.subject.in_([str(address) for address in wanted]),
            )
        )
    }
    stale: list[tuple[datetime, Address]] = []
    for address in wanted:
        answer = answers.get(str(address))
        if answer is None:
            return address
        until = store.fresh_until(answer)
        if until <= now:
            stale.append((until, address))
    return min(stale, key=lambda found: found[0])[1] if stale else None
