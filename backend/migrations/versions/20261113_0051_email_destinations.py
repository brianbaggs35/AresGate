"""Alerts by email: the mail server's settings and the address of an email destination

Revision ID: 0051
Revises: 0050
Create Date: 2026-11-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0051"
down_revision: str | Sequence[str] | None = "0050"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]

KIND = "ck_alert_destinations_kind"


def upgrade() -> None:
    op.create_table(
        "smtp_settings",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("host", sa.String(length=253), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("security", sa.String(length=8), nullable=False),
        sa.Column("username", sa.String(length=254), nullable=True),
        sa.Column("sender", sa.String(length=254), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name=op.f("ck_smtp_settings_single_row")),
        sa.CheckConstraint("port BETWEEN 1 AND 65535", name=op.f("ck_smtp_settings_port")),
        sa.CheckConstraint(
            "security IN ('starttls', 'ssl', 'none')", name=op.f("ck_smtp_settings_security")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_smtp_settings")),
        if_not_exists=True,
    )
    op.execute("ALTER TABLE alert_destinations ADD COLUMN IF NOT EXISTS recipient VARCHAR(254)")
    op.execute(f"ALTER TABLE alert_destinations DROP CONSTRAINT IF EXISTS {KIND}")
    op.create_check_constraint(KIND, "alert_destinations", "kind IN ('discord', 'email')")


def downgrade() -> None:
    op.execute("DELETE FROM alert_destinations WHERE kind = 'email'")
    op.execute(f"ALTER TABLE alert_destinations DROP CONSTRAINT IF EXISTS {KIND}")
    op.create_check_constraint(KIND, "alert_destinations", "kind IN ('discord')")
    op.execute("ALTER TABLE alert_destinations DROP COLUMN IF EXISTS recipient")
    op.drop_table("smtp_settings", if_exists=True)
