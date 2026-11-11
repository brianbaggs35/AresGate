"""What the owner of the network says of a subject, whatever the services made of it.

A service can be wrong either way: an address it flags may be a friend's server, and one it has
no complaint about may be the one that has been scanning the network. The owner can say so, and a
ruling stands for what the page shows, what the AI is told and what the other pages draw of the
subject, until it is taken back. The services' own answer is kept beside it, and shown as what they
said. A ruling is the owner's, so it belongs to no service and a newer answer does not replace it.
"""

from collections.abc import Iterable
from datetime import datetime
from ipaddress import IPv4Address, IPv6Address
from typing import Final, Literal

from sqlalchemy import ColumnElement, case, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.intel.subjects import Subject
from app.models import IntelOverride

type Address = IPv4Address | IPv6Address
type Ruling = Literal["safe", "suspicious"]

SAFE: Final = "safe"
SUSPICIOUS: Final = "suspicious"
# What each ruling comes to on the scale of a service's judgement.
JUDGEMENT_OF: Final = {SAFE: "clean", SUSPICIOUS: "suspicious"}
MAX_NOTE = 500
# How many rulings the list of them has room for.
LIMIT = 500


def effective(judgement: str, ruling: str | None) -> str:
    """What a subject comes to: the owner's ruling where there is one, else what the service made
    of it."""
    return JUDGEMENT_OF.get(ruling, judgement) if ruling is not None else judgement


def judgement_column(
    judgement: InstrumentedAttribute[str], ruling: InstrumentedAttribute[str]
) -> ColumnElement[str]:
    """``effective`` for a query: the judgement column, or the ruling's own where there is one."""
    return case(
        (ruling == SAFE, JUDGEMENT_OF[SAFE]),
        (ruling == SUSPICIOUS, JUDGEMENT_OF[SUSPICIOUS]),
        else_=judgement,
    )


def rule(
    db: Session, subject: Subject, verdict: Ruling, note: str | None, now: datetime
) -> IntelOverride:
    """Says what the owner makes of a subject, replacing what was said of it before."""
    values = {
        "kind": subject.kind,
        "subject": subject.key,
        "host": subject.host,
        "verdict": verdict,
        "note": note,
        "set_at": now,
    }
    statement = insert(IntelOverride).values(**values)
    return db.scalars(
        statement.on_conflict_do_update(
            constraint="uq_threat_intel_overrides_subject",
            set_={name: statement.excluded[name] for name in ("host", "verdict", "note", "set_at")},
        ).returning(IntelOverride),
        execution_options={"populate_existing": True},
    ).one()


def ruling_for(db: Session, subject: Subject) -> IntelOverride | None:
    """What the owner has said of a subject, if anything. It is read anew each time, since ``rule``
    replaces a ruling without going through the session."""
    return db.scalar(
        select(IntelOverride)
        .where(IntelOverride.kind == subject.kind, IntelOverride.subject == subject.key)
        .execution_options(populate_existing=True)
    )


def take_back(db: Session, subject: Subject) -> IntelOverride | None:
    """Takes back what the owner said of a subject, and returns what it was, or None if nothing was
    said."""
    found = ruling_for(db, subject)
    if found is None:
        return None
    db.delete(found)
    db.flush()
    return found


def for_addresses(db: Session, addresses: Iterable[Address]) -> dict[str, IntelOverride]:
    """What the owner has said of some internet addresses, by the address as text."""
    found = [str(address) for address in addresses]
    if not found:
        return {}
    return {
        row.subject: row
        for row in db.scalars(
            select(IntelOverride).where(
                IntelOverride.kind == "ip", IntelOverride.subject.in_(found)
            )
        )
    }


def listing(db: Session) -> list[IntelOverride]:
    """Everything the owner has ruled on, the latest first."""
    return list(
        db.scalars(
            select(IntelOverride)
            .order_by(IntelOverride.set_at.desc(), IntelOverride.id.desc())
            .limit(LIMIT)
        )
    )
