"""Device importance: which assets matter, and what that does to how threats are ranked

Revision ID: 0058
Revises: 0057
Create Date: 2026-11-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0058"
down_revision: str | Sequence[str] | None = "0057"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    op.add_column(
        "asset_profiles",
        sa.Column("importance", sa.String(length=10), server_default="normal", nullable=False),
        if_not_exists=True,
    )
    op.execute(
        sa.text("ALTER TABLE asset_profiles DROP CONSTRAINT IF EXISTS ck_asset_profiles_importance")
    )
    op.execute(
        sa.text(
            "ALTER TABLE asset_profiles ADD CONSTRAINT ck_asset_profiles_importance "
            "CHECK (importance IN ('normal', 'important', 'critical'))"
        )
    )
    op.add_column(
        "incidents",
        sa.Column("importance", sa.SmallInteger(), server_default="0", nullable=False),
        if_not_exists=True,
    )
    op.add_column(
        "threat_settings",
        sa.Column("important_drop", sa.SmallInteger(), server_default="10", nullable=False),
        if_not_exists=True,
    )
    op.add_column(
        "threat_settings",
        sa.Column("low_raise", sa.SmallInteger(), server_default="0", nullable=False),
        if_not_exists=True,
    )
    for name, rule in (
        ("important_drop", "important_drop BETWEEN 0 AND 30"),
        ("low_raise", "low_raise BETWEEN 0 AND 30"),
    ):
        op.execute(
            sa.text(
                f"ALTER TABLE threat_settings DROP CONSTRAINT IF EXISTS ck_threat_settings_{name}"
            )
        )
        op.execute(
            sa.text(
                f"ALTER TABLE threat_settings ADD CONSTRAINT ck_threat_settings_{name} "
                f"CHECK ({rule})"
            )
        )
    op.execute(sa.text("ALTER TABLE incidents DROP CONSTRAINT IF EXISTS ck_incidents_importance"))
    op.execute(
        sa.text(
            "ALTER TABLE incidents ADD CONSTRAINT ck_incidents_importance "
            "CHECK (importance BETWEEN -1 AND 2)"
        )
    )


def downgrade() -> None:
    op.drop_column("incidents", "importance")
    op.drop_column("threat_settings", "low_raise")
    op.drop_column("threat_settings", "important_drop")
    op.drop_column("asset_profiles", "importance")
