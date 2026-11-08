"""Verdicts that say where a device's traffic goes

Revision ID: 0032
Revises: 0031
Create Date: 2026-11-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0032"
down_revision: str | Sequence[str] | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]

MATCH = ["address", "source", "signature"]


def upgrade() -> None:
    op.add_column(
        "verdict_rules",
        sa.Column("destination", postgresql.CIDR(), nullable=True),
        if_not_exists=True,
    )
    # Postgres can't change a constraint in place, so each one is dropped first, as 0014 does, and
    # the newest migration can run again on a database that already has it.
    op.drop_constraint(
        op.f("uq_verdict_rules_match"), "verdict_rules", type_="unique", if_exists=True
    )
    op.create_unique_constraint(
        op.f("uq_verdict_rules_match"),
        "verdict_rules",
        [*MATCH, "destination"],
        postgresql_nulls_not_distinct=True,
    )
    op.drop_constraint(
        op.f("ck_verdict_rules_destination"), "verdict_rules", type_="check", if_exists=True
    )
    op.create_check_constraint(
        op.f("ck_verdict_rules_destination"),
        "verdict_rules",
        "destination IS NULL OR address IS NOT NULL",
    )


def downgrade() -> None:
    # A rule that names a destination would be read as one about the whole device, which would
    # mute far more than its owner said, so those rules go with the column.
    op.execute("DELETE FROM verdict_rules WHERE destination IS NOT NULL")
    op.drop_constraint(op.f("ck_verdict_rules_destination"), "verdict_rules", type_="check")
    op.drop_constraint(op.f("uq_verdict_rules_match"), "verdict_rules", type_="unique")
    op.create_unique_constraint(
        op.f("uq_verdict_rules_match"),
        "verdict_rules",
        MATCH,
        postgresql_nulls_not_distinct=True,
    )
    op.drop_column("verdict_rules", "destination")
