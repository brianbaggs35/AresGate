"""What the National Vulnerability Database says of the CVEs that incidents name

Revision ID: 0050
Revises: 0049
Create Date: 2026-11-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0050"
down_revision: str | Sequence[str] | None = "0049"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    op.create_table(
        "nvd_cves",
        sa.Column("cve_id", sa.String(length=20), nullable=False),
        sa.Column("state", sa.String(length=8), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("modified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cvss_version", sa.String(length=4), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("severity", sa.String(length=8), nullable=True),
        sa.Column("vector", sa.String(length=200), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("weaknesses", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("exploited", sa.Boolean(), nullable=False),
        sa.Column("exploited_on", sa.Date(), nullable=True),
        sa.Column("action_due", sa.Date(), nullable=True),
        sa.Column("required_action", sa.String(length=600), nullable=True),
        sa.Column("kev_name", sa.String(length=200), nullable=True),
        sa.CheckConstraint("state IN ('found', 'unknown')", name=op.f("ck_nvd_cves_state")),
        sa.CheckConstraint(
            "severity IS NULL OR severity IN ('NONE', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name=op.f("ck_nvd_cves_severity"),
        ),
        sa.CheckConstraint(
            "score IS NULL OR score BETWEEN 0 AND 10", name=op.f("ck_nvd_cves_score")
        ),
        sa.PrimaryKeyConstraint("cve_id"),
        if_not_exists=True,
    )
    op.create_index("ix_nvd_cves_checked_at", "nvd_cves", ["checked_at"], if_not_exists=True)


def downgrade() -> None:
    op.drop_table("nvd_cves", if_exists=True)
