"""How an account lays out its dashboard."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime, utcnow


class DashboardLayout(Base):
    """The dashboard as one account arranged it: which of the widgets it shows, in what order and
    how wide. There is no row until the owner changes something, and deleting it puts the default
    back. ``preset`` names the preset it started from, or is empty for a layout of their own
    making (app/dashboard_layout.py has the widgets and the presets)."""

    __tablename__ = "dashboard_layouts"

    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    preset: Mapped[str | None] = mapped_column(String(16), default=None)
    # A list of {id, size, hidden}, in the order they are shown.
    widgets: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class DashboardVisit(Base):
    """When one account last looked at the dashboard, so that coming back it can say what is new
    since. It is the server's, not the browser's, so a phone and a computer agree. There is no row
    until the first visit."""

    __tablename__ = "dashboard_visits"

    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    viewed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
