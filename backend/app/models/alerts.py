"""Alerts: where AresGate sends word of what it finds."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Identity,
    Index,
    Integer,
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

# Why a message was sent: an incident the destination had not heard of, one it had that got worse,
# one that was reopened after it was dealt with, or a summary of what was held back (``limit``: too
# many an hour, ``quiet``: it came in during quiet hours).
DELIVERY_REASONS = ("new", "worse", "reopened", "limit", "quiet")
# Where a message is: waiting (``queued``, ``held`` for quiet hours to end, ``retrying`` after a
# failure, ``limited`` until a summary tells of it), told in a summary (``summarized``), ``sent``,
# given up on (``failed``), or no longer worth sending (``dropped``).
DELIVERY_STATES = (
    "queued",
    "held",
    "retrying",
    "limited",
    "summarized",
    "sent",
    "failed",
    "dropped",
)


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
    # The destination hears of what happens after this and not before: when it was added, or last
    # turned on. Without it a new channel would be sent everything from the last hours at once.
    listening_since: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    # Discord said the webhook is gone or refused it (so trying again can only do harm: repeated
    # refusals count against the address). Nothing is sent until the address is replaced or a
    # test message gets through.
    refused: Mapped[bool] = mapped_column(Boolean, default=False)


class AlertDelivery(Base):
    """One message to one destination, and what became of it: the notifier's outbox and its log.

    An incident is told to a destination once (``key`` ``new``), and again only when it gets worse
    (``worse:<rank>``, a higher severity or confidence band) or is reopened after the owner dealt
    with it (``reopened:<when>``). The unique key is what keeps a retry, a restart or a second
    pass from sending the same thing twice. A summary has no incident: it says how many were held
    back, and the messages it covers point to it with ``summary_id``."""

    __tablename__ = "alert_deliveries"
    __table_args__ = (
        CheckConstraint("kind IN ('incident', 'summary')", name="kind"),
        CheckConstraint("reason IN ('new', 'worse', 'reopened', 'limit', 'quiet')", name="reason"),
        CheckConstraint(
            "state IN ('queued', 'held', 'retrying', 'limited', 'summarized', 'sent', 'failed', "
            "'dropped')",
            name="state",
        ),
        UniqueConstraint("destination_id", "incident_id", "key", name="uq_alert_deliveries_key"),
        Index(
            "ix_alert_deliveries_destination_id_state_due_at", "destination_id", "state", "due_at"
        ),
        Index("ix_alert_deliveries_incident_id", "incident_id"),
        Index("ix_alert_deliveries_created_at", "created_at"),
        Index("ix_alert_deliveries_summary_id", "summary_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    destination_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("alert_destinations.id", ondelete="CASCADE")
    )
    # The incident it is about. Gone with the incident, but the title stays in the log.
    incident_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("incidents.id", ondelete="SET NULL"), default=None
    )
    kind: Mapped[str] = mapped_column(String(8), default="incident")
    reason: Mapped[str] = mapped_column(String(8))
    key: Mapped[str] = mapped_column(String(40))
    state: Mapped[str] = mapped_column(String(12), default="queued")
    # How bad the incident was when this was made: its severity and confidence band as one number
    # (see app/alerts/notify.py), so that a higher one is worse.
    rank: Mapped[int] = mapped_column(SmallInteger, default=0)
    title: Mapped[str] = mapped_column(String(200), default="")
    severity: Mapped[int] = mapped_column(SmallInteger, default=0)
    confidence: Mapped[int] = mapped_column(SmallInteger, default=0)
    # For a summary: how many incidents it tells of. For one of those: the summary that did.
    covers: Mapped[int] = mapped_column(Integer, default=0)
    summary_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("alert_deliveries.id", ondelete="SET NULL"), default=None
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    # When it may be sent: now, when quiet hours end, or when the next try is due.
    due_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    attempts: Mapped[int] = mapped_column(SmallInteger, default=0)
    # Why it is not sent or was not: what Discord answered, or why it was dropped. Holds nothing
    # secret.
    note: Mapped[str | None] = mapped_column(String(500), default=None)
    # Whether it waited for quiet hours to end.
    was_held: Mapped[bool] = mapped_column(Boolean, default=False)
    # When the incident was seen dealt with, after this was made: the next message about it is a
    # reopening.
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
