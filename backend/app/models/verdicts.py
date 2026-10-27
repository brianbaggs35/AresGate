"""Verdicts: what the owner has said about a kind of signal, remembered so it is judged that way
from then on."""

from datetime import datetime
from ipaddress import IPv4Address, IPv6Address

from sqlalchemy import BigInteger, CheckConstraint, Identity, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime, utcnow

# What can be said about a signal. The first two keep it from raising an alarm; the last says it
# is real whatever AresGate made of it.
VERDICTS = ("not_suspicious", "low_priority", "threat")


class VerdictRule(Base):
    """A verdict and the signals it applies to: those that name this address, come from this
    program and carry this signature, each only where it is set. The address matches what a
    signal is about, or where it came from, and not where it was going: saying a device is fine
    must not hide the attacks on it."""

    __tablename__ = "verdict_rules"
    __table_args__ = (
        CheckConstraint("verdict IN ('not_suspicious', 'low_priority', 'threat')", name="verdict"),
        # A rule that matched everything would mute all of it.
        CheckConstraint(
            "address IS NOT NULL OR source IS NOT NULL OR signature IS NOT NULL", name="match"
        ),
        # One verdict for one match: saying it again changes it.
        UniqueConstraint(
            "address",
            "source",
            "signature",
            name="uq_verdict_rules_match",
            postgresql_nulls_not_distinct=True,
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    verdict: Mapped[str] = mapped_column(String(16))
    address: Mapped[IPv4Address | IPv6Address | None] = mapped_column(INET, default=None)
    # An integration's key, such as wazuh.
    source: Mapped[str | None] = mapped_column(String(32), default=None)
    signature: Mapped[str | None] = mapped_column(String(256), default=None)
    # Why, in the owner's words.
    note: Mapped[str | None] = mapped_column(String(500), default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
