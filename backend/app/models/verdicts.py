"""Verdicts: what the owner has said about a kind of signal, remembered so it is judged that way
from then on."""

from datetime import datetime
from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network

from sqlalchemy import BigInteger, CheckConstraint, Identity, SmallInteger, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import CIDR, INET
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime, utcnow

# What can be said about a signal. The first two keep it from raising an alarm; the last says it
# is real whatever AresGate made of it.
VERDICTS = ("not_suspicious", "low_priority", "threat")
# Who can give one: the owner, or the AI (app/ai/clearing.py), which says so wherever it is shown.
GIVERS = ("owner", "ai")


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
        CheckConstraint("given_by IN ('owner', 'ai')", name="given_by"),
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
    # Why, in the owner's words (or the AI's, for one it gave).
    note: Mapped[str | None] = mapped_column(String(500), default=None)
    # Who said it: ``owner``, or ``ai`` with its reading: how sure it was, the reason it gave, which
    # provider and model, and the incident it read. The owner's own verdict always wins over one
    # of the AI's, so saying the same thing replaces it and makes it the owner's.
    given_by: Mapped[str] = mapped_column(String(5), default="owner", server_default="owner")
    ai_confidence: Mapped[int | None] = mapped_column(SmallInteger, default=None)
    ai_provider: Mapped[str | None] = mapped_column(String(32), default=None)
    ai_model: Mapped[str | None] = mapped_column(String(128), default=None)
    ai_incident_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class AiClearVeto(Base):
    """A match the owner took back from the AI: it does not give a verdict on the same match again.
    The match is the same columns as a verdict's, and is kept until the owner gives the verdict
    themselves, which is the owner's and wins whatever the AI thinks."""

    __tablename__ = "ai_clear_vetoes"
    __table_args__ = (
        CheckConstraint(
            "address IS NOT NULL OR source IS NOT NULL OR signature IS NOT NULL", name="match"
        ),
        UniqueConstraint(
            "address",
            "source",
            "signature",
            name="uq_ai_clear_vetoes_match",
            postgresql_nulls_not_distinct=True,
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    address: Mapped[IPv4Address | IPv6Address | None] = mapped_column(INET, default=None)
    source: Mapped[str | None] = mapped_column(String(32), default=None)
    signature: Mapped[str | None] = mapped_column(String(256), default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
