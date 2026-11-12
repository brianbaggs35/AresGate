"""What the owner says each asset is: its kind and its purpose

Revision ID: 0046
Revises: 0045
Create Date: 2026-11-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0046"
down_revision: str | Sequence[str] | None = "0045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    op.create_table(
        "asset_profiles",
        sa.Column("key", sa.String(length=24), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("purpose", sa.String(length=200), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key"),
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_table("asset_profiles", if_exists=True)
