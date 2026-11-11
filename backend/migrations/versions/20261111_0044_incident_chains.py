"""Chains: an attack from the internet to a device and out again, across two incidents

Revision ID: 0044
Revises: 0043
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0044"
down_revision: str | Sequence[str] | None = "0043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    op.create_table(
        "incident_chains",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("device", sa.String(length=64), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed", sa.Boolean(), nullable=False),
        sa.Column("steps", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index(
        "ix_incident_chains_device_last_seen_at",
        "incident_chains",
        ["device", "last_seen_at"],
        if_not_exists=True,
    )
    op.add_column(
        "incidents", sa.Column("chain_id", sa.BigInteger(), nullable=True), if_not_exists=True
    )
    op.add_column(
        "incidents", sa.Column("chain_role", sa.String(length=8), nullable=True), if_not_exists=True
    )
    op.add_column(
        "incidents", sa.Column("chain_link", sa.String(length=9), nullable=True), if_not_exists=True
    )
    op.add_column(
        "incidents",
        sa.Column("chain_reason", sa.String(length=300), nullable=True),
        if_not_exists=True,
    )
    op.execute(
        sa.text(
            "DO $$ BEGIN "
            "ALTER TABLE incidents ADD CONSTRAINT fk_incidents_chain_id_incident_chains "
            "FOREIGN KEY (chain_id) REFERENCES incident_chains (id) ON DELETE SET NULL; "
            "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
        )
    )
    op.create_index("ix_incidents_chain_id", "incidents", ["chain_id"], if_not_exists=True)
    op.execute(
        sa.text(
            "DO $$ BEGIN "
            "ALTER TABLE incidents ADD CONSTRAINT ck_incidents_chain_role "
            "CHECK (chain_role IS NULL OR chain_role IN ('attacker', 'callout')); "
            "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
        )
    )
    op.execute(
        sa.text(
            "DO $$ BEGIN "
            "ALTER TABLE incidents ADD CONSTRAINT ck_incidents_chain_link "
            "CHECK (chain_link IS NULL OR chain_link IN ('confirmed', 'inferred')); "
            "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
        )
    )


def downgrade() -> None:
    op.drop_index("ix_incidents_chain_id", table_name="incidents", if_exists=True)
    op.execute(sa.text("ALTER TABLE incidents DROP CONSTRAINT IF EXISTS ck_incidents_chain_link"))
    op.execute(sa.text("ALTER TABLE incidents DROP CONSTRAINT IF EXISTS ck_incidents_chain_role"))
    op.execute(
        sa.text(
            "ALTER TABLE incidents DROP CONSTRAINT IF EXISTS fk_incidents_chain_id_incident_chains"
        )
    )
    for column in ("chain_reason", "chain_link", "chain_role", "chain_id"):
        op.drop_column("incidents", column, if_exists=True)
    op.drop_table("incident_chains", if_exists=True)
