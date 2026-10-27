"""AI providers: which ones are set up, and whether AresGate uses AI

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015"
down_revision: str | Sequence[str] | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    op.create_table(
        "ai_providers",
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("base_url", sa.String(length=255), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("models_found", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("models_found_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("provider", name=op.f("pk_ai_providers")),
        if_not_exists=True,
    )
    op.create_table(
        "ai_settings",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name=op.f("ck_ai_settings_single_row")),
        sa.ForeignKeyConstraint(
            ["provider"],
            ["ai_providers.provider"],
            name=op.f("fk_ai_settings_provider_ai_providers"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_settings")),
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_table("ai_settings", if_exists=True)
    op.drop_table("ai_providers", if_exists=True)
