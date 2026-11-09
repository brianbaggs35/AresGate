"""Threat intelligence searches: a domain or a web address is looked up too, not only an address

Revision ID: 0035
Revises: 0034
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0035"
down_revision: str | Sequence[str] | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    # A lookup of a domain or a web address has no address to keep.
    op.alter_column(
        "threat_intel_lookups",
        "address",
        existing_type=postgresql.INET(),
        nullable=True,
    )
    # The lookups kept so far are all of addresses, which the default says.
    op.add_column(
        "threat_intel_lookups",
        sa.Column("kind", sa.String(length=8), server_default=sa.text("'ip'"), nullable=False),
        if_not_exists=True,
    )
    op.add_column(
        "threat_intel_lookups",
        sa.Column("subject", sa.String(length=253), nullable=True),
        if_not_exists=True,
    )
    op.alter_column("threat_intel_lookups", "kind", server_default=None)


def downgrade() -> None:
    # Only the lookups of addresses can be kept once the address is required again.
    op.execute(sa.text("DELETE FROM threat_intel_lookups WHERE address IS NULL"))
    op.drop_column("threat_intel_lookups", "subject", if_exists=True)
    op.drop_column("threat_intel_lookups", "kind", if_exists=True)
    op.alter_column(
        "threat_intel_lookups",
        "address",
        existing_type=postgresql.INET(),
        nullable=False,
    )
