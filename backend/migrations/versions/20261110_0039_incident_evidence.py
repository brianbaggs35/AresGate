"""Incident signals keep what the programs reported besides the basics, and which alert a repeat is

Revision ID: 0039
Revises: 0038
Create Date: 2026-11-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0039"
down_revision: str | Sequence[str] | None = "0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    # Each of these is done only if it is not already, so applying this again changes nothing.
    op.add_column(
        "incident_signals",
        sa.Column("twin_of", sa.BigInteger(), nullable=True),
        if_not_exists=True,
    )
    op.add_column(
        "incident_signals",
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        if_not_exists=True,
    )
    # A duplicate already filed says which event it repeats, as far as its event is still stored.
    op.execute(
        sa.text(
            "UPDATE incident_signals AS signal SET twin_of = event.twin_of "
            "FROM events AS event "
            "WHERE signal.duplicate AND signal.twin_of IS NULL "
            "AND event.id = signal.event_id AND event.occurred_at = signal.occurred_at "
            "AND event.twin_of IS NOT NULL"
        )
    )
    op.create_index(
        "ix_incident_signals_evidence_unread",
        "incident_signals",
        ["id"],
        postgresql_where=sa.text("evidence IS NULL"),
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_incident_signals_evidence_unread", "incident_signals", if_exists=True)
    op.drop_column("incident_signals", "evidence", if_exists=True)
    op.drop_column("incident_signals", "twin_of", if_exists=True)
