"""Agents hand work to each other, and the steps the response planner proposes wait for approval

Revision ID: 0069
Revises: 0068
Create Date: 2026-11-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0069"
down_revision: str | Sequence[str] | None = "0068"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]

AGENT_ID = "agents.id"
RUN_ID = "agent_runs.id"
SET_NULL = "SET NULL"


def upgrade() -> None:
    # A run can now be started by another agent's hand-off. Dropping first lets this be applied a
    # second time.
    op.execute("ALTER TABLE agent_runs DROP CONSTRAINT IF EXISTS ck_agent_runs_trigger")
    op.create_check_constraint(
        op.f("ck_agent_runs_trigger"), "agent_runs", "trigger IN ('manual', 'schedule', 'handoff')"
    )
    op.create_table(
        "agent_handoffs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("from_agent_id", sa.BigInteger(), nullable=False),
        sa.Column("to_kind", sa.String(length=32), nullable=False),
        sa.Column("to_agent_id", sa.BigInteger(), nullable=True),
        sa.Column("to_run_id", sa.BigInteger(), nullable=True),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("incident_id", sa.BigInteger(), nullable=True),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=7), nullable=False),
        sa.Column("refusal", sa.String(length=200), nullable=True),
        sa.Column("depth", sa.SmallInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued', 'refused')", name=op.f("ck_agent_handoffs_status")
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            [RUN_ID],
            name=op.f("fk_agent_handoffs_run_id_agent_runs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["from_agent_id"],
            [AGENT_ID],
            name=op.f("fk_agent_handoffs_from_agent_id_agents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["to_agent_id"],
            [AGENT_ID],
            name=op.f("fk_agent_handoffs_to_agent_id_agents"),
            ondelete=SET_NULL,
        ),
        sa.ForeignKeyConstraint(
            ["to_run_id"],
            [RUN_ID],
            name=op.f("fk_agent_handoffs_to_run_id_agent_runs"),
            ondelete=SET_NULL,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_handoffs")),
        if_not_exists=True,
    )
    for column in ("created_at", "run_id", "to_run_id", "incident_id"):
        op.create_index(
            f"ix_agent_handoffs_{column}", "agent_handoffs", [column], if_not_exists=True
        )
    op.create_table(
        "agent_plan_steps",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("agent_id", sa.BigInteger(), nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=True),
        sa.Column("key", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("risk", sa.Text(), nullable=False),
        sa.Column("incident_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(length=9), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'dismissed')",
            name=op.f("ck_agent_plan_steps_status"),
        ),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            [AGENT_ID],
            name=op.f("fk_agent_plan_steps_agent_id_agents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            [RUN_ID],
            name=op.f("fk_agent_plan_steps_run_id_agent_runs"),
            ondelete=SET_NULL,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_plan_steps")),
        sa.UniqueConstraint("agent_id", "key", name="uq_agent_plan_steps_agent_id_key"),
        if_not_exists=True,
    )
    for column in ("status", "incident_id"):
        op.create_index(
            f"ix_agent_plan_steps_{column}", "agent_plan_steps", [column], if_not_exists=True
        )


def downgrade() -> None:
    op.drop_table("agent_plan_steps", if_exists=True)
    op.drop_table("agent_handoffs", if_exists=True)
    op.execute("DELETE FROM agent_runs WHERE trigger = 'handoff'")
    op.execute("ALTER TABLE agent_runs DROP CONSTRAINT IF EXISTS ck_agent_runs_trigger")
    op.create_check_constraint(
        op.f("ck_agent_runs_trigger"), "agent_runs", "trigger IN ('manual', 'schedule')"
    )
