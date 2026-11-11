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
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime, utcnow

# How a run came about: the owner asked for it, or the agent's schedule did.
TRIGGERS = ("manual", "schedule")
# Where a run is: waiting for the worker, going, or over (and how it ended).
STATUSES = ("queued", "running", "succeeded", "failed", "cancelled")
# The fewest minutes between the starts of a scheduled agent's runs.
MIN_INTERVAL_MINUTES = 5
# Which AI the agents ask: the one chosen under Settings > AI, one of their own, or none.
AI_SOURCES = ("shared", "own", "off")
# What the cleanup agent does with what it finds: only suggest it, or do the surest of it too.
CLEANUP_MODES = ("suggest", "auto")
# Where a suggestion of the cleanup agent is: waiting for the owner, done, turned down, or done and
# taken back.
PROPOSAL_STATUSES = ("pending", "applied", "dismissed", "undone")


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


class AgentSettings(Base):
    """How the agents use AI, which is apart from the rest of AresGate so that they can be given a
    cheaper model, or a provider of their own, or none. There is only ever one row. With ``shared``
    they ask what Settings > AI chose (and only while AI is on there); with ``own`` they ask
    ``provider``, a provider that is set up under Settings > AI, with ``model`` if one is given
    (otherwise the model it was set up with); with ``off`` they look and keep what they saw but
    ask nobody. The limits hold what the agents alone may spend, in millionths of a US dollar:
    in the last 24 hours and in the calendar month. None is no limit."""

    __tablename__ = "agent_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="single_row"),
        CheckConstraint("ai_source IN ('shared', 'own', 'off')", name="ai_source"),
        CheckConstraint("cleanup_mode IN ('suggest', 'auto')", name="cleanup_mode"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1, autoincrement=False)
    ai_source: Mapped[str] = mapped_column(String(6), default="shared")
    provider: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("ai_providers.provider", ondelete="SET NULL"), default=None
    )
    model: Mapped[str | None] = mapped_column(String(128), default=None)
    daily_limit_micros: Mapped[int | None] = mapped_column(BigInteger, default=None)
    monthly_limit_micros: Mapped[int | None] = mapped_column(BigInteger, default=None)
    # Whether the cleanup agent only suggests what to tidy (the owner applies it) or also does the
    # surest of it itself. Everything it does can be taken back.
    cleanup_mode: Mapped[str] = mapped_column(String(7), default="suggest")
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
    # What the run used of the AI, added up from its requests when it ended, so that it is still
    # known after the record of the requests is gone: how many, their tokens, what they cost in
    # millionths of a US dollar (the ones whose price is known, and how many were not), and who
    # answered last.
    calls: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cached_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_micros: Mapped[int] = mapped_column(BigInteger, default=0)
    unpriced_calls: Mapped[int] = mapped_column(Integer, default=0)
    provider: Mapped[str | None] = mapped_column(String(32), default=None)
    model: Mapped[str | None] = mapped_column(String(128), default=None)


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


class AgentProposal(Base):
    """One thing the cleanup agent suggests tidying: what it is about, which incidents it would
    change and how (``action``: dismiss them, resolve them or give them a "not suspicious"
    verdict), and how sure the agent is. ``key`` is the same for the same suggestion found again,
    so one that was turned down or taken back is not made twice. When it has been applied,
    ``undo`` says how to take it back, as the incident list's bulk change does."""

    __tablename__ = "agent_proposals"
    __table_args__ = (
        UniqueConstraint("agent_id", "key", name="uq_agent_proposals_agent_id_key"),
        CheckConstraint("status IN ('pending', 'applied', 'dismissed', 'undone')", name="status"),
        CheckConstraint("confidence BETWEEN 0 AND 100", name="confidence"),
        Index("ix_agent_proposals_agent_id_status", "agent_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    agent_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("agents.id", ondelete="CASCADE"))
    run_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("agent_runs.id", ondelete="SET NULL"), default=None
    )
    kind: Mapped[str] = mapped_column(String(12))
    key: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    detail: Mapped[str] = mapped_column(Text, default="")
    action: Mapped[str] = mapped_column(String(16))
    incident_ids: Mapped[list[int]] = mapped_column(ARRAY(BigInteger), default=list)
    # The incident that stays when the rest of a group of duplicates is dismissed.
    keep_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    confidence: Mapped[int] = mapped_column(SmallInteger)
    status: Mapped[str] = mapped_column(String(9), default="pending")
    # Who decided: the owner, or the agent itself in auto mode.
    decided_by: Mapped[str | None] = mapped_column(String(5), default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    undo: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
