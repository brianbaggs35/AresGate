"""The owner can rule a threat-intelligence subject safe or suspicious

Revision ID: 0043
Revises: 0042
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0043"
down_revision: str | Sequence[str] | None = "0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    op.create_table(
        "threat_intel_overrides",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("subject", sa.String(length=253), nullable=False),
        sa.Column("host", sa.String(length=253), nullable=False),
        sa.Column("verdict", sa.String(length=12), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("set_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kind", "subject", name="uq_threat_intel_overrides_subject"),
    )


def downgrade() -> None:
    op.drop_table("threat_intel_overrides")
