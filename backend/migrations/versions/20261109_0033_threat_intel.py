"""Threat intelligence: the lookups asked of VirusTotal, and the reports it gave

Revision ID: 0033
Revises: 0032
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0033"
down_revision: str | Sequence[str] | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    op.create_table(
        "threat_intel_lookups",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("address", postgresql.INET(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_threat_intel_lookups")),
    )
    op.create_index(
        "ix_threat_intel_lookups_provider_requested_at",
        "threat_intel_lookups",
        ["provider", "requested_at"],
        unique=False,
    )
    op.create_index(
        "ix_threat_intel_lookups_provider_address",
        "threat_intel_lookups",
        ["provider", "address", "requested_at"],
        unique=False,
    )
    op.create_table(
        "threat_intel_reports",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("address", postgresql.INET(), nullable=False),
        sa.Column("analysed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("malicious", sa.Integer(), nullable=False),
        sa.Column("suspicious", sa.Integer(), nullable=False),
        sa.Column("harmless", sa.Integer(), nullable=False),
        sa.Column("undetected", sa.Integer(), nullable=False),
        sa.Column("reputation", sa.Integer(), nullable=False),
        sa.Column("country", sa.String(length=8), nullable=True),
        sa.Column("owner", sa.String(length=120), nullable=True),
        sa.Column("asn", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_threat_intel_reports")),
        sa.UniqueConstraint("provider", "address", name=op.f("uq_threat_intel_reports_address")),
    )


def downgrade() -> None:
    op.drop_table("threat_intel_reports")
    op.drop_index("ix_threat_intel_lookups_provider_address", table_name="threat_intel_lookups")
    op.drop_index(
        "ix_threat_intel_lookups_provider_requested_at", table_name="threat_intel_lookups"
    )
    op.drop_table("threat_intel_lookups")
