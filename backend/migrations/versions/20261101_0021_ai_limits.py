"""AI spending limits: what may be spent in a day and in a month

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | Sequence[str] | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    op.add_column(
        "ai_settings",
        sa.Column("daily_limit_micros", sa.BigInteger(), nullable=True),
        if_not_exists=True,
    )
    op.add_column(
        "ai_settings",
        sa.Column("monthly_limit_micros", sa.BigInteger(), nullable=True),
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_column("ai_settings", "monthly_limit_micros", if_exists=True)
    op.drop_column("ai_settings", "daily_limit_micros", if_exists=True)
