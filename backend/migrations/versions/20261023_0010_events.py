"""Normalized events, in weekly partitions, and how long each source keeps them

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    # Only the table the weeks hang from: a week's partition is made when an event of that week
    # is stored (see app/events/partitions.py).
    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("connection", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.SmallInteger(), nullable=False),
        sa.Column("summary", sa.String(length=500), nullable=False),
        sa.Column("signature", sa.String(length=256), nullable=True),
        sa.Column("src_address", postgresql.INET(), nullable=True),
        sa.Column("src_port", sa.Integer(), nullable=True),
        sa.Column("dst_address", postgresql.INET(), nullable=True),
        sa.Column("dst_port", sa.Integer(), nullable=True),
        sa.Column("protocol", sa.String(length=16), nullable=True),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.CheckConstraint("severity BETWEEN 0 AND 4", name=op.f("ck_events_severity")),
        sa.CheckConstraint("src_port BETWEEN 0 AND 65535", name=op.f("ck_events_src_port")),
        sa.CheckConstraint("dst_port BETWEEN 0 AND 65535", name=op.f("ck_events_dst_port")),
        sa.PrimaryKeyConstraint("occurred_at", "id", name=op.f("pk_events")),
        sa.UniqueConstraint(
            "source", "fingerprint", "occurred_at", name=op.f("uq_events_fingerprint")
        ),
        postgresql_partition_by="RANGE (occurred_at)",
        if_not_exists=True,
    )
    op.create_index(
        "ix_events_source_occurred_at", "events", ["source", "occurred_at"], if_not_exists=True
    )
    op.create_index(
        "ix_events_src_address_occurred_at",
        "events",
        ["src_address", "occurred_at"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_events_dst_address_occurred_at",
        "events",
        ["dst_address", "occurred_at"],
        if_not_exists=True,
    )
    op.create_table(
        "event_retention",
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("days", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("days BETWEEN 1 AND 3650", name=op.f("ck_event_retention_days")),
        sa.PrimaryKeyConstraint("source", name=op.f("pk_event_retention")),
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_table("event_retention", if_exists=True)
    # The partitions go with the table they hang from, and the indexes with the table.
    op.drop_table("events", if_exists=True)
