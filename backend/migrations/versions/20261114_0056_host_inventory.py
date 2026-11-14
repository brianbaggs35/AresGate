"""Host inventory: what an agent reports about its machine's system, ports and software

Revision ID: 0056
Revises: 0055
Create Date: 2026-11-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0056"
down_revision: str | Sequence[str] | None = "0055"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
# Alembic reads these by name, so they're exported, which also tells CodeQL they're used.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]

KEY = ("source", "connection", "agent_id")
REFERENCE = ["host_systems.source", "host_systems.connection", "host_systems.agent_id"]


def upgrade() -> None:
    op.create_table(
        "host_systems",
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("connection", sa.String(32), nullable=False),
        sa.Column("agent_id", sa.String(128), nullable=False),
        sa.Column("name", sa.String(253)),
        sa.Column("hostname", sa.String(253)),
        sa.Column("os_name", sa.String(128)),
        sa.Column("os_version", sa.String(64)),
        sa.Column("os_platform", sa.String(32)),
        sa.Column("architecture", sa.String(32)),
        sa.Column("kernel", sa.String(128)),
        sa.Column("macs", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("addresses", postgresql.ARRAY(postgresql.INET()), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(*KEY, name=op.f("pk_host_systems")),
    )
    op.create_table(
        "host_ports",
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("connection", sa.String(32), nullable=False),
        sa.Column("agent_id", sa.String(128), nullable=False),
        sa.Column("transport", sa.String(8), nullable=False),
        sa.Column("address", postgresql.INET(), nullable=False),
        sa.Column("port", sa.BigInteger(), nullable=False),
        sa.Column("process", sa.String(128)),
        sa.PrimaryKeyConstraint(*KEY, "transport", "address", "port", name=op.f("pk_host_ports")),
        sa.ForeignKeyConstraint(
            KEY,
            REFERENCE,
            name=op.f("fk_host_ports_source_host_systems"),
            ondelete="CASCADE",
        ),
    )
    op.create_table(
        "host_packages",
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("connection", sa.String(32), nullable=False),
        sa.Column("agent_id", sa.String(128), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("version", sa.String(128), nullable=False),
        sa.Column("architecture", sa.String(32), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.PrimaryKeyConstraint(
            *KEY, "name", "version", "architecture", "kind", name=op.f("pk_host_packages")
        ),
        sa.ForeignKeyConstraint(
            KEY,
            REFERENCE,
            name=op.f("fk_host_packages_source_host_systems"),
            ondelete="CASCADE",
        ),
    )


def downgrade() -> None:
    op.drop_table("host_packages")
    op.drop_table("host_ports")
    op.drop_table("host_systems")
