"""Kinds of incident: a suggestion the owner said not now to

Revision ID: 0053
Revises: 0052
Create Date: 2026-11-13
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0053"
down_revision: str | Sequence[str] | None = "0052"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]

COLUMNS = (("suggestion_dismissed", "VARCHAR(10)"), ("suggestion_dismissed_count", "INTEGER"))


def upgrade() -> None:
    for name, kind in COLUMNS:
        op.execute(f"ALTER TABLE incident_families ADD COLUMN IF NOT EXISTS {name} {kind}")


def downgrade() -> None:
    for name, _ in COLUMNS:
        op.execute(f"ALTER TABLE incident_families DROP COLUMN IF EXISTS {name}")
