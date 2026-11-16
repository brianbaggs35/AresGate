"""What the owner lets the AI clear, in a card of its own

The switch for the AI giving verdicts moves from the threat settings to it, and becomes one of three
modes.

Revision ID: 0066
Revises: 0065
Create Date: 2026-11-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0066"
down_revision: str | Sequence[str] | None = "0065"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    op.create_table(
        "ai_clearing_settings",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("mode", sa.String(length=9), server_default="suggest", nullable=False),
        sa.Column("minimum", sa.SmallInteger(), server_default="80", nullable=False),
        sa.Column(
            "classes",
            postgresql.ARRAY(sa.String(length=12)),
            server_default=sa.text("'{noise,probe,unclear}'"),
            nullable=False,
        ),
        sa.Column(
            "sources",
            postgresql.ARRAY(sa.String(length=32)),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("ceiling", sa.String(length=6), server_default="medium", nullable=False),
        sa.Column("daily_cap", sa.SmallInteger(), server_default="25", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name=op.f("ck_ai_clearing_settings_single_row")),
        sa.CheckConstraint(
            "mode IN ('off', 'suggest', 'automatic')", name=op.f("ck_ai_clearing_settings_mode")
        ),
        sa.CheckConstraint(
            "minimum BETWEEN 50 AND 99", name=op.f("ck_ai_clearing_settings_minimum")
        ),
        sa.CheckConstraint(
            "ceiling IN ('low', 'medium', 'high')", name=op.f("ck_ai_clearing_settings_ceiling")
        ),
        sa.CheckConstraint(
            "daily_cap BETWEEN 0 AND 500", name=op.f("ck_ai_clearing_settings_daily_cap")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_clearing_settings")),
        if_not_exists=True,
    )
    # An owner who had turned the AI giving verdicts on keeps it on, as sure as they had asked it
    # to be, and still able to clear what it could (high, short of critical). Run again on a
    # database that has the change, there is no switch left to read.
    columns = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("threat_settings")
    }
    if "ai_gives_verdicts" in columns:
        op.execute(
            """
            INSERT INTO ai_clearing_settings (id, mode, minimum, ceiling, updated_at)
            SELECT 1, 'automatic', LEAST(GREATEST(clear_from, 50), 99), 'high', now()
            FROM threat_settings
            WHERE ai_gives_verdicts
            ON CONFLICT (id) DO NOTHING
            """
        )
    op.drop_column("threat_settings", "ai_gives_verdicts", if_exists=True)


def downgrade() -> None:
    op.add_column(
        "threat_settings",
        sa.Column("ai_gives_verdicts", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.execute(
        """
        UPDATE threat_settings SET ai_gives_verdicts = true
        WHERE EXISTS (SELECT 1 FROM ai_clearing_settings WHERE mode = 'automatic')
        """
    )
    op.drop_table("ai_clearing_settings")
