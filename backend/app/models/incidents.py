"""Incidents: the alerts, bans and other signals from every integration that belong together."""

from datetime import datetime
from ipaddress import IPv4Address, IPv6Address
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Identity,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime, utcnow

# What the person who looks after the network has decided about an incident.
STATUSES = ("open", "investigating", "resolved", "dismissed")


class Incident(Base):
    """Signals that belong together: the same address behind a scan that Suricata saw, Wazuh
    logged and CrowdSec banned. It says how serious that is and how sure AresGate is, and keeps
    the reasons, so a person (or the analyst) can see why and disagree.

    It is kept as a summary that grows with each signal, so that working out what a new signal
    changes never means reading the old ones again. The signals themselves are kept beside it
    (``IncidentSignal``) as a timeline, and outlive the events they came from."""

    __tablename__ = "incidents"
    __table_args__ = (
        CheckConstraint("severity BETWEEN 0 AND 4", name="severity"),
        CheckConstraint("confidence BETWEEN 0 AND 100", name="confidence"),
        CheckConstraint(
            "status IN ('open', 'investigating', 'resolved', 'dismissed')", name="status"
        ),
        CheckConstraint(
            "verdict IS NULL OR verdict IN ('not_suspicious', 'low_priority', 'threat')",
            name="verdict",
        ),
        Index("ix_incidents_last_seen_at", "last_seen_at"),
        Index("ix_incidents_subject_last_seen_at", "subject", "last_seen_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    # What the signals are about: the address that is the centre of them (an attacker's, or the
    # device an alert is about), or the rule that fired when they carry no address.
    subject: Mapped[str] = mapped_column(String(300))
    title: Mapped[str] = mapped_column(String(200))
    # The most serious signal's severity, on the scale in app/events/event.py.
    severity: Mapped[int] = mapped_column(SmallInteger)
    # How sure AresGate is that this is a real attack, from 0 to 100, and the reasons it adds up
    # to (see app/incidents/rules.py): a list of {rule, points, text}.
    confidence: Mapped[int] = mapped_column(SmallInteger)
    reasons: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(16), default="open")
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime)
    signal_count: Mapped[int] = mapped_column(Integer, default=0)
    # The integrations whose signals are in it, sorted.
    sources: Mapped[list[str]] = mapped_column(ARRAY(String(32)), default=list)
    # Every address in the signals, the first fifty of them, subject first.
    addresses: Mapped[list[IPv4Address | IPv6Address]] = mapped_column(ARRAY(INET), default=list)
    # Facts about the strongest signal and the rest, kept so scoring needs no old signals.
    top_source: Mapped[str] = mapped_column(String(32))
    top_summary: Mapped[str] = mapped_column(String(500))
    banned: Mapped[bool] = mapped_column(default=False)
    # How many of the signals the owner has a verdict on, by verdict. A signal that is not
    # suspicious or low priority is listed and counted in ``signal_count``, but everything above
    # (the severity, the programs, the addresses) is about the ones that are not.
    verdict_counts: Mapped[dict[str, int]] = mapped_column(JSONB, default=dict)
    # What the verdicts say of the incident as a whole: a real threat if any signal is, not
    # suspicious or low priority if every signal is, and none otherwise.
    verdict: Mapped[str | None] = mapped_column(String(16), default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
    # When someone last changed the status, and nothing before that.
    status_changed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)


class IncidentSignal(Base):
    """One event in an incident's timeline, as it was when it joined: copied, because incidents
    are kept after the events they came from have passed their retention period."""

    __tablename__ = "incident_signals"
    __table_args__ = (
        # An event belongs to one incident.
        UniqueConstraint("event_id", name="uq_incident_signals_event_id"),
        CheckConstraint(
            "verdict IS NULL OR verdict IN ('not_suspicious', 'low_priority', 'threat')",
            name="verdict",
        ),
        Index("ix_incident_signals_incident_id_occurred_at", "incident_id", "occurred_at"),
        Index("ix_incident_signals_verdict_rule_id", "verdict_rule_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    incident_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("incidents.id", ondelete="CASCADE")
    )
    # Which event it was, while that is still stored: its id and time, which are its key.
    event_id: Mapped[int] = mapped_column(BigInteger)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime)
    source: Mapped[str] = mapped_column(String(32))
    kind: Mapped[str] = mapped_column(String(32))
    severity: Mapped[int] = mapped_column(SmallInteger)
    summary: Mapped[str] = mapped_column(String(500))
    signature: Mapped[str | None] = mapped_column(String(256), default=None)
    src_address: Mapped[IPv4Address | IPv6Address | None] = mapped_column(INET, default=None)
    src_port: Mapped[int | None] = mapped_column(Integer, default=None)
    dst_address: Mapped[IPv4Address | IPv6Address | None] = mapped_column(INET, default=None)
    dst_port: Mapped[int | None] = mapped_column(Integer, default=None)
    protocol: Mapped[str | None] = mapped_column(String(16), default=None)
    # What the owner's rules said of it when it joined, and which rule that was while it exists.
    # A verdict stays on a resolved incident as it was, whatever becomes of the rule.
    verdict: Mapped[str | None] = mapped_column(String(16), default=None)
    verdict_rule_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("verdict_rules.id", ondelete="SET NULL"), default=None
    )
