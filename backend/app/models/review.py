"""How the owner reviews what the AI decided, and what they told it."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Identity, Integer, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime, utcnow

# Whose decisions wait for the owner: every one, only those the AI is less than ``auto_from`` sure
# of, or none (the AI decides on its own and the owner looks later, if at all).
REVIEW_MODES = ("all", "uncertain", "auto")
# What the owner can say of a decision.
ANSWERS = ("agree", "disagree")
# What a decision is about: one incident the AI read, or a whole family of them it judged.
SUBJECTS = ("incident", "family")


class ReviewSettings(Base):
    """How much of what the AI decides the owner wants to look at first. There is only ever one
    row, and none until the owner first saves (the defaults are in app/review/settings.py)."""

    __tablename__ = "review_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="single_row"),
        CheckConstraint("mode IN ('all', 'uncertain', 'auto')", name="mode"),
        CheckConstraint("auto_from BETWEEN 50 AND 100", name="auto_from"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1, autoincrement=False)
    mode: Mapped[str] = mapped_column(String(10), default="all")
    # With ``uncertain``: how sure (0 to 100) the AI has to be for a decision to count at once.
    auto_from: Mapped[int] = mapped_column(SmallInteger, default=85)
    # Whether what the owner disagreed with, and why, goes to the AI the next time it decides.
    learn: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class ReviewFeedback(Base):
    """What the owner said of one decision: that they agree or not, and why. It is the record that
    the AI is taught from and that says how much its decisions can be trusted. It is kept until
    the owner clears their activity, and holds no more than the title and the AI's call."""

    __tablename__ = "review_feedback"
    __table_args__ = (
        CheckConstraint("subject IN ('incident', 'family')", name="subject"),
        CheckConstraint("answer IN ('agree', 'disagree')", name="answer"),
        CheckConstraint("ai_confidence BETWEEN 0 AND 100", name="ai_confidence"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    subject: Mapped[str] = mapped_column(String(10))
    # Which incident or family, with no foreign key: the answer outlives what it was about.
    subject_id: Mapped[int] = mapped_column(BigInteger)
    # What it was about, in a line, for the AI to be reminded of.
    title: Mapped[str] = mapped_column(String(200))
    ai_class: Mapped[str] = mapped_column(String(12))
    ai_confidence: Mapped[int] = mapped_column(SmallInteger)
    answer: Mapped[str] = mapped_column(String(10))
    reason: Mapped[str | None] = mapped_column(String(300), default=None)
