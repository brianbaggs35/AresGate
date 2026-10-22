"""The credentials AresGate holds for the things it talks to."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime, utcnow


class StoredCredential(Base):
    """One secret, such as an integration's API key, sealed with the app secret key (see
    app/security/vault.py). Only code that talks to the integration ever opens it: no route
    returns it."""

    __tablename__ = "credentials"
    __table_args__ = (
        UniqueConstraint("kind", "name", "field", name="uq_credentials_kind_name_field"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    # What it is for: an integration, or an AI provider.
    kind: Mapped[str] = mapped_column(String(16))
    # Which one, such as "opnsense", and which of its secrets, such as "api_key".
    name: Mapped[str] = mapped_column(String(64))
    field: Mapped[str] = mapped_column(String(64))
    value_sealed: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
