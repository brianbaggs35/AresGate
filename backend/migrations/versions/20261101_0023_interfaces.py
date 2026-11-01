"""Interfaces: parts of the network, the feeds placed on them, and the port of an event

Revision ID: 0023
Revises: 0018
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0023"
down_revision: str | Sequence[str] | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    op.create_table(
        "interfaces",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("notes", sa.String(length=300), nullable=False),
        sa.Column("networks", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "role IN ('internet', 'dmz', 'home', 'guest', 'iot', 'vpn', 'management', 'other')",
            name=op.f("ck_interfaces_role"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_interfaces")),
        sa.UniqueConstraint("name", name="uq_interfaces_name"),
        if_not_exists=True,
    )
    op.create_table(
        "interface_feeds",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("integration", sa.String(length=32), nullable=False),
        sa.Column("connection", sa.String(length=32), nullable=False),
        sa.Column("native_name", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("detail", sa.String(length=200), nullable=False),
        sa.Column("interface_id", sa.BigInteger(), nullable=True),
        sa.Column("ignored", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "NOT (ignored AND interface_id IS NOT NULL)",
            name=op.f("ck_interface_feeds_placed_or_ignored"),
        ),
        sa.ForeignKeyConstraint(
            ["interface_id"],
            ["interfaces.id"],
            name=op.f("fk_interface_feeds_interface_id_interfaces"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_interface_feeds")),
        sa.UniqueConstraint(
            "integration", "connection", "native_name", name="uq_interface_feeds_name"
        ),
        if_not_exists=True,
    )
    op.add_column(
        "events",
        sa.Column("iface", sa.String(length=64), nullable=True),
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_column("events", "iface", if_exists=True)
    op.drop_table("interface_feeds", if_exists=True)
    op.drop_table("interfaces", if_exists=True)
