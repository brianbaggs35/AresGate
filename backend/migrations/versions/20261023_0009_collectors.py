"""How the collectors are doing, and the worker's heartbeat

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    op.create_table(
        "collector_health",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("collector", sa.String(length=48), nullable=False),
        sa.Column("integration", sa.String(length=32), nullable=False),
        sa.Column("connection", sa.String(length=32), nullable=False),
        sa.Column("interval_seconds", sa.Integer(), nullable=False),
        sa.Column("last_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_duration_ms", sa.Integer(), nullable=True),
        sa.Column("last_items", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_collector_health")),
        sa.UniqueConstraint(
            "collector",
            "integration",
            "connection",
            name=op.f("uq_collector_health_collector"),
        ),
        if_not_exists=True,
    )
    op.create_table(
        "worker_beats",
        sa.Column("name", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("beat_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("name", name=op.f("pk_worker_beats")),
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_table("worker_beats", if_exists=True)
    op.drop_table("collector_health", if_exists=True)
