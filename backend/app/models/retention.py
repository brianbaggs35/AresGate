"""How long what each integration reported is kept, for the tables that hold a lot of it."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Integer, SmallInteger, String
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


class RetentionSettings(Base):
    """What the owner chose, on the Retention page, about how long data is kept and how big the
    database may get. There is only ever one row, and none until the owner first saves: without
    one, or with ``managed`` off, nothing here applies and each kind of data is kept for the period
    its own setting gives (see app/retention_policy.py)."""

    __tablename__ = "retention_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="single_row"),
        CheckConstraint("days BETWEEN 1 AND 3650", name="days"),
        CheckConstraint("quota_gb IS NULL OR quota_gb BETWEEN 1 AND 100000", name="quota_gb"),
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1, autoincrement=False)
    # Whether the choices below are used at all. Off, which is how it starts, leaves everything as
    # it was.
    managed: Mapped[bool] = mapped_column(Boolean, default=False)
    # Keep everything, however old and however much: no age limit and no quota.
    keep_forever: Mapped[bool] = mapped_column(Boolean, default=False)
    # How many days data is kept, where it has no period of its own.
    days: Mapped[int] = mapped_column(Integer, default=30)
    # The most the database may hold, in gigabytes, or none: older data goes to make room.
    quota_gb: Mapped[int | None] = mapped_column(BigInteger, default=None)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
