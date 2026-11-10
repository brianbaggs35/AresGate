"""Agents: what they are, each run they made and each step of a run

Revision ID: 0038
Revises: 0037
Create Date: 2026-11-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0038"
down_revision: str | Sequence[str] | None = "0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    # Each of these is made only if it is not there, so applying this again changes nothing.
    op.create_table(
        "agents",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("template", sa.String(length=32), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("interval_minutes", sa.Integer(), nullable=True),
        sa.Column("allow_active", sa.Boolean(), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "interval_minutes IS NULL OR interval_minutes >= 5", name=op.f("ck_agents_interval")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agents")),
        if_not_exists=True,
    )
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("agent_id", sa.BigInteger(), nullable=False),
        sa.Column("trigger", sa.String(length=8), nullable=False),
        sa.Column("status", sa.String(length=9), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("node", sa.String(length=16), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("findings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column("rounds", sa.Integer(), nullable=False),
        sa.Column("ai", sa.String(length=500), nullable=False),
        sa.Column("call_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.CheckConstraint("trigger IN ('manual', 'schedule')", name=op.f("ck_agent_runs_trigger")),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name=op.f("ck_agent_runs_status"),
        ),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["agents.id"],
            name=op.f("fk_agent_runs_agent_id_agents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_runs")),
        if_not_exists=True,
    )
    op.create_index(
        "ix_agent_runs_agent_id_id", "agent_runs", ["agent_id", "id"], if_not_exists=True
    )
    op.create_index("ix_agent_runs_status", "agent_runs", ["status"], if_not_exists=True)
    op.create_table(
        "agent_steps",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("node", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["agent_runs.id"],
            name=op.f("fk_agent_steps_run_id_agent_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_steps")),
        if_not_exists=True,
    )
    op.create_index(
        "ix_agent_steps_run_id_seq", "agent_steps", ["run_id", "seq"], if_not_exists=True
    )


def downgrade() -> None:
    op.drop_table("agent_steps", if_exists=True)
    op.drop_table("agent_runs", if_exists=True)
    op.drop_table("agents", if_exists=True)
