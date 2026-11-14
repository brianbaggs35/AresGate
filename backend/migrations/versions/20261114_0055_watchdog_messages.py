"""Watchdog messages: a collector that went quiet is told to the destinations

Revision ID: 0055
Revises: 0054
Create Date: 2026-11-14
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0055"
down_revision: str | Sequence[str] | None = "0054"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]

KIND = "ck_alert_deliveries_kind"
REASON = "ck_alert_deliveries_reason"
KINDS = "'incident', 'summary', 'update'"
REASONS = "'new', 'worse', 'reopened', 'limit', 'quiet', 'retract'"


def upgrade() -> None:
    op.execute(f"ALTER TABLE alert_deliveries DROP CONSTRAINT IF EXISTS {KIND}")
    op.execute(f"ALTER TABLE alert_deliveries DROP CONSTRAINT IF EXISTS {REASON}")
    op.create_check_constraint(op.f(KIND), "alert_deliveries", f"kind IN ({KINDS}, 'watchdog')")
    op.create_check_constraint(
        op.f(REASON), "alert_deliveries", f"reason IN ({REASONS}, 'silent', 'back')"
    )


def downgrade() -> None:
    op.execute("DELETE FROM alert_deliveries WHERE kind = 'watchdog'")
    op.execute(f"ALTER TABLE alert_deliveries DROP CONSTRAINT IF EXISTS {KIND}")
    op.execute(f"ALTER TABLE alert_deliveries DROP CONSTRAINT IF EXISTS {REASON}")
    op.create_check_constraint(op.f(KIND), "alert_deliveries", f"kind IN ({KINDS})")
    op.create_check_constraint(op.f(REASON), "alert_deliveries", f"reason IN ({REASONS})")
