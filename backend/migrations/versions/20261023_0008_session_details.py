"""Where each sign-in came from

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    # Sign-ins made before this have nothing to show, so both are optional.
    op.add_column("user_sessions", sa.Column("address", sa.String(length=64), nullable=True))
    op.add_column("user_sessions", sa.Column("user_agent", sa.String(length=256), nullable=True))


def downgrade() -> None:
    op.drop_column("user_sessions", "user_agent")
    op.drop_column("user_sessions", "address")
