"""The AI providers AresGate may ask, and whether it asks any."""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime, utcnow


class AiProvider(Base):
    """How to reach one AI provider (app/ai/catalog.py names them) and how the last attempt went.
    Its API key is in the credential store (see app/security/credential_store.py), sealed, under
    the provider's key, so a row here holds nothing that has to stay secret. No row means the
    provider isn't set up."""

    __tablename__ = "ai_providers"

    provider: Mapped[str] = mapped_column(String(32), primary_key=True)
    # Where it is, for a provider that runs on the owner's own computer. The others are at one
    # address that the catalog knows.
    base_url: Mapped[str | None] = mapped_column(String(255), default=None)
    model: Mapped[str] = mapped_column(String(128))
    # The plan of the account, for a provider that has plans whose models differ (``free`` or
    # ``paid``), which only its owner can say: nothing the provider answers tells.
    plan: Mapped[str | None] = mapped_column(String(8), default=None)
    # The models that were installed or offered when they were last asked for, for the providers
    # that have no fixed list: each has a name, and may have its size and family.
    models_found: Mapped[list[dict[str, str | int | None]]] = mapped_column(JSONB, default=list)
    models_found_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    # The last time AresGate tried it and the last time that worked. A failure keeps the reason
    # (``last_error``) until the next success.
    last_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    last_success_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    last_error: Mapped[str | None] = mapped_column(String(500), default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class AiSettings(Base):
    """Whether AresGate uses AI, and which provider it asks. There is only ever one row."""

    __tablename__ = "ai_settings"
    __table_args__ = (CheckConstraint("id = 1", name="single_row"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1, autoincrement=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # Forgetting a provider turns it off here rather than leaving a dangling choice.
    provider: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("ai_providers.provider", ondelete="SET NULL"), default=None
    )
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
