"""The notifier's outbox and delivery log

Revision ID: 0029
Revises: 0028
Create Date: 2026-11-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029"
down_revision: str | Sequence[str] | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]

STATES = "('queued', 'held', 'retrying', 'limited', 'summarized', 'sent', 'failed', 'dropped')"


def upgrade() -> None:
    # A destination that exists already hears of what happens from now on.
    op.add_column(
        "alert_destinations",
        sa.Column(
            "listening_since",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        if_not_exists=True,
    )
    op.alter_column("alert_destinations", "listening_since", server_default=None)
    op.add_column(
        "alert_destinations",
        sa.Column("refused", sa.Boolean(), server_default=sa.false(), nullable=False),
        if_not_exists=True,
    )
    op.alter_column("alert_destinations", "refused", server_default=None)

    op.create_table(
        "alert_deliveries",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("destination_id", sa.BigInteger(), nullable=False),
        sa.Column("incident_id", sa.BigInteger(), nullable=True),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("reason", sa.String(length=8), nullable=False),
        sa.Column("key", sa.String(length=40), nullable=False),
        sa.Column("state", sa.String(length=12), nullable=False),
        sa.Column("rank", sa.SmallInteger(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("severity", sa.SmallInteger(), nullable=False),
        sa.Column("confidence", sa.SmallInteger(), nullable=False),
        sa.Column("covers", sa.Integer(), nullable=False),
        sa.Column("summary_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.SmallInteger(), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("was_held", sa.Boolean(), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('incident', 'summary')", name=op.f("ck_alert_deliveries_kind")
        ),
        sa.CheckConstraint(
            "reason IN ('new', 'worse', 'reopened', 'limit', 'quiet')",
            name=op.f("ck_alert_deliveries_reason"),
        ),
        sa.CheckConstraint(f"state IN {STATES}", name=op.f("ck_alert_deliveries_state")),
        sa.ForeignKeyConstraint(
            ["destination_id"],
            ["alert_destinations.id"],
            name=op.f("fk_alert_deliveries_destination_id_alert_destinations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.id"],
            name=op.f("fk_alert_deliveries_incident_id_incidents"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["summary_id"],
            ["alert_deliveries.id"],
            name=op.f("fk_alert_deliveries_summary_id_alert_deliveries"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alert_deliveries")),
        sa.UniqueConstraint("destination_id", "incident_id", "key", name="uq_alert_deliveries_key"),
        if_not_exists=True,
    )
    op.create_index(
        "ix_alert_deliveries_destination_id_state_due_at",
        "alert_deliveries",
        ["destination_id", "state", "due_at"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_alert_deliveries_incident_id", "alert_deliveries", ["incident_id"], if_not_exists=True
    )
    op.create_index(
        "ix_alert_deliveries_created_at", "alert_deliveries", ["created_at"], if_not_exists=True
    )
    op.create_index(
        "ix_alert_deliveries_summary_id", "alert_deliveries", ["summary_id"], if_not_exists=True
    )


def downgrade() -> None:
    op.drop_table("alert_deliveries", if_exists=True)
    op.drop_column("alert_destinations", "refused", if_exists=True)
    op.drop_column("alert_destinations", "listening_since", if_exists=True)
