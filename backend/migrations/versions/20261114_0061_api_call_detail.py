"""Everything about a request in the API log, so an entry can be opened

Revision ID: 0061
Revises: 0060
Create Date: 2026-11-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0061"
down_revision: str | Sequence[str] | None = "0060"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    op.add_column(
        "integration_api_calls",
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        if_not_exists=True,
    )
    op.add_column(
        "integration_api_calls", sa.Column("excerpt", sa.Text(), nullable=True), if_not_exists=True
    )


def downgrade() -> None:
    op.drop_column("integration_api_calls", "excerpt", if_exists=True)
    op.drop_column("integration_api_calls", "detail", if_exists=True)
