"""Threat intelligence: what is kept of each subject beyond its last answer

Revision ID: 0037
Revises: 0036
Create Date: 2026-11-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0037"
down_revision: str | Sequence[str] | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]

TABLE = "threat_intel_subjects"
INDEX = "ix_threat_intel_subjects_provider_checked_at"


def upgrade() -> None:
    # Each of these is made only if it is not there, so applying this again changes nothing.
    op.execute(
        sa.text(
            """
            ALTER TABLE threat_intel_subjects
                ADD COLUMN IF NOT EXISTS host varchar(253),
                ADD COLUMN IF NOT EXISTS first_checked_at timestamptz,
                ADD COLUMN IF NOT EXISTS checks integer NOT NULL DEFAULT 1,
                ADD COLUMN IF NOT EXISTS judgement varchar(16) NOT NULL DEFAULT 'unknown',
                ADD COLUMN IF NOT EXISTS changed_at timestamptz,
                ADD COLUMN IF NOT EXISTS previous_judgement varchar(16)
            """
        )
    )
    # What is kept so far was asked about once as far as anyone can tell, and is judged as an answer
    # is judged when it arrives. A web address was kept as a hash alone, so its host stays unknown.
    op.execute(
        sa.text(
            """
            UPDATE threat_intel_subjects
            SET
                first_checked_at = checked_at,
                host = CASE WHEN kind = 'url' THEN NULL ELSE subject END,
                judgement = CASE
                    WHEN outcome <> 'reported' OR analysed_at IS NULL THEN 'unknown'
                    WHEN malicious > 0 THEN 'malicious'
                    WHEN suspicious > 0 THEN 'suspicious'
                    ELSE 'clean'
                END
            WHERE first_checked_at IS NULL
            """
        )
    )
    op.alter_column(TABLE, "first_checked_at", nullable=False)
    op.alter_column(TABLE, "checks", server_default=None)
    op.alter_column(TABLE, "judgement", server_default=None)
    op.create_index(INDEX, TABLE, ["provider", "checked_at"], if_not_exists=True)


def downgrade() -> None:
    op.drop_index(INDEX, table_name=TABLE, if_exists=True)
    op.execute(
        sa.text(
            """
            ALTER TABLE threat_intel_subjects
                DROP COLUMN IF EXISTS previous_judgement,
                DROP COLUMN IF EXISTS changed_at,
                DROP COLUMN IF EXISTS judgement,
                DROP COLUMN IF EXISTS checks,
                DROP COLUMN IF EXISTS first_checked_at,
                DROP COLUMN IF EXISTS host
            """
        )
    )
