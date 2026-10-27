"""Saved searches: a search in words, kept under a name to use again."""

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, Identity, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime, utcnow


class SavedSearch(Base):
    """A search and the name it is kept under, for one page: the incidents and the logs each have
    their own, since the words mean different things in each. The words are kept as they were
    typed, so ``since:1h`` is the last hour whenever the search is used."""

    __tablename__ = "saved_searches"
    __table_args__ = (
        CheckConstraint("scope IN ('incidents', 'logs')", name="scope"),
        # Saving under a name again changes the search.
        UniqueConstraint("scope", "name", name="uq_saved_searches_name"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    scope: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(60))
    query: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
