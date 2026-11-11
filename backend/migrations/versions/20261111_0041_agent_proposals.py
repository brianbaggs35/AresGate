"""Agent proposals: what the cleanup agent suggests tidying, and whether it may do the surest itself

Revision ID: 0041
Revises: 0040
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0041"
down_revision: str | Sequence[str] | None = "0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    op.add_column(
        "agent_settings",
        sa.Column("cleanup_mode", sa.String(length=7), nullable=False, server_default="suggest"),
        if_not_exists=True,
    )
    op.alter_column("agent_settings", "cleanup_mode", server_default=None)
    # Applying this again to a database that has it changes nothing.
    op.execute(
        "ALTER TABLE agent_settings DROP CONSTRAINT IF EXISTS ck_agent_settings_cleanup_mode"
    )
    op.create_check_constraint(
        op.f("ck_agent_settings_cleanup_mode"),
        "agent_settings",
        "cleanup_mode IN ('suggest', 'auto')",
    )
    op.create_table(
        "agent_proposals",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("agent_id", sa.BigInteger(), nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=True),
        sa.Column("kind", sa.String(length=12), nullable=False),
        sa.Column("key", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("incident_ids", postgresql.ARRAY(sa.BigInteger()), nullable=False),
        sa.Column("keep_id", sa.BigInteger(), nullable=True),
        sa.Column("confidence", sa.SmallInteger(), nullable=False),
        sa.Column("status", sa.String(length=9), nullable=False),
        sa.Column("decided_by", sa.String(length=5), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("undo", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'applied', 'dismissed', 'undone')",
            name=op.f("ck_agent_proposals_status"),
        ),
        sa.CheckConstraint(
            "confidence BETWEEN 0 AND 100", name=op.f("ck_agent_proposals_confidence")
        ),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["agents.id"],
            name=op.f("fk_agent_proposals_agent_id_agents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["agent_runs.id"],
            name=op.f("fk_agent_proposals_run_id_agent_runs"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_proposals")),
        sa.UniqueConstraint("agent_id", "key", name="uq_agent_proposals_agent_id_key"),
        if_not_exists=True,
    )
    op.create_index(
        "ix_agent_proposals_agent_id_status",
        "agent_proposals",
        ["agent_id", "status"],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_table("agent_proposals", if_exists=True)
    op.execute(
        "ALTER TABLE agent_settings DROP CONSTRAINT IF EXISTS ck_agent_settings_cleanup_mode"
    )
    op.drop_column("agent_settings", "cleanup_mode", if_exists=True)
