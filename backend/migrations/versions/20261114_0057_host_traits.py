"""Host traits: what ntopng knows of a host (system, network, country, fingerprints)

Revision ID: 0057
Revises: 0056
Create Date: 2026-11-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0057"
down_revision: str | Sequence[str] | None = "0056"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    op.create_table(
        "host_traits",
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("connection", sa.String(32), nullable=False),
        sa.Column("address", postgresql.INET(), nullable=False),
        sa.Column("hostname", sa.String(253)),
        sa.Column("os_name", sa.String(128)),
        sa.Column("asn", sa.BigInteger()),
        sa.Column("as_name", sa.String(128)),
        sa.Column("country", sa.String(64)),
        sa.Column("fingerprints", postgresql.JSONB(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("source", "connection", "address", name=op.f("pk_host_traits")),
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_table("host_traits")
