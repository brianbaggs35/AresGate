"""Partial indexes for what the dashboard reads of alerts and of refused connections

Revision ID: 0062
Revises: 0061
Create Date: 2026-11-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0062"
down_revision: str | Sequence[str] | None = "0061"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    # On the partitioned table, so every week has them, the ones made later included. They are
    # made again harmlessly where they exist, because the upgrade tests downgrade, stamp and
    # upgrade again.
    op.create_index(
        "ix_events_alert_occurred_at",
        "events",
        ["occurred_at"],
        postgresql_include=[
            "source",
            "severity",
            "signature",
            "summary",
            "src_address",
            "dst_address",
            "dst_port",
            "protocol",
            "twin_of",
        ],
        postgresql_where=sa.text("kind = 'alert'"),
        if_not_exists=True,
    )
    op.create_index(
        "ix_events_block_occurred_at",
        "events",
        ["occurred_at"],
        postgresql_include=["src_address", "dst_address", "dst_port"],
        postgresql_where=sa.text("kind = 'firewall' AND severity >= 1"),
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_events_block_occurred_at", table_name="events", if_exists=True)
    op.drop_index("ix_events_alert_occurred_at", table_name="events", if_exists=True)
