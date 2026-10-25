"""Numbers measured over time, in weekly partitions, and how long each source keeps them

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    op.create_table(
        "metric_series",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("connection", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("labels", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_metric_series")),
        sa.UniqueConstraint("fingerprint", name=op.f("uq_metric_series_fingerprint")),
        if_not_exists=True,
    )
    op.create_index(
        "ix_metric_series_source_name", "metric_series", ["source", "name"], if_not_exists=True
    )
    # Only the table the weeks hang from: a week's partition is made when a sample of that week
    # is stored (see app/partitions.py).
    op.create_table(
        "metric_samples",
        sa.Column("series_id", sa.BigInteger(), nullable=False),
        sa.Column("sampled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("value", sa.Double[float](), nullable=False),
        sa.ForeignKeyConstraint(
            ["series_id"],
            ["metric_series.id"],
            name=op.f("fk_metric_samples_series_id_metric_series"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("series_id", "sampled_at", name=op.f("pk_metric_samples")),
        postgresql_partition_by="RANGE (sampled_at)",
        if_not_exists=True,
    )
    op.create_index(
        "ix_metric_samples_source_sampled_at",
        "metric_samples",
        ["source", "sampled_at"],
        if_not_exists=True,
    )
    op.create_table(
        "metric_retention",
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("days", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("days BETWEEN 1 AND 3650", name=op.f("ck_metric_retention_days")),
        sa.PrimaryKeyConstraint("source", name=op.f("pk_metric_retention")),
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_table("metric_retention", if_exists=True)
    # The partitions go with the table they hang from, and the indexes with the table.
    op.drop_table("metric_samples", if_exists=True)
    op.drop_table("metric_series", if_exists=True)
