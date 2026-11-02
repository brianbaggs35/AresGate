"""Alerts: where AresGate sends word of what it finds."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Identity, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime, utcnow

# How a destination is reached. Discord's webhooks are the first; others join the list.
KINDS = ("discord",)


class AlertDestination(Base):
    """A place alerts are sent, such as a channel on the owner's Discord server. The address of a
    Discord webhook is a secret (whoever has it can post to the channel), so it is not here: it is
    sealed in the credential store under ``destination-<id>`` and only the code that sends opens
    it. What is kept here is what can be shown without it."""

    __tablename__ = "alert_destinations"
    __table_args__ = (
        CheckConstraint("kind IN ('discord')", name="kind"),
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
