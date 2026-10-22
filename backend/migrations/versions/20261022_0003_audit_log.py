"""The audit log, which the database keeps append-only

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]

APPEND_ONLY_FUNCTION = """
CREATE OR REPLACE FUNCTION audit_events_append_only() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' AND current_setting('aresgate.audit_purge', true) = 'on' THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'The audit log is append-only' USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql
"""
APPEND_ONLY_TRIGGER = """
CREATE TRIGGER audit_events_append_only BEFORE UPDATE OR DELETE ON audit_events
FOR EACH ROW EXECUTE FUNCTION audit_events_append_only()
"""


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("client_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=256), nullable=True),
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.CheckConstraint(
            "outcome IN ('success', 'failure')", name=op.f("ck_audit_events_outcome")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_audit_events_occurred_at"), "audit_events", ["occurred_at"], if_not_exists=True
    )
    op.create_index(op.f("ix_audit_events_action"), "audit_events", ["action"], if_not_exists=True)
    op.execute(APPEND_ONLY_FUNCTION)
    # Applying this migration twice must work, and a trigger can't be created if not exists.
    op.execute("DROP TRIGGER IF EXISTS audit_events_append_only ON audit_events")
    op.execute(APPEND_ONLY_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_events_append_only ON audit_events")
    op.drop_index(op.f("ix_audit_events_action"), table_name="audit_events", if_exists=True)
    op.drop_index(op.f("ix_audit_events_occurred_at"), table_name="audit_events", if_exists=True)
    op.drop_table("audit_events", if_exists=True)
    op.execute("DROP FUNCTION IF EXISTS audit_events_append_only()")
