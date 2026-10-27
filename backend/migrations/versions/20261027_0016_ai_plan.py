"""AI providers: the plan of the account, for the provider whose models depend on it

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | Sequence[str] | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    op.add_column(
        "ai_providers",
        sa.Column("plan", sa.String(length=8), nullable=True),
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_column("ai_providers", "plan", if_exists=True)
