"""AI triage: what a provider made of an incident, and how much AI is used unasked

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020"
down_revision: str | Sequence[str] | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    op.add_column(
        "ai_settings",
        sa.Column("usage_level", sa.String(length=10), nullable=False, server_default="medium"),
        if_not_exists=True,
    )
    op.alter_column("ai_settings", "usage_level", server_default=None)
    # A constraint has no `if_not_exists`: it is dropped first, so applying this again changes
    # nothing.
    op.execute("ALTER TABLE ai_settings DROP CONSTRAINT IF EXISTS ck_ai_settings_usage_level")
    op.create_check_constraint(
        op.f("ck_ai_settings_usage_level"),
        "ai_settings",
        "usage_level IN ('very_low', 'low', 'medium', 'high', 'maximum')",
    )
    op.create_table(
        "ai_triage",
        sa.Column("incident_id", sa.BigInteger(), nullable=False),
        sa.Column("call_id", sa.BigInteger(), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("signals_read", sa.Integer(), nullable=False),
        sa.Column("classification", sa.String(length=12), nullable=False),
        sa.Column("confidence", sa.SmallInteger(), nullable=False),
        sa.Column("headline", sa.String(length=160), nullable=False),
        sa.Column("story", sa.Text(), nullable=False),
        sa.Column("checks", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("verdict", sa.String(length=16), nullable=True),
        sa.Column("verdict_reason", sa.String(length=300), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.CheckConstraint(
            "classification IN ('compromise', 'attack', 'probe', 'noise', 'unclear')",
            name=op.f("ck_ai_triage_classification"),
        ),
        sa.CheckConstraint("confidence BETWEEN 0 AND 100", name=op.f("ck_ai_triage_confidence")),
        sa.CheckConstraint(
            "verdict IS NULL OR verdict IN ('not_suspicious', 'low_priority', 'threat')",
            name=op.f("ck_ai_triage_verdict"),
        ),
        sa.ForeignKeyConstraint(
            ["call_id"],
            ["ai_calls.id"],
            name=op.f("fk_ai_triage_call_id_ai_calls"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.id"],
            name=op.f("fk_ai_triage_incident_id_incidents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("incident_id", name=op.f("pk_ai_triage")),
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_table("ai_triage", if_exists=True)
    op.execute("ALTER TABLE ai_settings DROP CONSTRAINT IF EXISTS ck_ai_settings_usage_level")
    op.drop_column("ai_settings", "usage_level", if_exists=True)
