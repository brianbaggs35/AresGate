"""What AresGate asked threat-intelligence services, and what they said.

A lookup is kept for as long as its access level's allowance is counted over, so that a restart
doesn't hand the allowance back. The answer about a subject is kept for good, and a newer answer
takes its place: it is what the AI reads of an address, what a search is answered with while the
answer is fresh, and what the Threat intelligence page lists as what AresGate knows.
"""

from datetime import datetime
from ipaddress import IPv4Address, IPv6Address

from sqlalchemy import BigInteger, Identity, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime, utcnow


class IntelLookup(Base):
    """One request AresGate made to a threat-intelligence service about a subject. One that failed
    is kept too, since a request that went out counts toward the allowance. An address is kept as
    an address; a domain, or the host of a web address, is kept as its text."""

    __tablename__ = "threat_intel_lookups"
    __table_args__ = (
        Index("ix_threat_intel_lookups_provider_requested_at", "provider", "requested_at"),
        Index("ix_threat_intel_lookups_provider_address", "provider", "address", "requested_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    provider: Mapped[str] = mapped_column(String(32))
    # The address asked about, when the subject is an address; None otherwise.
    address: Mapped[IPv4Address | IPv6Address | None] = mapped_column(INET, default=None)
    # What kind of subject it was: ip, domain or url.
    kind: Mapped[str] = mapped_column(String(8), default="ip")
    # The domain asked about, or the host of a web address; None for an address.
    subject: Mapped[str | None] = mapped_column(String(253), default=None)
    requested_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    # What came of it: pending while it is being asked, then reported, unknown (the service has no
    # report on the address) or failed.
    outcome: Mapped[str] = mapped_column(String(16), default="pending")


class IntelSubject(Base):
    """The last answer a threat-intelligence service gave about one subject: an internet address, a
    domain or a web address. A subject is kept once, so a search or a lookup of it is answered from
    here while the answer is fresh. A web address is kept as the hash of its text, not the text, and
    a subject the service has no report on is kept as unknown, with no counts. The row also keeps
    when the subject was first asked about, how often, and when its judgement last changed."""

    __tablename__ = "threat_intel_subjects"
    __table_args__ = (
        UniqueConstraint("provider", "kind", "subject", name="uq_threat_intel_subjects_subject"),
        Index("ix_threat_intel_subjects_provider_checked_at", "provider", "checked_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    provider: Mapped[str] = mapped_column(String(32))
    # What kind of subject it is: ip, domain or url.
    kind: Mapped[str] = mapped_column(String(8))
    # The address as text, the domain, or the SHA-256 of a web address.
    subject: Mapped[str] = mapped_column(String(253))
    # What the subject is shown as: the address, the domain, or the host of a web address. None for
    # a web address kept before its host was.
    host: Mapped[str | None] = mapped_column(String(253), default=None)
    # When the service was asked about the subject. The answer is fresh for a while after this.
    checked_at: Mapped[datetime] = mapped_column(UTCDateTime)
    # When the service was first asked about the subject, and how many answers it has given since.
    first_checked_at: Mapped[datetime] = mapped_column(UTCDateTime)
    checks: Mapped[int] = mapped_column(Integer, default=1)
    # What the answer comes to: malicious, suspicious, clean or unknown.
    judgement: Mapped[str] = mapped_column(String(16), default="unknown")
    # When a newer answer last changed the judgement, and what it was before. None if it never has.
    changed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    previous_judgement: Mapped[str | None] = mapped_column(String(16), default=None)
    # reported, or unknown when the service has no report on the subject.
    outcome: Mapped[str] = mapped_column(String(16))
    # When the service last analysed the subject, as it says. None when it has no report.
    analysed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    malicious: Mapped[int] = mapped_column(Integer, default=0)
    suspicious: Mapped[int] = mapped_column(Integer, default=0)
    harmless: Mapped[int] = mapped_column(Integer, default=0)
    undetected: Mapped[int] = mapped_column(Integer, default=0)
    # The community's score: below zero leans malicious, above zero leans harmless.
    reputation: Mapped[int] = mapped_column(Integer, default=0)
    country: Mapped[str | None] = mapped_column(String(8), default=None)
    owner: Mapped[str | None] = mapped_column(String(120), default=None)
    asn: Mapped[int | None] = mapped_column(BigInteger, default=None)
    # The categories the engines gave, and what else the service says: each one's label and text.
    categories: Mapped[list[str]] = mapped_column(JSONB, default=list)
    details: Mapped[list[dict[str, str]]] = mapped_column(JSONB, default=list)
