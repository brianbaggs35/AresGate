"""Threat intelligence: the last answer about each subject, in place of the reports of addresses

Revision ID: 0036
Revises: 0035
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0036"
down_revision: str | Sequence[str] | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    # Each of these is made only if it is not there, so applying this again changes nothing.
    op.create_table(
        "threat_intel_subjects",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("subject", sa.String(length=253), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("analysed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("malicious", sa.Integer(), nullable=False),
        sa.Column("suspicious", sa.Integer(), nullable=False),
        sa.Column("harmless", sa.Integer(), nullable=False),
        sa.Column("undetected", sa.Integer(), nullable=False),
        sa.Column("reputation", sa.Integer(), nullable=False),
        sa.Column("country", sa.String(length=8), nullable=True),
        sa.Column("owner", sa.String(length=120), nullable=True),
        sa.Column("asn", sa.BigInteger(), nullable=True),
        sa.Column("categories", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_threat_intel_subjects")),
        sa.UniqueConstraint(
            "provider", "kind", "subject", name=op.f("uq_threat_intel_subjects_subject")
        ),
        if_not_exists=True,
    )
    # The reports kept so far are of addresses. Each is taken as checked when its lookup was asked,
    # so it stays fresh for as long as a lookup is, and is asked about again after that. Once they
    # have been moved, the reports are gone and there is nothing left to move.
    if sa.inspect(op.get_bind()).has_table("threat_intel_reports"):
        op.execute(
            sa.text(
                """
                INSERT INTO threat_intel_subjects (
                    provider, kind, subject, checked_at, outcome, analysed_at, malicious,
                    suspicious, harmless, undetected, reputation, country, owner, asn,
                    categories, details
                )
                SELECT
                    r.provider,
                    'ip',
                    host(r.address),
                    COALESCE(
                        (
                            SELECT max(l.requested_at)
                            FROM threat_intel_lookups l
                            WHERE l.provider = r.provider
                                AND l.address = r.address
                                AND l.outcome = 'reported'
                        ),
                        r.analysed_at
                    ),
                    'reported',
                    r.analysed_at,
                    r.malicious,
                    r.suspicious,
                    r.harmless,
                    r.undetected,
                    r.reputation,
                    r.country,
                    r.owner,
                    r.asn,
                    '[]'::jsonb,
                    '[]'::jsonb
                FROM threat_intel_reports r
                ON CONFLICT (provider, kind, subject) DO NOTHING
                """
            )
        )
    op.drop_table("threat_intel_reports", if_exists=True)


def downgrade() -> None:
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
        if_not_exists=True,
    )
    # Only the answers that reported on an address can be kept as reports of addresses again.
    op.execute(
        sa.text(
            """
            INSERT INTO threat_intel_reports (
                provider, address, analysed_at, malicious, suspicious, harmless, undetected,
                reputation, country, owner, asn
            )
            SELECT
                provider,
                CAST(subject AS inet),
                analysed_at,
                malicious,
                suspicious,
                harmless,
                undetected,
                reputation,
                country,
                owner,
                asn
            FROM threat_intel_subjects
            WHERE kind = 'ip' AND outcome = 'reported' AND analysed_at IS NOT NULL
            ON CONFLICT (provider, address) DO NOTHING
            """
        )
    )
    op.drop_table("threat_intel_subjects", if_exists=True)
