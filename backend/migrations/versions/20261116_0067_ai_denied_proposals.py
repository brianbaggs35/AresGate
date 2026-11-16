"""What the owner denied the assistant, so that it is not proposed again

Revision ID: 0067
Revises: 0066
Create Date: 2026-11-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0067"
down_revision: str | Sequence[str] | None = "0066"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    op.create_table(
        "ai_denied_proposals",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("kind", sa.String(length=7), nullable=False),
        sa.Column("value", sa.String(length=16), nullable=False),
        sa.Column("incident_id", sa.BigInteger(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("denied_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('status', 'verdict')", name=op.f("ck_ai_denied_proposals_kind")
        ),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.id"],
            name=op.f("fk_ai_denied_proposals_incident_id_incidents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_denied_proposals")),
        sa.UniqueConstraint(
            "kind", "value", "incident_id", name=op.f("uq_ai_denied_proposals_change")
        ),
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_table("ai_denied_proposals", if_exists=True)
