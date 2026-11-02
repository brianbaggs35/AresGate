"""Alerts: where AresGate sends word of what it finds."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Identity,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime, utcnow

# How a destination is reached. Discord's webhooks are the first; others join the list.
KINDS = ("discord",)
# How much of an incident a message says (see app/alerts/rules.py).
DETAILS = ("brief", "standard", "full")

# What a new destination is told about: only what is serious (medium or worse) and that
# AresGate is sure of (the "high" band of confidence), at most six messages an hour, and no
# quiet hours until the owner chooses some.
DEFAULT_MIN_SEVERITY = 2
DEFAULT_MIN_CONFIDENCE = 65
DEFAULT_MAX_PER_HOUR = 6
DEFAULT_QUIET_FROM = 22 * 60
DEFAULT_QUIET_UNTIL = 7 * 60
DEFAULT_DETAIL = "standard"


class AlertDestination(Base):
    """A place alerts are sent, such as a channel on the owner's Discord server. The address of a
    Discord webhook is a secret (whoever has it can post to the channel), so it is not here: it is
    sealed in the credential store under ``destination-<id>`` and only the code that sends opens
    it. What is kept here is what can be shown without it."""

    __tablename__ = "alert_destinations"
    __table_args__ = (
        CheckConstraint("kind IN ('discord')", name="kind"),
        CheckConstraint("min_severity BETWEEN 1 AND 4", name="min_severity"),
        CheckConstraint("min_confidence BETWEEN 0 AND 100", name="min_confidence"),
        CheckConstraint("max_per_hour BETWEEN 1 AND 60", name="max_per_hour"),
        CheckConstraint("quiet_from BETWEEN 0 AND 1439", name="quiet_from"),
        CheckConstraint("quiet_until BETWEEN 0 AND 1439", name="quiet_until"),
        CheckConstraint("detail IN ('brief', 'standard', 'full')", name="detail"),
        UniqueConstraint("name", name="uq_alert_destinations_name"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))
    # What the owner calls it, such as "Security channel".
    name: Mapped[str] = mapped_column(String(60))
    # Off keeps it, and its address, without sending anything to it.
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # The end of the webhook's number, so the owner can tell two webhooks apart. Not enough to
    # find the webhook, and it has no part of the token.
    hint: Mapped[str] = mapped_column(String(8), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
    # The last time a message was tried, the last time one got through and why the last one did not.
    last_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    last_success_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    last_error: Mapped[str | None] = mapped_column(String(500), default=None)

    # What it is told about (rules.py decides with these). An incident has to be at least this
    # serious (0 to 4, as in app/events/event.py) and AresGate at least this sure (0 to 100), unless
    # the owner said it is a real threat.
    min_severity: Mapped[int] = mapped_column(SmallInteger, default=DEFAULT_MIN_SEVERITY)
    min_confidence: Mapped[int] = mapped_column(SmallInteger, default=DEFAULT_MIN_CONFIDENCE)
    # Only incidents some of these integrations reported part of, and only these kinds of activity
    # (``scan``, ``brute_force``). None chosen means any.
    sources: Mapped[list[str]] = mapped_column(ARRAY(String(32)), default=list)
    activities: Mapped[list[str]] = mapped_column(ARRAY(String(16)), default=list)
    # Quiet hours: nothing is sent between ``quiet_from`` and ``quiet_until`` (minutes after
    # midnight in ``time_zone``) unless it is critical and ``quiet_critical`` says that gets
    # through. What was held back is sent when they end.
    quiet_hours: Mapped[bool] = mapped_column(Boolean, default=False)
    quiet_from: Mapped[int] = mapped_column(SmallInteger, default=DEFAULT_QUIET_FROM)
    quiet_until: Mapped[int] = mapped_column(SmallInteger, default=DEFAULT_QUIET_UNTIL)
    quiet_critical: Mapped[bool] = mapped_column(Boolean, default=True)
    time_zone: Mapped[str] = mapped_column(String(64), default="UTC")
    # No more than this many messages an hour; the rest are said in one.
    max_per_hour: Mapped[int] = mapped_column(SmallInteger, default=DEFAULT_MAX_PER_HOUR)
    # How much of the network a message tells: see ``DETAILS``.
    detail: Mapped[str] = mapped_column(String(16), default=DEFAULT_DETAIL)
    # Whether an incident it has already told of is told of again when it gets worse.
    again_when_worse: Mapped[bool] = mapped_column(Boolean, default=True)
