"""Keep the filters and order of a list under a name, for each account

Revision ID: 0070
Revises: 0069
Create Date: 2026-11-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0070"
down_revision: str | Sequence[str] | None = "0069"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    op.create_table(
        "saved_views",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("page", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("query", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "page IN ('incidents', 'alerts', 'devices', 'assets')",
            name=op.f("ck_saved_views_page"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_saved_views_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_saved_views")),
        sa.UniqueConstraint("user_id", "page", "name", name=op.f("uq_saved_views_name")),
        if_not_exists=True,
    )
    op.create_index(
        "uq_saved_views_default",
        "saved_views",
        ["user_id", "page"],
        unique=True,
        postgresql_where=sa.text("is_default"),
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_table("saved_views", if_exists=True)
