"""Facts about this install that the app itself keeps, such as when it was first set up."""

from datetime import datetime

from sqlalchemy import Sequence, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime, utcnow


class SystemInfo(Base):
    __tablename__ = "system_info"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


# Advanced whenever the owner changes something, so that an answer kept for a few seconds can tell
# that it was built before the change (app/answers.py). A sequence, not a row, because it is not a
# fact about the install, and it can be advanced by any worker without waiting for another.
ANSWERS_STAMP = Sequence("answers_stamp", metadata=Base.metadata)
