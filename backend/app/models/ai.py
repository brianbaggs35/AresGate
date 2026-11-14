"""The AI providers AresGate may ask, and whether it asks any."""

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
from sqlalchemy import text as sql
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime, utcnow

# How much the owner lets AresGate use AI of its own accord, from none but what they ask for to
# everything it can (app/ai/triage.py says what each does).
USAGE_LEVELS = ("very_low", "low", "medium", "high", "maximum")
# What an AI reading of an incident can make of it, and what it can suggest the owner say.
CLASSES = ("compromise", "attack", "probe", "noise", "unclear")


class AiProvider(Base):
    """How to reach one AI provider (app/ai/catalog.py names them) and how the last attempt went.
    Its API key is in the credential store (see app/security/credential_store.py), sealed, under
    the provider's key, so a row here holds nothing that has to stay secret. No row means the
    provider isn't set up."""

    __tablename__ = "ai_providers"

    provider: Mapped[str] = mapped_column(String(32), primary_key=True)
    # Where it is, for a provider that runs on the owner's own computer. The others are at one
    # address that the catalog knows.
    base_url: Mapped[str | None] = mapped_column(String(255), default=None)
    model: Mapped[str] = mapped_column(String(128))
    # The plan of the account, for a provider that has plans whose models differ (``free`` or
    # ``paid``), which only its owner can say: nothing the provider answers tells.
    plan: Mapped[str | None] = mapped_column(String(8), default=None)
    # The models that were installed or offered when they were last asked for, for the providers
    # that have no fixed list: each has a name, and may have its size and family.
    models_found: Mapped[list[dict[str, str | int | None]]] = mapped_column(JSONB, default=list)
    models_found_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    # The last time AresGate tried it and the last time that worked. A failure keeps the reason
    # (``last_error``) until the next success.
    last_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    last_success_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    last_error: Mapped[str | None] = mapped_column(String(500), default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class AiSettings(Base):
    """Whether AresGate uses AI, and which provider it asks. There is only ever one row."""

    __tablename__ = "ai_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="single_row"),
        CheckConstraint("redaction IN ('strict', 'balanced', 'local')", name="redaction"),
        CheckConstraint(
            "usage_level IN ('very_low', 'low', 'medium', 'high', 'maximum')", name="usage_level"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1, autoincrement=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # What a provider is allowed to see (app/ai/redaction.py): ``strict``, ``balanced`` or
    # ``local``, which only a provider on the owner's own network is given.
    redaction: Mapped[str] = mapped_column(String(8), default="balanced")
    # How much AI is used without being asked (``medium`` until the owner says otherwise).
    usage_level: Mapped[str] = mapped_column(String(10), default="medium")
    # What may be spent on a provider that charges by the token, in millionths of a US dollar:
    # in the last 24 hours and in the calendar month (UTC, as providers bill it). None is no
    # limit. Reaching one stops the requests to such a provider until it passes.
    daily_limit_micros: Mapped[int | None] = mapped_column(BigInteger, default=None)
    monthly_limit_micros: Mapped[int | None] = mapped_column(BigInteger, default=None)
    # Forgetting a provider turns it off here rather than leaving a dangling choice.
    provider: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("ai_providers.provider", ondelete="SET NULL"), default=None
    )
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class AiAlias(Base):
    """A real value (an address, a name) and the stand-in a provider is shown for it, which is
    the kind and this row's id (``HOST_12``). Only this server can turn a stand-in back into
    the value, and the same value is always the same stand-in, so an answer about ``HOST_12``
    today still means the same device tomorrow."""

    __tablename__ = "ai_aliases"
    __table_args__ = (UniqueConstraint("kind", "value", name="uq_ai_aliases_value"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    kind: Mapped[str] = mapped_column(String(8))
    value: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class AiCall(Base):
    """One request AresGate made to an AI provider about something: what it asked (as the
    provider saw it, with the stand-ins), what came back, what it counted and what it cost.
    The usage page and the limits read these."""

    __tablename__ = "ai_calls"
    __table_args__ = (Index("ix_ai_calls_purpose_id", "purpose", "id"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    # What for: ``triage``, ``chat``, and so on (app/ai/gateway.py).
    purpose: Mapped[str] = mapped_column(String(24))
    # What it was about, in a few words, such as ``incident 12``.
    about: Mapped[str | None] = mapped_column(String(120), default=None)
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(128))
    # How much of the network the provider was shown (``strict``, ``balanced`` or ``local``).
    level: Mapped[str] = mapped_column(String(8))
    ok: Mapped[bool] = mapped_column(Boolean)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cached_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_write_tokens: Mapped[int] = mapped_column(Integer, default=0)
    reasoning_tokens: Mapped[int] = mapped_column(Integer, default=0)
    # What it cost, in millionths of a US dollar, from the catalog's prices; None for a model
    # whose price isn't known.
    cost_micros: Mapped[int | None] = mapped_column(BigInteger, default=None)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    # The answer ran out of room, so it may be incomplete.
    truncated: Mapped[bool] = mapped_column(Boolean, default=False)
    # Why a request failed, in words that hold nothing the provider said and no secret.
    error: Mapped[str | None] = mapped_column(String(500), default=None)
    # Both with the stand-ins in them, exactly as the provider saw and said them.
    prompt: Mapped[str] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text, default=None)


class AiTriage(Base):
    """What an AI provider made of an incident, the latest time it was asked: what kind of thing it
    thinks it is, how sure it is, the story in plain words, what to check and what the owner
    might say about it. It is the AI's opinion, kept as such, beside the incident and never
    changing it. The request that made it is in ``ai_calls``."""

    __tablename__ = "ai_triage"
    __table_args__ = (
        CheckConstraint(
            "classification IN ('compromise', 'attack', 'probe', 'noise', 'unclear')",
            name="classification",
        ),
        CheckConstraint("confidence BETWEEN 0 AND 100", name="confidence"),
        CheckConstraint(
            "verdict IS NULL OR verdict IN ('not_suspicious', 'low_priority', 'threat')",
            name="verdict",
        ),
        CheckConstraint("review IN ('pending', 'auto', 'agreed', 'disagreed')", name="review"),
    )

    incident_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("incidents.id", ondelete="CASCADE"), primary_key=True
    )
    call_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("ai_calls.id", ondelete="SET NULL"), default=None
    )
    read_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    # How many signals the incident had when it was read, to tell when it has grown since.
    signals_read: Mapped[int] = mapped_column(Integer)
    classification: Mapped[str] = mapped_column(String(12))
    # How sure the AI is that it is what it says, from 0 to 100.
    confidence: Mapped[int] = mapped_column(SmallInteger)
    headline: Mapped[str] = mapped_column(String(160))
    story: Mapped[str] = mapped_column(Text)
    checks: Mapped[list[str]] = mapped_column(JSONB, default=list)
    # What stands out in what was actually sent, one plain statement each.
    observations: Mapped[list[str]] = mapped_column(JSONB, default=list)
    # What it suggests the owner say about it, if anything, and why.
    verdict: Mapped[str | None] = mapped_column(String(16), default=None)
    verdict_reason: Mapped[str | None] = mapped_column(String(300), default=None)
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(128))
    # Whether the owner has to look at this decision before it counts (``pending``), it counted
    # at once and is listed to look at later (``auto``), or the owner agreed or disagreed with it
    # (app/review).
    review: Mapped[str] = mapped_column(String(10), default="auto", server_default="auto")
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)


class AiConversation(Base):
    """A conversation with the assistant on the chat page (app/ai/chat.py). It is kept until the
    owner deletes it, and holds the real values the owner and the assistant wrote: the stand-ins
    a provider saw are in ``ai_calls``."""

    __tablename__ = "ai_conversations"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    # The first question, cut short.
    title: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class AiMessage(Base):
    """One thing said in a conversation: by the owner, or the assistant's answer to it. An answer
    that could not be made is kept too, with the reason as its text and ``ok`` false."""

    __tablename__ = "ai_messages"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="role"),
        Index("ix_ai_messages_conversation_id_id", "conversation_id", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ai_conversations.id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(String(9))
    text: Mapped[str] = mapped_column(Text)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    # What an answer looked at to make it, as {tool, summary} (the summary says what was found,
    # in words without a name or an address in them), and what it cites: {kind, key, label}.
    lookups: Mapped[list[dict[str, str]]] = mapped_column(JSONB, default=list)
    cites: Mapped[list[dict[str, str]]] = mapped_column(JSONB, default=list)
    # What an answer suggests the owner do, which they approve with a button (the assistant changes
    # nothing itself), as {kind, target_kind, target_key, value, note, label}.
    actions: Mapped[list[dict[str, str | None]]] = mapped_column(
        JSONB, default=list, server_default=sql("'[]'::jsonb")
    )
    # The requests to the provider that made it, in ``ai_calls`` (which may have been deleted).
    call_ids: Mapped[list[int]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
