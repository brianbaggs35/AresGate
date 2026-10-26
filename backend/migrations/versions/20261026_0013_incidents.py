"""Incidents: the signals of every integration that belong together

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: str | Sequence[str] | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    op.create_table(
        "incidents",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("subject", sa.String(length=300), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("severity", sa.SmallInteger(), nullable=False),
        sa.Column("confidence", sa.SmallInteger(), nullable=False),
        sa.Column("reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("signal_count", sa.Integer(), nullable=False),
        sa.Column("sources", postgresql.ARRAY(sa.String(length=32)), nullable=False),
        sa.Column("addresses", postgresql.ARRAY(postgresql.INET()), nullable=False),
        sa.Column("top_source", sa.String(length=32), nullable=False),
        sa.Column("top_summary", sa.String(length=500), nullable=False),
        sa.Column("banned", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("severity BETWEEN 0 AND 4", name=op.f("ck_incidents_severity")),
        sa.CheckConstraint("confidence BETWEEN 0 AND 100", name=op.f("ck_incidents_confidence")),
        sa.CheckConstraint(
            "status IN ('open', 'investigating', 'resolved', 'dismissed')",
            name=op.f("ck_incidents_status"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_incidents")),
        if_not_exists=True,
    )
    op.create_index("ix_incidents_last_seen_at", "incidents", ["last_seen_at"], if_not_exists=True)
    op.create_index(
        "ix_incidents_subject_last_seen_at",
        "incidents",
        ["subject", "last_seen_at"],
        if_not_exists=True,
    )
    op.create_table(
        "incident_signals",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("incident_id", sa.BigInteger(), nullable=False),
        sa.Column("event_id", sa.BigInteger(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.SmallInteger(), nullable=False),
        sa.Column("summary", sa.String(length=500), nullable=False),
        sa.Column("signature", sa.String(length=256), nullable=True),
        sa.Column("src_address", postgresql.INET(), nullable=True),
        sa.Column("src_port", sa.Integer(), nullable=True),
        sa.Column("dst_address", postgresql.INET(), nullable=True),
        sa.Column("dst_port", sa.Integer(), nullable=True),
        sa.Column("protocol", sa.String(length=16), nullable=True),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.id"],
            name=op.f("fk_incident_signals_incident_id_incidents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_incident_signals")),
        sa.UniqueConstraint("event_id", name=op.f("uq_incident_signals_event_id")),
        if_not_exists=True,
    )
    op.create_index(
        "ix_incident_signals_incident_id_occurred_at",
        "incident_signals",
        ["incident_id", "occurred_at"],
        if_not_exists=True,
    )


def downgrade() -> None:
    # The indexes go with their tables.
    op.drop_table("incident_signals", if_exists=True)
    op.drop_table("incidents", if_exists=True)
