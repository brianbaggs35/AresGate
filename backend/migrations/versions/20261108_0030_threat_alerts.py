"""Alerts for threats only, and corrections to messages already sent

Revision ID: 0030
Revises: 0029
Create Date: 2026-11-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030"
down_revision: str | Sequence[str] | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    # A destination that exists already keeps the rules it was given; a new one is told of threats.
    op.add_column(
        "alert_destinations",
        sa.Column("mode", sa.String(length=8), server_default="custom", nullable=False),
        if_not_exists=True,
    )
    op.alter_column("alert_destinations", "mode", server_default=None)
    # Postgres can't add a constraint only if it is missing, so each is dropped first: the newest
    # migration has to be able to run again on a database that has it.
    op.drop_constraint(op.f("ck_alert_destinations_mode"), "alert_destinations", if_exists=True)
    op.create_check_constraint(
        op.f("ck_alert_destinations_mode"), "alert_destinations", "mode IN ('threats', 'custom')"
    )

    op.add_column(
        "alert_deliveries",
        sa.Column("message_id", sa.String(length=32), nullable=True),
        if_not_exists=True,
    )
    op.add_column(
        "alert_deliveries",
        sa.Column("target_id", sa.BigInteger(), nullable=True),
        if_not_exists=True,
    )
    op.drop_constraint(
        op.f("fk_alert_deliveries_target_id_alert_deliveries"),
        "alert_deliveries",
        if_exists=True,
    )
    op.create_foreign_key(
        op.f("fk_alert_deliveries_target_id_alert_deliveries"),
        "alert_deliveries",
        "alert_deliveries",
        ["target_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_alert_deliveries_target_id", "alert_deliveries", ["target_id"], if_not_exists=True
    )
    op.drop_constraint(
        op.f("ck_alert_deliveries_kind"), "alert_deliveries", type_="check", if_exists=True
    )
    op.create_check_constraint(
        op.f("ck_alert_deliveries_kind"),
        "alert_deliveries",
        "kind IN ('incident', 'summary', 'update')",
    )
    op.drop_constraint(
        op.f("ck_alert_deliveries_reason"), "alert_deliveries", type_="check", if_exists=True
    )
    op.create_check_constraint(
        op.f("ck_alert_deliveries_reason"),
        "alert_deliveries",
        "reason IN ('new', 'worse', 'reopened', 'limit', 'quiet', 'retract')",
    )


def downgrade() -> None:
    # An update or a retraction has no place in the older table.
    op.execute("DELETE FROM alert_deliveries WHERE kind = 'update'")
    op.drop_constraint(op.f("ck_alert_deliveries_reason"), "alert_deliveries", type_="check")
    op.create_check_constraint(
        op.f("ck_alert_deliveries_reason"),
        "alert_deliveries",
        "reason IN ('new', 'worse', 'reopened', 'limit', 'quiet')",
    )
    op.drop_constraint(op.f("ck_alert_deliveries_kind"), "alert_deliveries", type_="check")
    op.create_check_constraint(
        op.f("ck_alert_deliveries_kind"), "alert_deliveries", "kind IN ('incident', 'summary')"
    )
    op.drop_index("ix_alert_deliveries_target_id", "alert_deliveries", if_exists=True)
    op.drop_constraint(
        op.f("fk_alert_deliveries_target_id_alert_deliveries"),
        "alert_deliveries",
        type_="foreignkey",
    )
    op.drop_column("alert_deliveries", "target_id", if_exists=True)
    op.drop_column("alert_deliveries", "message_id", if_exists=True)
    op.drop_constraint(op.f("ck_alert_destinations_mode"), "alert_destinations", type_="check")
    op.drop_column("alert_destinations", "mode", if_exists=True)
