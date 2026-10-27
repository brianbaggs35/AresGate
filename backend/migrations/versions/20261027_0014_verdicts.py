"""Verdicts: what the owner has said about a kind of signal

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: str | Sequence[str] | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]

VERDICT_CHECK = "verdict IS NULL OR verdict IN ('not_suspicious', 'low_priority', 'threat')"


def upgrade() -> None:
    op.create_table(
        "verdict_rules",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("verdict", sa.String(length=16), nullable=False),
        sa.Column("address", postgresql.INET(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=True),
        sa.Column("signature", sa.String(length=256), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "verdict IN ('not_suspicious', 'low_priority', 'threat')",
            name=op.f("ck_verdict_rules_verdict"),
        ),
        sa.CheckConstraint(
            "address IS NOT NULL OR source IS NOT NULL OR signature IS NOT NULL",
            name=op.f("ck_verdict_rules_match"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_verdict_rules")),
        sa.UniqueConstraint(
            "address",
            "source",
            "signature",
            name=op.f("uq_verdict_rules_match"),
            postgresql_nulls_not_distinct=True,
        ),
        if_not_exists=True,
    )
    # The incidents that were there before have no verdicts: every signal counts.
    op.add_column(
        "incidents",
        sa.Column(
            "verdict_counts",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        if_not_exists=True,
    )
    op.alter_column("incidents", "verdict_counts", server_default=None)
    op.add_column(
        "incidents",
        sa.Column("verdict", sa.String(length=16), nullable=True),
        if_not_exists=True,
    )
    # Postgres can't add a constraint only if it is missing, so it is dropped first: the newest
    # migration has to be able to run again on a database that has it.
    op.drop_constraint(op.f("ck_incidents_verdict"), "incidents", if_exists=True)
    op.create_check_constraint(op.f("ck_incidents_verdict"), "incidents", VERDICT_CHECK)
    op.add_column(
        "incident_signals",
        sa.Column("verdict", sa.String(length=16), nullable=True),
        if_not_exists=True,
    )
    op.add_column(
        "incident_signals",
        sa.Column("verdict_rule_id", sa.BigInteger(), nullable=True),
        if_not_exists=True,
    )
    op.drop_constraint(op.f("ck_incident_signals_verdict"), "incident_signals", if_exists=True)
    op.create_check_constraint(
        op.f("ck_incident_signals_verdict"), "incident_signals", VERDICT_CHECK
    )
    op.drop_constraint(
        op.f("fk_incident_signals_verdict_rule_id_verdict_rules"),
        "incident_signals",
        if_exists=True,
    )
    op.create_foreign_key(
        op.f("fk_incident_signals_verdict_rule_id_verdict_rules"),
        "incident_signals",
        "verdict_rules",
        ["verdict_rule_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_incident_signals_verdict_rule_id",
        "incident_signals",
        ["verdict_rule_id"],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_incident_signals_verdict_rule_id", "incident_signals", if_exists=True)
    op.drop_constraint(
        op.f("fk_incident_signals_verdict_rule_id_verdict_rules"),
        "incident_signals",
        if_exists=True,
    )
    op.drop_constraint(op.f("ck_incident_signals_verdict"), "incident_signals", if_exists=True)
    op.drop_column("incident_signals", "verdict_rule_id", if_exists=True)
    op.drop_column("incident_signals", "verdict", if_exists=True)
    op.drop_constraint(op.f("ck_incidents_verdict"), "incidents", if_exists=True)
    op.drop_column("incidents", "verdict", if_exists=True)
    op.drop_column("incidents", "verdict_counts", if_exists=True)
    op.drop_table("verdict_rules", if_exists=True)
