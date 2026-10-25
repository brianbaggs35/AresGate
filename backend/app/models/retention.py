"""How long what each integration reported is kept, for the tables that hold a lot of it."""

from datetime import datetime

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime, utcnow


class SourceRetention(Base):
    """How long one source's rows are kept in a table, when that isn't the default. A source
    without a row keeps them for the default that table's setting names. Each table has its own
    subclass, with the check that keeps the days to a sensible range."""

    __abstract__ = True

    source: Mapped[str] = mapped_column(String(32), primary_key=True)
    days: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
