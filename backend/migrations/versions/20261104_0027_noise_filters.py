"""Noise filters: the owner's settings for what is set aside, and which signals they set aside

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0027"
down_revision: str | Sequence[str] | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    op.create_table(
        "noise_settings",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("confidence_floor", sa.SmallInteger(), nullable=False),
        sa.Column("quiet_inside", sa.Boolean(), nullable=False),
        sa.Column("source_floors", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name=op.f("ck_noise_settings_single_row")),
        sa.CheckConstraint(
            "confidence_floor BETWEEN 1 AND 100", name=op.f("ck_noise_settings_confidence_floor")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_noise_settings")),
        if_not_exists=True,
    )
    op.add_column(
        "incident_signals",
        sa.Column("filtered_by", sa.String(length=16), nullable=True),
        if_not_exists=True,
    )
    op.add_column(
        "incidents",
        sa.Column("filtered_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        if_not_exists=True,
    )
    # The ones that are there have none set aside; new ones are counted by the engine.
    op.alter_column("incidents", "filtered_count", server_default=None)


def downgrade() -> None:
    op.drop_column("incidents", "filtered_count", if_exists=True)
    op.drop_column("incident_signals", "filtered_by", if_exists=True)
    op.drop_table("noise_settings", if_exists=True)
