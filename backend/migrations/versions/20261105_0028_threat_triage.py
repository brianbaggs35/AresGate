"""Threat triage: families of incidents, the owner's threat settings, duplicate alerts

Revision ID: 0028
Revises: 0027
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0028"
down_revision: str | Sequence[str] | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]

CLASSES = "('compromise', 'attack', 'probe', 'noise', 'unclear')"


def upgrade() -> None:
    op.create_table(
        "incident_families",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("key", sa.String(length=40), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("reach", sa.String(length=8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("owner_call", sa.String(length=10), nullable=True),
        sa.Column("owner_call_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ai_class", sa.String(length=12), nullable=True),
        sa.Column("ai_confidence", sa.SmallInteger(), nullable=True),
        sa.Column("ai_reason", sa.String(length=300), nullable=True),
        sa.Column("judged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("judged_incidents", sa.Integer(), nullable=False),
        sa.Column("call_id", sa.BigInteger(), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.CheckConstraint(
            "reach IN ('internet', 'network', 'rule')", name=op.f("ck_incident_families_reach")
        ),
        sa.CheckConstraint(
            "owner_call IS NULL OR owner_call IN ('background', 'watch')",
            name=op.f("ck_incident_families_owner_call"),
        ),
        sa.CheckConstraint(
            f"ai_class IS NULL OR ai_class IN {CLASSES}", name=op.f("ck_incident_families_ai_class")
        ),
        sa.CheckConstraint(
            "ai_confidence IS NULL OR ai_confidence BETWEEN 0 AND 100",
            name=op.f("ck_incident_families_ai_confidence"),
        ),
        sa.ForeignKeyConstraint(
            ["call_id"],
            ["ai_calls.id"],
            name=op.f("fk_incident_families_call_id_ai_calls"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_incident_families")),
        sa.UniqueConstraint("key", name="uq_incident_families_key"),
        if_not_exists=True,
    )
    op.create_table(
        "threat_settings",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("threat_from", sa.SmallInteger(), nullable=False),
        sa.Column("ai_may_clear", sa.Boolean(), nullable=False),
        sa.Column("clear_from", sa.SmallInteger(), nullable=False),
        sa.Column("ai_confirms", sa.Boolean(), nullable=False),
        sa.Column("exposure", sa.String(length=8), nullable=False),
        sa.Column("exposed_ports", postgresql.ARRAY(sa.Integer()), nullable=False),
        sa.Column("notes", sa.String(length=500), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name=op.f("ck_threat_settings_single_row")),
        sa.CheckConstraint(
            "threat_from BETWEEN 1 AND 100", name=op.f("ck_threat_settings_threat_from")
        ),
        sa.CheckConstraint(
            "clear_from BETWEEN 50 AND 100", name=op.f("ck_threat_settings_clear_from")
        ),
        sa.CheckConstraint(
            "exposure IN ('none', 'some', 'unknown')", name=op.f("ck_threat_settings_exposure")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_threat_settings")),
        if_not_exists=True,
    )

    op.add_column(
        "events", sa.Column("twin_of", sa.BigInteger(), nullable=True), if_not_exists=True
    )
    op.add_column(
        "incident_signals",
        sa.Column("duplicate", sa.Boolean(), server_default=sa.false(), nullable=False),
        if_not_exists=True,
    )
    op.alter_column("incident_signals", "duplicate", server_default=None)

    op.add_column(
        "incidents",
        sa.Column("duplicate_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        if_not_exists=True,
    )
    op.alter_column("incidents", "duplicate_count", server_default=None)
    op.add_column(
        "incidents",
        sa.Column(
            "stages",
            postgresql.ARRAY(sa.String(length=12)),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        if_not_exists=True,
    )
    op.alter_column("incidents", "stages", server_default=None)
    op.add_column(
        "incidents",
        sa.Column("family_key", sa.String(length=40), nullable=True),
        if_not_exists=True,
    )
    op.add_column(
        "incidents", sa.Column("family_id", sa.BigInteger(), nullable=True), if_not_exists=True
    )
    op.add_column(
        "incidents", sa.Column("ai_class", sa.String(length=12), nullable=True), if_not_exists=True
    )
    op.add_column(
        "incidents",
        sa.Column("ai_confidence", sa.SmallInteger(), nullable=True),
        if_not_exists=True,
    )
    op.add_column(
        "incidents", sa.Column("ai_basis", sa.String(length=8), nullable=True), if_not_exists=True
    )
    # Constraints have no IF NOT EXISTS, so a second run drops them first.
    for name in ("ai_basis", "ai_confidence", "ai_class"):
        op.execute(f"ALTER TABLE incidents DROP CONSTRAINT IF EXISTS ck_incidents_{name}")
    op.execute(
        "ALTER TABLE incidents DROP CONSTRAINT IF EXISTS fk_incidents_family_id_incident_families"
    )
    op.create_foreign_key(
        op.f("fk_incidents_family_id_incident_families"),
        "incidents",
        "incident_families",
        ["family_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        op.f("ck_incidents_ai_class"),
        "incidents",
        f"ai_class IS NULL OR ai_class IN {CLASSES}",
    )
    op.create_check_constraint(
        op.f("ck_incidents_ai_confidence"),
        "incidents",
        "ai_confidence IS NULL OR ai_confidence BETWEEN 0 AND 100",
    )
    op.create_check_constraint(
        op.f("ck_incidents_ai_basis"),
        "incidents",
        "ai_basis IS NULL OR ai_basis IN ('owner', 'reading', 'family')",
    )
    op.create_index("ix_incidents_family_id", "incidents", ["family_id"], if_not_exists=True)
    op.create_index("ix_incidents_family_key", "incidents", ["family_key"], if_not_exists=True)


def downgrade() -> None:
    op.drop_index("ix_incidents_family_key", table_name="incidents", if_exists=True)
    op.drop_index("ix_incidents_family_id", table_name="incidents", if_exists=True)
    for name in ("ai_basis", "ai_confidence", "ai_class"):
        op.execute(f"ALTER TABLE incidents DROP CONSTRAINT IF EXISTS ck_incidents_{name}")
    op.execute(
        "ALTER TABLE incidents DROP CONSTRAINT IF EXISTS fk_incidents_family_id_incident_families"
    )
    for column in (
        "ai_basis",
        "ai_confidence",
        "ai_class",
        "family_id",
        "family_key",
        "stages",
        "duplicate_count",
    ):
        op.drop_column("incidents", column, if_exists=True)
    op.drop_column("incident_signals", "duplicate", if_exists=True)
    op.drop_column("events", "twin_of", if_exists=True)
    op.drop_table("threat_settings", if_exists=True)
    op.drop_table("incident_families", if_exists=True)
