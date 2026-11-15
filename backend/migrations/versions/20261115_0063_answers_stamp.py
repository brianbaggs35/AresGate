"""A stamp that changes with whatever the owner changes, for the answers that are kept briefly

Revision ID: 0063
Revises: 0062
Create Date: 2026-11-15
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0063"
down_revision: str | Sequence[str] | None = "0062"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    # Made again harmlessly where it exists, because the upgrade tests downgrade, stamp and
    # upgrade again.
    op.execute("CREATE SEQUENCE IF NOT EXISTS answers_stamp")


def downgrade() -> None:
    op.execute("DROP SEQUENCE IF EXISTS answers_stamp")
