"""The audit log: what happened to the install's security, in the order it happened."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DDL, BigInteger, CheckConstraint, Identity, String, Uuid, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime, utcnow

# Nothing in AresGate changes or removes an event, except the retention purge, which says so
# first (see app/audit.py). The database refuses anything else, so a bug can't rewrite history.
# The migration holds a copy of this SQL, as migrations keep what they ran.
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


class AuditEvent(Base):
    """One thing that happened. It keeps the username as it was at the time, and the account's id
    without a foreign key, so it outlives the account (recovering a lost password deletes it)."""

    __tablename__ = "audit_events"
    __table_args__ = (CheckConstraint("outcome IN ('success', 'failure')", name="outcome"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    # What happened, e.g. auth.login_failed.
    action: Mapped[str] = mapped_column(String(64), index=True)
    outcome: Mapped[str] = mapped_column(String(16))
    user_id: Mapped[UUID | None] = mapped_column(Uuid, default=None)
    username: Mapped[str | None] = mapped_column(String(64), default=None)
    # Where the request came from, and what it said it was. Neither is empty only for something
    # done from the command line.
    client_address: Mapped[str | None] = mapped_column(String(64), default=None)
    user_agent: Mapped[str | None] = mapped_column(String(256), default=None)
    # A few facts about it, e.g. why a sign-in failed. Never a secret.
    detail: Mapped[dict[str, str | int | bool] | None] = mapped_column(JSONB, default=None)


# Tests and the end-to-end harness make the tables from the models, so they get the trigger too.
event.listen(AuditEvent.__table__, "after_create", DDL(APPEND_ONLY_FUNCTION))
event.listen(AuditEvent.__table__, "after_create", DDL(APPEND_ONLY_TRIGGER))
