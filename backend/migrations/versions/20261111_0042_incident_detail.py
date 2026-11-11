"""The AI notes what stands out in what was sent, and signals are read again for more detail

Revision ID: 0042
Revises: 0041
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0042"
down_revision: str | Sequence[str] | None = "0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    op.add_column(
        "ai_triage",
        sa.Column(
            "observations",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        if_not_exists=True,
    )
    op.alter_column("ai_triage", "observations", server_default=None)
    # The programs' records are read for more than they were (the flow's ends, the ports, the
    # score, what was sent), so each signal whose event is still stored is read again, a batch at
    # a time as the engine runs. A signal whose event is gone keeps what it has.
    op.execute(
        sa.text(
            "UPDATE incident_signals AS signal SET evidence = NULL "
            "FROM events AS event "
            "WHERE signal.evidence IS NOT NULL "
            "AND event.id = signal.event_id AND event.occurred_at = signal.occurred_at"
        )
    )


def downgrade() -> None:
    op.drop_column("ai_triage", "observations", if_exists=True)
