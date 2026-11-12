"""What was said on the wire is read again from the programs' records

Revision ID: 0048
Revises: 0047
Create Date: 2026-11-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0048"
down_revision: str | Sequence[str] | None = "0047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    # The programs' records are read for the certificate, the request and the lookup of a
    # connection too (shown on the incident page), so each signal whose event is still stored is
    # read again, a batch at a time as the engine runs. A signal whose event is gone keeps what it
    # has.
    op.execute(
        sa.text(
            "UPDATE incident_signals AS signal SET evidence = NULL "
            "FROM events AS event "
            "WHERE signal.evidence IS NOT NULL "
            "AND event.id = signal.event_id AND event.occurred_at = signal.occurred_at"
        )
    )


def downgrade() -> None:
    # Nothing to undo: what was read again is what it would have been.
    pass
