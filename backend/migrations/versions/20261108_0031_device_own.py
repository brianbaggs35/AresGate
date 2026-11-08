"""Assets: which devices are the firewall's own addresses, so that they stay listed

Revision ID: 0031
Revises: 0030
Create Date: 2026-11-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031"
down_revision: str | Sequence[str] | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    # Rows that exist already were listed as neighbours, so they start as not the firewall's own;
    # the next read of the ARP table says which they are.
    op.add_column(
        "device_sources",
        sa.Column("own", sa.Boolean(), server_default=sa.false(), nullable=False),
        if_not_exists=True,
    )
    op.alter_column("device_sources", "own", server_default=None)


def downgrade() -> None:
    op.drop_column("device_sources", "own", if_exists=True)
