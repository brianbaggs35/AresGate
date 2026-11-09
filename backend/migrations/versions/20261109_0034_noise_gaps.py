"""Noise filters, second pass: how long a scan may pause, and the fewest signals of a thin incident

Revision ID: 0034
Revises: 0033
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034"
down_revision: str | Sequence[str] | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    # The row that is there, if any, takes these defaults; new rows take the model's own.
    op.add_column(
        "noise_settings",
        sa.Column("scan_gap_hours", sa.SmallInteger(), server_default=sa.text("4"), nullable=False),
        if_not_exists=True,
    )
    op.add_column(
        "noise_settings",
        sa.Column(
            "brute_force_gap_hours", sa.SmallInteger(), server_default=sa.text("6"), nullable=False
        ),
        if_not_exists=True,
    )
    op.add_column(
        "noise_settings",
        sa.Column(
            "thin_low_signals", sa.SmallInteger(), server_default=sa.text("1"), nullable=False
        ),
        if_not_exists=True,
    )
    checks = {
        "scan_gap_hours": "scan_gap_hours BETWEEN 1 AND 24",
        "brute_force_gap_hours": "brute_force_gap_hours BETWEEN 1 AND 24",
        "thin_low_signals": "thin_low_signals BETWEEN 1 AND 10",
    }
    for column, condition in checks.items():
        name = op.f(f"ck_noise_settings_{column}")
        # Dropped first if it is there already, so applying this again changes nothing.
        op.drop_constraint(name, "noise_settings", type_="check", if_exists=True)
        op.create_check_constraint(name, "noise_settings", condition)
    for column in ("scan_gap_hours", "brute_force_gap_hours", "thin_low_signals"):
        op.alter_column("noise_settings", column, server_default=None)


def downgrade() -> None:
    # Dropping a column drops the check constraint on it with it.
    op.drop_column("noise_settings", "thin_low_signals", if_exists=True)
    op.drop_column("noise_settings", "brute_force_gap_hours", if_exists=True)
    op.drop_column("noise_settings", "scan_gap_hours", if_exists=True)
