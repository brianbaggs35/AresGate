"""What is normal on this network, learned

Revision ID: 0065
Revises: 0064
Create Date: 2026-11-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0065"
down_revision: str | Sequence[str] | None = "0064"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    op.create_table(
        "traffic_baselines",
        sa.Column("series_id", sa.BigInteger(), nullable=False),
        sa.Column("bucket", sa.SmallInteger(), nullable=False),
        sa.Column("samples", sa.Integer(), nullable=False),
        sa.Column("median", sa.Double[float](), nullable=False),
        sa.Column("spread", sa.Double[float](), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("bucket BETWEEN 0 AND 71", name=op.f("ck_traffic_baselines_bucket")),
        sa.ForeignKeyConstraint(
            ["series_id"],
            ["metric_series.id"],
            name=op.f("fk_traffic_baselines_series_id_metric_series"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("series_id", "bucket", name=op.f("pk_traffic_baselines")),
        if_not_exists=True,
    )
    op.create_table(
        "known_destinations",
        sa.Column("client", postgresql.INET(), nullable=False),
        sa.Column("network", postgresql.CIDR(), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hits", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("client", "network", "port", name=op.f("pk_known_destinations")),
        if_not_exists=True,
    )
    op.create_index(
        "ix_known_destinations_last_seen_at",
        "known_destinations",
        ["last_seen_at"],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_table("known_destinations", if_exists=True)
    op.drop_table("traffic_baselines", if_exists=True)
