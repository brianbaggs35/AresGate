"""How an account lays out its dashboard

Revision ID: 0064
Revises: 0063
Create Date: 2026-11-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0064"
down_revision: str | Sequence[str] | None = "0063"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    op.create_table(
        "dashboard_layouts",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("preset", sa.String(length=16), nullable=True),
        sa.Column("widgets", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_dashboard_layouts_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_dashboard_layouts")),
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_table("dashboard_layouts", if_exists=True)
