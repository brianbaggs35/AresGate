"""AI verdicts: who gave a verdict, the matches taken back from the AI, and the switch

Revision ID: 0059
Revises: 0058
Create Date: 2026-11-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0059"
down_revision: str | Sequence[str] | None = "0058"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    op.add_column(
        "verdict_rules",
        sa.Column("given_by", sa.String(length=5), server_default="owner", nullable=False),
        if_not_exists=True,
    )
    op.add_column(
        "verdict_rules",
        sa.Column("ai_confidence", sa.SmallInteger(), nullable=True),
        if_not_exists=True,
    )
    op.add_column(
        "verdict_rules",
        sa.Column("ai_provider", sa.String(length=32), nullable=True),
        if_not_exists=True,
    )
    op.add_column(
        "verdict_rules",
        sa.Column("ai_model", sa.String(length=128), nullable=True),
        if_not_exists=True,
    )
    op.add_column(
        "verdict_rules",
        sa.Column("ai_incident_id", sa.BigInteger(), nullable=True),
        if_not_exists=True,
    )
    op.execute(
        sa.text("ALTER TABLE verdict_rules DROP CONSTRAINT IF EXISTS ck_verdict_rules_given_by")
    )
    op.execute(
        sa.text(
            "ALTER TABLE verdict_rules ADD CONSTRAINT ck_verdict_rules_given_by "
            "CHECK (given_by IN ('owner', 'ai'))"
        )
    )
    op.add_column(
        "threat_settings",
        sa.Column("ai_gives_verdicts", sa.Boolean(), server_default=sa.false(), nullable=False),
        if_not_exists=True,
    )
    op.create_table(
        "ai_clear_vetoes",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("address", postgresql.INET(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=True),
        sa.Column("signature", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "address IS NOT NULL OR source IS NOT NULL OR signature IS NOT NULL",
            name=op.f("ck_ai_clear_vetoes_match"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_clear_vetoes")),
        sa.UniqueConstraint(
            "address",
            "source",
            "signature",
            name=op.f("uq_ai_clear_vetoes_match"),
            postgresql_nulls_not_distinct=True,
        ),
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_table("ai_clear_vetoes")
    op.drop_column("threat_settings", "ai_gives_verdicts")
    op.drop_column("verdict_rules", "ai_incident_id")
    op.drop_column("verdict_rules", "ai_model")
    op.drop_column("verdict_rules", "ai_provider")
    op.drop_column("verdict_rules", "ai_confidence")
    op.drop_column("verdict_rules", "given_by")
