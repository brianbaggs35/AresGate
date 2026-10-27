"""Saved searches: a search in words, kept under a name

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | Sequence[str] | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    op.create_table(
        "saved_searches",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("query", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("scope IN ('incidents', 'logs')", name=op.f("ck_saved_searches_scope")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_saved_searches")),
        sa.UniqueConstraint("scope", "name", name=op.f("uq_saved_searches_name")),
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_table("saved_searches", if_exists=True)
