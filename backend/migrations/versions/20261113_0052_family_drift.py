"""Kinds of incident that change after they were judged: what they were like then, and now

Revision ID: 0052
Revises: 0051
Create Date: 2026-11-13
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0052"
down_revision: str | Sequence[str] | None = "0051"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]

COLUMNS = (
    ("judged_profile", "JSONB"),
    ("changes", "JSONB"),
    ("changed_at", "TIMESTAMP WITH TIME ZONE"),
    ("drift_checked_at", "TIMESTAMP WITH TIME ZONE"),
)


def upgrade() -> None:
    for name, kind in COLUMNS:
        op.execute(f"ALTER TABLE incident_families ADD COLUMN IF NOT EXISTS {name} {kind}")


def downgrade() -> None:
    for name, _ in COLUMNS:
        op.execute(f"ALTER TABLE incident_families DROP COLUMN IF EXISTS {name}")
