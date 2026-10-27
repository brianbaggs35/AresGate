"""Incidents: the block of the subject, the activities, the waves and the ports

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017"
down_revision: str | Sequence[str] | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    op.add_column(
        "incidents",
        sa.Column("block", sa.String(length=64), nullable=True),
        if_not_exists=True,
    )
    # The incidents that were there before have none of it worked out: no waves says so, and the
    # engine fills it in from their signals on its next run.
    op.add_column(
        "incidents",
        sa.Column(
            "activities",
            postgresql.ARRAY(sa.String(length=16)),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        if_not_exists=True,
    )
    op.alter_column("incidents", "activities", server_default=None)
    op.add_column(
        "incidents",
        sa.Column("waves", sa.Integer(), nullable=False, server_default=sa.text("0")),
        if_not_exists=True,
    )
    op.alter_column("incidents", "waves", server_default=None)
    op.add_column(
        "incidents",
        sa.Column(
            "ports",
            postgresql.ARRAY(sa.Integer()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        if_not_exists=True,
    )
    op.alter_column("incidents", "ports", server_default=None)
    op.create_index(
        "ix_incidents_block_last_seen_at",
        "incidents",
        ["block", "last_seen_at"],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_incidents_block_last_seen_at", "incidents", if_exists=True)
    op.drop_column("incidents", "ports", if_exists=True)
    op.drop_column("incidents", "waves", if_exists=True)
    op.drop_column("incidents", "activities", if_exists=True)
    op.drop_column("incidents", "block", if_exists=True)
