"""Integration connections and the log of the calls made to them

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    op.create_table(
        "integration_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("integration", sa.String(length=32), nullable=False),
        sa.Column("connection", sa.String(length=32), nullable=False),
        sa.Column("base_url", sa.String(length=255), nullable=False),
        sa.Column("tls_mode", sa.String(length=16), nullable=False),
        sa.Column("tls_ca_pem", sa.Text(), nullable=True),
        sa.Column("tls_fingerprint", sa.String(length=95), nullable=True),
        sa.Column("options", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("module_states", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("disabled_modules", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "tls_mode IN ('system', 'ca', 'pinned')",
            name=op.f("ck_integration_connections_tls_mode"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_integration_connections")),
        sa.UniqueConstraint(
            "integration",
            "connection",
            name=op.f("uq_integration_connections_integration_connection"),
        ),
        if_not_exists=True,
    )
    op.create_table(
        "integration_api_calls",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("integration", sa.String(length=32), nullable=False),
        sa.Column("connection", sa.String(length=32), nullable=False),
        sa.Column("method", sa.String(length=8), nullable=False),
        sa.Column("path", sa.String(length=256), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_integration_api_calls")),
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_integration_api_calls_occurred_at"),
        "integration_api_calls",
        ["occurred_at"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_integration_api_calls_integration_id",
        "integration_api_calls",
        ["integration", "id"],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_integration_api_calls_integration_id",
        table_name="integration_api_calls",
        if_exists=True,
    )
    op.drop_index(
        op.f("ix_integration_api_calls_occurred_at"),
        table_name="integration_api_calls",
        if_exists=True,
    )
    op.drop_table("integration_api_calls", if_exists=True)
    op.drop_table("integration_connections", if_exists=True)
