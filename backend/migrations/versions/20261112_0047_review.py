"""Reviewing what the AI decided: whether each decision counts yet, the owner's answers and
how they want to review

Revision ID: 0047
Revises: 0046
Create Date: 2026-11-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0047"
down_revision: str | Sequence[str] | None = "0046"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]

REVIEW = "review IN ('pending', 'auto', 'agreed', 'disagreed')"


def upgrade() -> None:
    # What the AI had decided already counts: it is `auto`, and listed to look at.
    for table in ("ai_triage", "incident_families"):
        op.add_column(
            table,
            sa.Column("review", sa.String(length=10), server_default="auto", nullable=False),
            if_not_exists=True,
        )
        op.add_column(
            table,
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            if_not_exists=True,
        )
        op.execute(sa.text(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS ck_{table}_review"))
        op.execute(
            sa.text(f"ALTER TABLE {table} ADD CONSTRAINT ck_{table}_review CHECK ({REVIEW})")
        )
    op.create_table(
        "review_settings",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("mode", sa.String(length=10), nullable=False),
        sa.Column("auto_from", sa.SmallInteger(), nullable=False),
        sa.Column("learn", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name=op.f("ck_review_settings_single_row")),
        sa.CheckConstraint(
            "mode IN ('all', 'uncertain', 'auto')", name=op.f("ck_review_settings_mode")
        ),
        sa.CheckConstraint(
            "auto_from BETWEEN 50 AND 100", name=op.f("ck_review_settings_auto_from")
        ),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_table(
        "review_feedback",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("subject", sa.String(length=10), nullable=False),
        sa.Column("subject_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("ai_class", sa.String(length=12), nullable=False),
        sa.Column("ai_confidence", sa.SmallInteger(), nullable=False),
        sa.Column("answer", sa.String(length=10), nullable=False),
        sa.Column("reason", sa.String(length=300), nullable=True),
        sa.CheckConstraint(
            "subject IN ('incident', 'family')", name=op.f("ck_review_feedback_subject")
        ),
        sa.CheckConstraint(
            "answer IN ('agree', 'disagree')", name=op.f("ck_review_feedback_answer")
        ),
        sa.CheckConstraint(
            "ai_confidence BETWEEN 0 AND 100", name=op.f("ck_review_feedback_ai_confidence")
        ),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_table("review_feedback", if_exists=True)
    op.drop_table("review_settings", if_exists=True)
    for table in ("ai_triage", "incident_families"):
        op.execute(sa.text(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS ck_{table}_review"))
        op.drop_column(table, "reviewed_at", if_exists=True)
        op.drop_column(table, "review", if_exists=True)
