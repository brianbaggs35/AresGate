"""Storing what ntopng knows of the hosts it watches: the collector calls ``record`` with the
hosts it read."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from ipaddress import IPv4Address, IPv6Address
from typing import Any

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import HostTrait

Address = IPv4Address | IPv6Address
_COLUMNS = ("hostname", "os_name", "asn", "as_name", "country", "fingerprints", "read_at")


@dataclass(frozen=True)
class NewTrait:
    """One host as ntopng describes it. What it doesn't say is empty."""

    address: Address
    hostname: str | None = None
    os_name: str | None = None
    asn: int | None = None
    as_name: str | None = None
    country: str | None = None
    fingerprints: dict[str, Any] = field(default_factory=dict[str, Any])


def record(
    db: Session, traits: Sequence[NewTrait], now: datetime, *, source: str, connection: str
) -> int:
    """Puts what ntopng says of each host in place of what was kept, forgets the hosts it no
    longer lists, and returns how many hosts there are. A host listed twice (on two interfaces)
    keeps the one that says more. The caller commits."""
    found: dict[Address, NewTrait] = {}
    for trait in traits:
        kept = found.get(trait.address)
        if kept is None or _said(trait) > _said(kept):
            found[trait.address] = trait
    if found:
        new = insert(HostTrait)
        db.execute(
            new.on_conflict_do_update(
                index_elements=["source", "connection", "address"],
                set_={column: getattr(new.excluded, column) for column in _COLUMNS},
            ),
            [
                {
                    "source": source,
                    "connection": connection,
                    "address": trait.address,
                    "hostname": trait.hostname,
                    "os_name": trait.os_name,
                    "asn": trait.asn,
                    "as_name": trait.as_name,
                    "country": trait.country,
                    "fingerprints": trait.fingerprints,
                    "read_at": now,
                }
                for trait in found.values()
            ],
        )
    db.execute(
        delete(HostTrait).where(
            HostTrait.source == source,
            HostTrait.connection == connection,
            HostTrait.address.not_in(list(found)),
        )
    )
    return len(found)


def _said(trait: NewTrait) -> int:
    """How much a host's description says, for choosing between two."""
    return sum(
        1
        for fact in (
            trait.hostname,
            trait.os_name,
            trait.asn,
            trait.as_name,
            trait.country,
            trait.fingerprints,
        )
        if fact
    )
