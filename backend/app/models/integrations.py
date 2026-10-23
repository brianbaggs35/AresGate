"""What AresGate knows about the systems it connects to, and the calls it made to them."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime, utcnow


class IntegrationConnection(Base):
    """How to reach one part of an integration, such as OPNsense's API or Wazuh's indexer, and
    how the last attempt went. The secrets it needs are in the credential store (see
    app/security/credential_store.py), under the name ``<integration>-<connection>``, so a row
    here holds nothing that has to stay secret. No row means it isn't connected."""

    __tablename__ = "integration_connections"
    __table_args__ = (
        UniqueConstraint(
            "integration", "connection", name="uq_integration_connections_integration_connection"
        ),
        CheckConstraint("tls_mode IN ('system', 'ca', 'pinned')", name="tls_mode"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    # Which integration, such as "opnsense", and which part of it, such as "api" (app/integrations/
    # registry.py has the names).
    integration: Mapped[str] = mapped_column(String(32))
    connection: Mapped[str] = mapped_column(String(32))
    # The address, as scheme://host:port and nothing after it.
    base_url: Mapped[str] = mapped_column(String(255))
    # How to know it is the right system: the certificates the computer trusts, a certificate
    # authority pasted in (tls_ca_pem), or one certificate's SHA-256 fingerprint (tls_fingerprint).
    tls_mode: Mapped[str] = mapped_column(String(16), default="system")
    tls_ca_pem: Mapped[str | None] = mapped_column(Text, default=None)
    tls_fingerprint: Mapped[str | None] = mapped_column(String(95), default=None)
    # The settings that aren't secret, such as a user name or an interface number.
    options: Mapped[dict[str, str | int]] = mapped_column(JSONB, default=dict)
    # What testing found of the services that run on the system, such as Suricata on OPNsense:
    # each module's key and state. And the modules AresGate has been told to leave alone.
    module_states: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    disabled_modules: Mapped[list[str]] = mapped_column(JSONB, default=list)
    # The last time AresGate tried it, and the last time that worked. A failure keeps the reason
    # (``last_error``) until the next success.
    last_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    last_success_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    last_error: Mapped[str | None] = mapped_column(String(500), default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class ApiCall(Base):
    """One request AresGate made to an integration: when, what, how it ended and how long it
    took. It never holds a secret or a query string, and what the integration said is kept to
    a short description, because that text is the integration's own and can't be trusted."""

    __tablename__ = "integration_api_calls"
    __table_args__ = (Index("ix_integration_api_calls_integration_id", "integration", "id"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    integration: Mapped[str] = mapped_column(String(32))
    connection: Mapped[str] = mapped_column(String(32))
    method: Mapped[str] = mapped_column(String(8))
    # The path only: no host, query string or fragment.
    path: Mapped[str] = mapped_column(String(256))
    # None when no answer came (it couldn't connect, or wasn't allowed to).
    status_code: Mapped[int | None] = mapped_column(Integer, default=None)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(500), default=None)
