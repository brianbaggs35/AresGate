"""Saved views: the filters and the order of a list, kept under a name for one account."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Identity,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    false,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime, utcnow

PAGES = ("incidents", "alerts", "devices", "assets")


class SavedView(Base):
    """What a list showed, kept under a name by the account that saved it: the page's route query,
    so choosing the view sets it again. One view per page can be the one the page opens on."""

    __tablename__ = "saved_views"
    __table_args__ = (
        CheckConstraint("page IN ('incidents', 'alerts', 'devices', 'assets')", name="page"),
        UniqueConstraint("user_id", "page", "name", name="uq_saved_views_name"),
        # Only one of an account's views of a page is the default.
        Index(
            "uq_saved_views_default",
            "user_id",
            "page",
            unique=True,
            postgresql_where="is_default",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"))
    page: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(60))
    # The route's query: each name with one value or several, as the page wrote them.
    query: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
