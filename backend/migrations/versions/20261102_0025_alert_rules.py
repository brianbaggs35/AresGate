"""Alert rules: what each destination is told about, and when

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-02
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0025"
down_revision: str | Sequence[str] | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]

CHECKS = (
    ("min_severity", "min_severity BETWEEN 1 AND 4"),
    ("min_confidence", "min_confidence BETWEEN 0 AND 100"),
    ("max_per_hour", "max_per_hour BETWEEN 1 AND 60"),
    ("quiet_from", "quiet_from BETWEEN 0 AND 1439"),
    ("quiet_until", "quiet_until BETWEEN 0 AND 1439"),
    ("detail", "detail IN ('brief', 'standard', 'full')"),
)


def columns() -> list[sa.Column[Any]]:
    """The new columns. A destination that already exists is told what a new one is: only what
    is serious and sure."""
    return [
        sa.Column("min_severity", sa.SmallInteger(), nullable=False, server_default="2"),
        sa.Column("min_confidence", sa.SmallInteger(), nullable=False, server_default="65"),
        sa.Column(
            "sources",
            postgresql.ARRAY(sa.String(length=32)),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "activities",
            postgresql.ARRAY(sa.String(length=16)),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("quiet_hours", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("quiet_from", sa.SmallInteger(), nullable=False, server_default="1320"),
        sa.Column("quiet_until", sa.SmallInteger(), nullable=False, server_default="420"),
        sa.Column("quiet_critical", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("time_zone", sa.String(length=64), nullable=False, server_default="UTC"),
        sa.Column("max_per_hour", sa.SmallInteger(), nullable=False, server_default="6"),
        sa.Column("detail", sa.String(length=16), nullable=False, server_default="standard"),
        sa.Column("again_when_worse", sa.Boolean(), nullable=False, server_default=sa.true()),
    ]


def upgrade() -> None:
    for column in columns():
        op.add_column("alert_destinations", column, if_not_exists=True)
    for name, condition in CHECKS:
        # Postgres can't add a constraint only if it is missing, so it is dropped first: the
        # newest migration has to be able to run again on a database that has it.
        op.drop_constraint(
            op.f(f"ck_alert_destinations_{name}"), "alert_destinations", if_exists=True
        )
        op.create_check_constraint(
            op.f(f"ck_alert_destinations_{name}"), "alert_destinations", condition
        )


def downgrade() -> None:
    # The checks go with their columns.
    for column in reversed(columns()):
        op.drop_column("alert_destinations", column.name, if_exists=True)
