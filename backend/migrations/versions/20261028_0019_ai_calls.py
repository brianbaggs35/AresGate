"""AI calls and stand-ins: what was asked of a provider, and the names it was shown instead

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | Sequence[str] | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    op.add_column(
        "ai_settings",
        sa.Column("redaction", sa.String(length=8), nullable=False, server_default="balanced"),
        if_not_exists=True,
    )
    op.alter_column("ai_settings", "redaction", server_default=None)
    op.create_check_constraint(
        op.f("ck_ai_settings_redaction"),
        "ai_settings",
        "redaction IN ('strict', 'balanced', 'local')",
    )
    op.create_table(
        "ai_aliases",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("value", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_aliases")),
        sa.UniqueConstraint("kind", "value", name=op.f("uq_ai_aliases_value")),
        if_not_exists=True,
    )
    op.create_table(
        "ai_calls",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("purpose", sa.String(length=24), nullable=False),
        sa.Column("about", sa.String(length=120), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("level", sa.String(length=8), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cached_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_write_tokens", sa.Integer(), nullable=False),
        sa.Column("reasoning_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_micros", sa.BigInteger(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("truncated", sa.Boolean(), nullable=False),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_calls")),
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_ai_calls_occurred_at"), "ai_calls", ["occurred_at"], if_not_exists=True
    )
    op.create_index("ix_ai_calls_purpose_id", "ai_calls", ["purpose", "id"], if_not_exists=True)


def downgrade() -> None:
    op.drop_table("ai_calls", if_exists=True)
    op.drop_table("ai_aliases", if_exists=True)
    op.drop_constraint(op.f("ck_ai_settings_redaction"), "ai_settings", type_="check")
    op.drop_column("ai_settings", "redaction", if_exists=True)
