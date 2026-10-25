"""What AresGate has seen on the network, in one shape whatever program reported it."""

from datetime import datetime
from ipaddress import IPv4Address, IPv6Address
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Identity,
    Index,
    Integer,
    PrimaryKeyConstraint,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime, utcnow
from app.models.retention import SourceRetention


class Event(Base):
    """One thing a connected program reported: a firewall block, an alert, a failed login. Every
    program's events are stored in this shape so one page, one alert rule or the analyst can read
    them all, and the program's own record is kept beside it.

    The table is split into one partition for each week of ``occurred_at`` (see
    ``app/partitions.py``), so old events leave by dropping a table instead of by deleting
    rows. That is why the key and the unique index both hold the time. Nothing is made for a week
    until an event of that week arrives; the migration makes only the table they go in."""

    __tablename__ = "events"
    __table_args__ = (
        PrimaryKeyConstraint("occurred_at", "id"),
        # The same event read twice, because a collector's windows overlap, is kept once.
        UniqueConstraint("source", "fingerprint", "occurred_at", name="uq_events_fingerprint"),
        CheckConstraint("severity BETWEEN 0 AND 4", name="severity"),
        CheckConstraint("src_port BETWEEN 0 AND 65535", name="src_port"),
        CheckConstraint("dst_port BETWEEN 0 AND 65535", name="dst_port"),
        Index("ix_events_source_occurred_at", "source", "occurred_at"),
        Index("ix_events_src_address_occurred_at", "src_address", "occurred_at"),
        Index("ix_events_dst_address_occurred_at", "dst_address", "occurred_at"),
        {"postgresql_partition_by": "RANGE (occurred_at)"},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity())
    # When it happened, as the program that saw it says; and when AresGate read it.
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    # Which integration and which of its connections reported it, such as wazuh and indexer.
    source: Mapped[str] = mapped_column(String(32))
    connection: Mapped[str] = mapped_column(String(32))
    # What sort of event, such as alert, firewall or authentication.
    kind: Mapped[str] = mapped_column(String(32))
    # How serious, from 0 (info) to 4 (critical): the scale in app/events/event.py.
    severity: Mapped[int] = mapped_column(SmallInteger)
    # What it says, in a line, with control characters taken out.
    summary: Mapped[str] = mapped_column(String(500))
    # The rule or signature that fired, such as an Emerging Threats name or a Wazuh rule.
    signature: Mapped[str | None] = mapped_column(String(256), default=None)
    src_address: Mapped[IPv4Address | IPv6Address | None] = mapped_column(INET, default=None)
    src_port: Mapped[int | None] = mapped_column(Integer, default=None)
    dst_address: Mapped[IPv4Address | IPv6Address | None] = mapped_column(INET, default=None)
    dst_port: Mapped[int | None] = mapped_column(Integer, default=None)
    # Lowercase, such as tcp or udp.
    protocol: Mapped[str | None] = mapped_column(String(16), default=None)
    # A hash of what makes it this event at the source, to tell one read twice from two events.
    fingerprint: Mapped[str] = mapped_column(String(64))
    # The program's own record of it, as it gave it (cut down if it was very large).
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)


class EventRetention(SourceRetention):
    """How long one source's events are kept, when that isn't the default. A source without a
    row here keeps them for ``ARESGATE_EVENT_RETENTION_DAYS``."""

    __tablename__ = "event_retention"
    __table_args__ = (CheckConstraint("days BETWEEN 1 AND 3650", name="days"),)
