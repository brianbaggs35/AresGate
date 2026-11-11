"""Agent settings (which AI the agents ask, and what they may spend) and what each run used

Revision ID: 0040
Revises: 0039
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0040"
down_revision: str | Sequence[str] | None = "0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]

# What a run used of the AI. A run that was over before this has used none that is known.
USAGE = (
    ("calls", sa.Integer()),
    ("input_tokens", sa.Integer()),
    ("output_tokens", sa.Integer()),
    ("cached_tokens", sa.Integer()),
    ("cost_micros", sa.BigInteger()),
    ("unpriced_calls", sa.Integer()),
)


def upgrade() -> None:
    op.create_table(
        "agent_settings",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("ai_source", sa.String(length=6), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("daily_limit_micros", sa.BigInteger(), nullable=True),
        sa.Column("monthly_limit_micros", sa.BigInteger(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name=op.f("ck_agent_settings_single_row")),
        sa.CheckConstraint(
            "ai_source IN ('shared', 'own', 'off')", name=op.f("ck_agent_settings_ai_source")
        ),
        sa.ForeignKeyConstraint(
            ["provider"],
            ["ai_providers.provider"],
            name=op.f("fk_agent_settings_provider_ai_providers"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_settings")),
        if_not_exists=True,
    )
    for name, kind in USAGE:
        op.add_column(
            "agent_runs",
            sa.Column(name, kind, nullable=False, server_default="0"),
            if_not_exists=True,
        )
        op.alter_column("agent_runs", name, server_default=None)
    op.add_column(
        "agent_runs",
        sa.Column("provider", sa.String(length=32), nullable=True),
        if_not_exists=True,
    )
    op.add_column(
        "agent_runs",
        sa.Column("model", sa.String(length=128), nullable=True),
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_column("agent_runs", "model", if_exists=True)
    op.drop_column("agent_runs", "provider", if_exists=True)
    for name, _ in USAGE:
        op.drop_column("agent_runs", name, if_exists=True)
    op.drop_table("agent_settings", if_exists=True)
