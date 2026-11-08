"""Verdicts: what the owner has said about a kind of signal, remembered so it is judged that way
from then on."""

from datetime import datetime
from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network

from sqlalchemy import BigInteger, CheckConstraint, Identity, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import CIDR, INET
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime, utcnow

# What can be said about a signal. The first two keep it from raising an alarm; the last says it
# is real whatever AresGate made of it.
VERDICTS = ("not_suspicious", "low_priority", "threat")


class VerdictRule(Base):
    """A verdict and the signals it applies to: those that name this address, come from this
    program and carry this signature, each only where it is set. The address matches what a
    signal is about, or where it came from, and not where it was going: saying a device is fine
    must not hide the attacks on it. A destination is the one way to say where the device's
    traffic goes: it matches only what that device sends there, so its other traffic, and what is
    sent to it, still counts."""

    __tablename__ = "verdict_rules"
    __table_args__ = (
        CheckConstraint("verdict IN ('not_suspicious', 'low_priority', 'threat')", name="verdict"),
        # A rule that matched everything would mute all of it.
        CheckConstraint(
            "address IS NOT NULL OR source IS NOT NULL OR signature IS NOT NULL", name="match"
        ),
        # A destination is where a device sends its traffic, so it needs the device.
        CheckConstraint("destination IS NULL OR address IS NOT NULL", name="destination"),
        # One verdict for one match: saying it again changes it.
        UniqueConstraint(
            "address",
            "source",
            "signature",
            "destination",
            name="uq_verdict_rules_match",
            postgresql_nulls_not_distinct=True,
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    verdict: Mapped[str] = mapped_column(String(16))
    address: Mapped[IPv4Address | IPv6Address | None] = mapped_column(INET, default=None)
    # Where that address sends its traffic: one address, or a whole network. Only with an address.
    destination: Mapped[IPv4Network | IPv6Network | None] = mapped_column(CIDR, default=None)
    # An integration's key, such as wazuh.
    source: Mapped[str | None] = mapped_column(String(32), default=None)
    signature: Mapped[str | None] = mapped_column(String(256), default=None)
    # Why, in the owner's words.
    note: Mapped[str | None] = mapped_column(String(500), default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
