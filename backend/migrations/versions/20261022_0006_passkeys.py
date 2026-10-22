"""Passkeys

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    op.create_table(
        "passkeys",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("credential_id", sa.LargeBinary(), nullable=False),
        sa.Column("credential_data", sa.LargeBinary(), nullable=False),
        sa.Column("sign_count", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_passkeys_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_passkeys")),
        sa.UniqueConstraint("credential_id", name=op.f("uq_passkeys_credential_id")),
        if_not_exists=True,
    )
    op.create_table(
        "passkey_challenges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(length=16), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("challenge", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_passkey_challenges_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_passkey_challenges")),
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_table("passkey_challenges", if_exists=True)
    op.drop_table("passkeys", if_exists=True)
