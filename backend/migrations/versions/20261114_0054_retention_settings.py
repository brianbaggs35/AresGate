"""Retention settings: how long data is kept and how big the database may get

Revision ID: 0054
Revises: 0053
Create Date: 2026-11-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0054"
down_revision: str | Sequence[str] | None = "0053"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    op.create_table(
        "retention_settings",
        sa.Column("id", sa.SmallInteger(), autoincrement=False, nullable=False),
        sa.Column("managed", sa.Boolean(), nullable=False),
        sa.Column("keep_forever", sa.Boolean(), nullable=False),
        sa.Column("days", sa.Integer(), nullable=False),
        sa.Column("quota_gb", sa.BigInteger(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name=op.f("ck_retention_settings_single_row")),
        sa.CheckConstraint("days BETWEEN 1 AND 3650", name=op.f("ck_retention_settings_days")),
        sa.CheckConstraint(
            "quota_gb IS NULL OR quota_gb BETWEEN 1 AND 100000",
            name=op.f("ck_retention_settings_quota_gb"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_retention_settings")),
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_table("retention_settings", if_exists=True)
