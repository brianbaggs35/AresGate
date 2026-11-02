"""Assets: which integration listed each device and how, and the machines with no hardware address

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026"
down_revision: str | Sequence[str] | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    op.create_table(
        "device_sources",
        sa.Column("device_id", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("via", sa.String(length=16), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["devices.id"],
            name=op.f("fk_device_sources_device_id_devices"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("device_id", "source", "via", name=op.f("pk_device_sources")),
        if_not_exists=True,
    )
    op.create_table(
        "host_listings",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("connection", sa.String(length=32), nullable=False),
        sa.Column("via", sa.String(length=16), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("hostname", sa.String(length=253), nullable=True),
        sa.Column("address", postgresql.INET(), nullable=True),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("online", sa.Boolean(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_host_listings")),
        sa.UniqueConstraint("source", "connection", "key", name="uq_host_listings_key"),
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_table("host_listings", if_exists=True)
    op.drop_table("device_sources", if_exists=True)
