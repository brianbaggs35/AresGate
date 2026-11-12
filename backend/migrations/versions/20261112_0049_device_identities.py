"""What each device is, as a device-fingerprinting service says

Revision ID: 0049
Revises: 0048
Create Date: 2026-11-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0049"
down_revision: str | Sequence[str] | None = "0048"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    op.create_table(
        "device_identities",
        sa.Column("device_id", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("state", sa.String(length=10), nullable=False),
        sa.Column("reason", sa.String(length=10), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("path", sa.String(length=600), nullable=True),
        sa.Column("manufacturer", sa.String(length=128), nullable=True),
        sa.Column("operating_system", sa.String(length=128), nullable=True),
        sa.Column("score", sa.SmallInteger(), nullable=True),
        sa.Column("external_id", sa.BigInteger(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('identified', 'unknown', 'private')", name=op.f("ck_device_identities_state")
        ),
        sa.CheckConstraint(
            "reason IN ('asset', 'incident')", name=op.f("ck_device_identities_reason")
        ),
        sa.CheckConstraint(
            "score IS NULL OR score BETWEEN 0 AND 100", name=op.f("ck_device_identities_score")
        ),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("device_id"),
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_table("device_identities", if_exists=True)
