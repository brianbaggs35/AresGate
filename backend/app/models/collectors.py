"""How the collectors are doing, kept where the web app can read it while the worker (a process
of its own) writes it."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime, utcnow


class CollectorHealth(Base):
    """One collector reading from one connection, such as the connection check on OPNsense's
    API: when it last ran, how that went and when it runs next. The page for each integration
    and the status page are made from these rows. A row is deleted along with the connection."""

    __tablename__ = "collector_health"
    __table_args__ = (
        UniqueConstraint(
            "collector", "integration", "connection", name="uq_collector_health_collector"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    # Which collector (its key in app/collectors/registry.py), and the connection it reads from.
    collector: Mapped[str] = mapped_column(String(48))
    integration: Mapped[str] = mapped_column(String(32))
    connection: Mapped[str] = mapped_column(String(32))
    # How often it is meant to run, so a row that hasn't been touched for much longer than that
    # shows the worker has stopped.
    interval_seconds: Mapped[int] = mapped_column(Integer)
    last_started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    last_finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    last_success_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    last_duration_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    # How many things the last successful run collected, for a collector that counts them.
    last_items: Mapped[int | None] = mapped_column(Integer, default=None)
    # Why the last run failed. It is kept until the next success.
    last_error: Mapped[str | None] = mapped_column(String(500), default=None)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    next_run_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class WorkerBeat(Base):
    """The worker saying it is alive: when it started and when it last did. The status page
    reads this to tell a worker that has stopped from one that has nothing to do."""

    __tablename__ = "worker_beats"

    # What the worker is called; there is one, "collectors".
    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime)
    beat_at: Mapped[datetime] = mapped_column(UTCDateTime)
