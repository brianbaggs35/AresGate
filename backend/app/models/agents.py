"""Agents: standing instructions to look at the network in a certain way, how often to, and what
each time they did came of it (app/agents)."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime, utcnow

# How a run came about: the owner asked for it, or the agent's schedule did.
TRIGGERS = ("manual", "schedule")
# Where a run is: waiting for the worker, going, or over (and how it ended).
STATUSES = ("queued", "running", "succeeded", "failed", "cancelled")
# The fewest minutes between the starts of a scheduled agent's runs.
MIN_INTERVAL_MINUTES = 5


class Agent(Base):
    """One agent the owner made from a template (app/agents/catalog.py). ``goal`` is the owner's
    own instructions, added to what the template already tells it. A schedule starts a run every
    ``interval_minutes`` while the agent is ``enabled``; with none, a run is started by hand."""

    __tablename__ = "agents"
    __table_args__ = (
        CheckConstraint(
            f"interval_minutes IS NULL OR interval_minutes >= {MIN_INTERVAL_MINUTES}",
            name="interval",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    template: Mapped[str] = mapped_column(String(32))
    goal: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    interval_minutes: Mapped[int | None] = mapped_column(Integer, default=None)
    # Whether the agent may send probes to the devices on the network, which only a template that
    # tests the network does. Off until the owner turns it on, and only ever for a run they start.
    allow_active: Mapped[bool] = mapped_column(Boolean, default=False)
    # When the schedule starts the next run, if it has one.
    next_run_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class AgentRun(Base):
    """One time an agent ran: when it was asked for, how it went, what it found. A run that is
    over keeps its summary and its findings, as {severity, title, detail, cites}."""

    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint("trigger IN ('manual', 'schedule')", name="trigger"),
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')", name="status"
        ),
        Index("ix_agent_runs_agent_id_id", "agent_id", "id"),
        Index("ix_agent_runs_status", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    agent_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("agents.id", ondelete="CASCADE"))
    trigger: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(9), default="queued")
    requested_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    # The step of the graph a running run is in.
    node: Mapped[str | None] = mapped_column(String(16), default=None)
    summary: Mapped[str] = mapped_column(Text, default="")
    findings: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list)
    error: Mapped[str | None] = mapped_column(String(500), default=None)
    # How many times the agent looked and thought, and what became of asking the AI.
    rounds: Mapped[int] = mapped_column(Integer, default=0)
    ai: Mapped[str] = mapped_column(String(500), default="")
    # The requests to the provider that made it, in ``ai_calls`` (which may have been deleted).
    call_ids: Mapped[list[int]] = mapped_column(JSONB, default=list)
    # Set by the owner to stop a run; it stops before its next step.
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)


class AgentStep(Base):
    """One thing a run did, in order, for the owner to follow what an agent is up to."""

    __tablename__ = "agent_steps"
    __table_args__ = (Index("ix_agent_steps_run_id_seq", "run_id", "seq"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("agent_runs.id", ondelete="CASCADE"))
    seq: Mapped[int] = mapped_column(Integer)
    at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    # The step of the graph it belongs to: plan, act, think or report.
    node: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(200))
    detail: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
