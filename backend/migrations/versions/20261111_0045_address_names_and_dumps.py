"""Names for addresses from reverse lookups, and the data of a packet read again as a dump

Revision ID: 0045
Revises: 0044
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0045"
down_revision: str | Sequence[str] | None = "0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    op.create_table(
        "address_names",
        sa.Column("address", sa.String(length=45), nullable=False),
        sa.Column("name", sa.String(length=253), nullable=True),
        sa.Column("looked_up_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("address"),
        if_not_exists=True,
    )
    # The programs' records are read for the data of the packet too (shown as a dump), so each
    # signal whose event is still stored is read again, a batch at a time as the engine runs. A
    # signal whose event is gone keeps what it has.
    op.execute(
        sa.text(
            "UPDATE incident_signals AS signal SET evidence = NULL "
            "FROM events AS event "
            "WHERE signal.evidence IS NOT NULL "
            "AND event.id = signal.event_id AND event.occurred_at = signal.occurred_at"
        )
    )


def downgrade() -> None:
    op.drop_table("address_names", if_exists=True)
