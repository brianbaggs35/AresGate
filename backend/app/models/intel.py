"""What AresGate asked threat-intelligence services, and what they said.

A lookup is kept for as long as its access level's allowance is counted over, so that a restart
doesn't hand the allowance back. A report is the last thing a service said of one address, and it
is what the AI reads of that address.
"""

from datetime import datetime
from ipaddress import IPv4Address, IPv6Address

from sqlalchemy import BigInteger, Identity, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime, utcnow


class IntelLookup(Base):
    """One request AresGate made to a threat-intelligence service about an address. One that failed
    is kept too, since a request that went out counts toward the allowance."""

    __tablename__ = "threat_intel_lookups"
    __table_args__ = (
        Index("ix_threat_intel_lookups_provider_requested_at", "provider", "requested_at"),
        Index("ix_threat_intel_lookups_provider_address", "provider", "address", "requested_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    provider: Mapped[str] = mapped_column(String(32))
    address: Mapped[IPv4Address | IPv6Address] = mapped_column(INET)
    requested_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    # What came of it: pending while it is being asked, then reported, unknown (the service has no
    # report on the address) or failed.
    outcome: Mapped[str] = mapped_column(String(16), default="pending")


class IntelReport(Base):
    """The last thing a threat-intelligence service said of one address."""

    __tablename__ = "threat_intel_reports"
    __table_args__ = (
        UniqueConstraint("provider", "address", name="uq_threat_intel_reports_address"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    provider: Mapped[str] = mapped_column(String(32))
    address: Mapped[IPv4Address | IPv6Address] = mapped_column(INET)
    # When the service last analysed the address, as it says.
    analysed_at: Mapped[datetime] = mapped_column(UTCDateTime)
    malicious: Mapped[int] = mapped_column(Integer)
    suspicious: Mapped[int] = mapped_column(Integer)
    harmless: Mapped[int] = mapped_column(Integer)
    undetected: Mapped[int] = mapped_column(Integer)
    # The community's score: below zero leans malicious, above zero leans harmless.
    reputation: Mapped[int] = mapped_column(Integer)
    country: Mapped[str | None] = mapped_column(String(8), default=None)
    owner: Mapped[str | None] = mapped_column(String(120), default=None)
    asn: Mapped[int | None] = mapped_column(BigInteger, default=None)
