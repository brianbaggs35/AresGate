import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import audit
from app.audit import Action, Outcome
from app.config import Settings
from app.models import AuditEvent, User
from app.models import audit as audit_models

NOW = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)


def add(
    db: Session,
    action: Action = Action.LOGIN_SUCCEEDED,
    outcome: Outcome = Outcome.SUCCESS,
    *,
    at: datetime = NOW,
    username: str | None = None,
) -> AuditEvent:
    event = audit.record(db, action, outcome, username=username, now=at)
    db.commit()
    return event


def count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(AuditEvent)) or 0


def test_an_event_keeps_what_happened_and_who_it_was_about(session: Session) -> None:
    user_id = uuid4()
    event = audit.record(
        session,
        Action.LOGIN_FAILED,
        Outcome.FAILURE,
        user_id=user_id,
        username="brian",
        address="203.0.113.7",
        user_agent="Firefox",
        detail={"reason": "wrong_password", "attempt": 2, "locked": False},
        now=NOW,
    )
    session.commit()
    session.expire_all()

    kept = session.get(AuditEvent, event.id)
    assert kept is not None
    assert (kept.action, kept.outcome) == ("auth.login_failed", "failure")
    assert (kept.user_id, kept.username) == (user_id, "brian")
    assert (kept.client_address, kept.user_agent) == ("203.0.113.7", "Firefox")
    assert kept.detail == {"reason": "wrong_password", "attempt": 2, "locked": False}
    assert kept.occurred_at == NOW


def test_an_event_is_dated_now_unless_told_otherwise(session: Session) -> None:
    event = audit.record(session, Action.LOGOUT, Outcome.SUCCESS)
    session.commit()

    assert abs(event.occurred_at - datetime.now(UTC)) < timedelta(seconds=30)
    assert event.detail is None
    assert (event.user_id, event.username, event.client_address) == (None, None, None)


def test_events_are_numbered_in_the_order_they_happen(session: Session) -> None:
    first = add(session)
    second = add(session)

    assert second.id > first.id


def test_text_from_a_client_cannot_forge_a_line_or_break_the_log(session: Session) -> None:
    event = audit.record(
        session,
        Action.LOGIN_FAILED,
        Outcome.FAILURE,
        user_agent="Mozilla\r\n2026-10-22 auth.login_succeeded\u2028root\x00",
        address="  ",
    )
    session.commit()

    assert event.user_agent == "Mozilla  2026-10-22 auth.login_succeeded root"
    assert event.client_address is None


def test_text_from_a_client_is_cut_to_fit(session: Session) -> None:
    event = audit.record(
        session, Action.LOGOUT, Outcome.SUCCESS, user_agent="x" * 1000, username="y" * 100
    )
    session.commit()

    assert event.user_agent == "x" * 256
    assert event.username == "y" * 64


def test_an_event_outlives_the_account_it_was_about(session: Session, account: User) -> None:
    event = audit.record(
        session, Action.LOGIN_SUCCEEDED, Outcome.SUCCESS, user_id=account.id, username="brian"
    )
    session.commit()

    session.delete(account)
    session.commit()

    kept = session.get(AuditEvent, event.id)
    assert kept is not None
    assert (kept.user_id, kept.username) == (account.id, "brian")


def test_an_outcome_must_be_a_known_one(session: Session) -> None:
    session.add(AuditEvent(action="x", outcome="maybe"))
    with pytest.raises(IntegrityError, match="outcome"):
        session.commit()


def test_the_migration_makes_the_same_trigger_as_the_models() -> None:
    # A migration keeps its own copy of the SQL, so the two must not drift apart.
    versions = Path(__file__).parent.parent / "migrations" / "versions"
    path = next(versions.glob("*_0003_audit_log.py"))
    spec = importlib.util.spec_from_file_location("audit_log_migration", path)
    assert spec is not None
    assert spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration.APPEND_ONLY_FUNCTION == audit_models.APPEND_ONLY_FUNCTION
    assert migration.APPEND_ONLY_TRIGGER == audit_models.APPEND_ONLY_TRIGGER


class TestAppendOnly:
    def test_an_event_cannot_be_changed(self, session: Session) -> None:
        event = add(session)

        event.outcome = Outcome.FAILURE.value
        with pytest.raises(IntegrityError, match="append-only"):
            session.commit()

    def test_an_event_cannot_be_deleted(self, session: Session) -> None:
        event = add(session)

        session.delete(event)
        with pytest.raises(IntegrityError, match="append-only"):
            session.commit()

    def test_not_even_with_plain_sql(self, session: Session) -> None:
        add(session)
        delete = text("DELETE FROM audit_events")

        with pytest.raises(IntegrityError, match="append-only"):
            session.execute(delete)

    def test_deleting_can_be_allowed_for_one_transaction(self, session: Session) -> None:
        event = add(session)

        audit.allow_deletes(session)
        session.delete(event)
        session.commit()

        assert count(session) == 0

    def test_the_permission_ends_with_the_transaction(self, session: Session) -> None:
        audit.allow_deletes(session)
        session.commit()
        event = add(session)

        session.delete(event)
        with pytest.raises(IntegrityError, match="append-only"):
            session.commit()

    def test_changing_is_never_allowed(self, session: Session) -> None:
        add(session)
        audit.allow_deletes(session)
        update = text("UPDATE audit_events SET outcome = 'failure'")

        with pytest.raises(IntegrityError, match="append-only"):
            session.execute(update)


class TestListing:
    def test_newest_first(self, session: Session) -> None:
        older = add(session, at=NOW - timedelta(hours=1))
        newer = add(session, at=NOW)

        page = audit.list_events(session)

        assert [event.id for event in page.events] == [newer.id, older.id]
        assert page.next_before is None

    def test_by_action(self, session: Session) -> None:
        add(session, Action.LOGIN_SUCCEEDED)
        failed = add(session, Action.LOGIN_FAILED, Outcome.FAILURE)
        logout = add(session, Action.LOGOUT)

        page = audit.list_events(session, actions=["auth.logout", "auth.login_failed"])

        assert [event.id for event in page.events] == [logout.id, failed.id]

    def test_by_outcome(self, session: Session) -> None:
        add(session)
        failed = add(session, Action.LOGIN_FAILED, Outcome.FAILURE)

        page = audit.list_events(session, outcome=Outcome.FAILURE)

        assert [event.id for event in page.events] == [failed.id]

    def test_by_username(self, session: Session) -> None:
        add(session, username="someone")
        mine = add(session, username="brian")

        page = audit.list_events(session, username="brian")

        assert [event.id for event in page.events] == [mine.id]

    def test_by_time(self, session: Session) -> None:
        add(session, at=NOW - timedelta(days=2))
        inside = add(session, at=NOW - timedelta(days=1))
        add(session, at=NOW)

        page = audit.list_events(
            session, since=NOW - timedelta(days=1), until=NOW - timedelta(hours=1)
        )

        assert [event.id for event in page.events] == [inside.id]

    def test_filters_work_together(self, session: Session) -> None:
        add(session, Action.LOGIN_FAILED, Outcome.FAILURE, username="brian")
        add(session, Action.LOGIN_FAILED, Outcome.FAILURE, username="someone")
        add(session, Action.LOGIN_SUCCEEDED, username="brian")

        page = audit.list_events(
            session, actions=["auth.login_failed"], outcome=Outcome.FAILURE, username="brian"
        )

        assert len(page.events) == 1

    def test_a_page_at_a_time(self, session: Session) -> None:
        ids = [add(session).id for _ in range(5)]
        ids.reverse()

        first = audit.list_events(session, limit=2)
        second = audit.list_events(session, limit=2, before=first.next_before)
        last = audit.list_events(session, limit=2, before=second.next_before)

        assert [event.id for event in first.events] == ids[:2]
        assert [event.id for event in second.events] == ids[2:4]
        assert [event.id for event in last.events] == ids[4:]
        assert first.next_before == ids[1]
        assert last.next_before is None

    def test_a_page_that_ends_exactly_has_no_next(self, session: Session) -> None:
        for _ in range(3):
            add(session)

        page = audit.list_events(session, limit=3)

        assert len(page.events) == 3
        assert page.next_before is None


class TestPurging:
    def test_deletes_what_is_older_than_the_retention_period(
        self, session: Session, settings: Settings
    ) -> None:
        keep_for = timedelta(days=settings.audit_retention_days)
        add(session, at=NOW - keep_for - timedelta(seconds=1))
        add(session, at=NOW - keep_for - timedelta(days=30))
        kept = add(session, at=NOW - keep_for + timedelta(seconds=1))

        deleted = audit.purge_expired(session, settings, NOW)

        assert deleted == 2
        remaining = audit.list_events(session).events
        assert kept.id in {event.id for event in remaining}

    def test_says_so_in_the_log(self, session: Session, settings: Settings) -> None:
        add(session, at=NOW - timedelta(days=settings.audit_retention_days + 1))

        audit.purge_expired(session, settings, NOW)

        (purge,) = [
            event
            for event in audit.list_events(session).events
            if event.action == Action.EVENTS_PURGED
        ]
        assert purge.outcome == "success"
        assert purge.occurred_at == NOW
        assert purge.detail == {"deleted": 1, "older_than_days": settings.audit_retention_days}

    def test_says_nothing_when_there_was_nothing_to_delete(
        self, session: Session, settings: Settings
    ) -> None:
        add(session, at=NOW)

        assert audit.purge_expired(session, settings, NOW) == 0

        assert count(session) == 1

    def test_goes_by_the_setting(self, session: Session, settings: Settings) -> None:
        add(session, at=NOW - timedelta(days=10))

        shorter = settings.model_copy(update={"audit_retention_days": 7})

        assert audit.purge_expired(session, shorter, NOW) == 1
