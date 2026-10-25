"""The devices seen on the network, and the addresses they have had

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    op.create_table(
        "devices",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("mac", postgresql.MACADDR(), nullable=False),
        sa.Column("hostname", sa.String(length=253), nullable=True),
        sa.Column("vendor", sa.String(length=128), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_devices")),
        sa.UniqueConstraint("mac", name=op.f("uq_devices_mac")),
        if_not_exists=True,
    )
    op.create_table(
        "device_addresses",
        sa.Column("device_id", sa.BigInteger(), nullable=False),
        sa.Column("address", postgresql.INET(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["devices.id"],
            name=op.f("fk_device_addresses_device_id_devices"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("device_id", "address", name=op.f("pk_device_addresses")),
        if_not_exists=True,
    )
    op.create_index(
        "ix_device_addresses_address", "device_addresses", ["address"], if_not_exists=True
    )


def downgrade() -> None:
    # The indexes go with their tables.
    op.drop_table("device_addresses", if_exists=True)
    op.drop_table("devices", if_exists=True)
