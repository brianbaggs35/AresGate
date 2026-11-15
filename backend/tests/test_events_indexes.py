from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ClauseElement

from app import dashboard
from app.config import Settings
from app.events.event import Severity
from app.events.store import record as record_events
from app.models import Event
from app.partitions import EVENTS, Partition
from tests.helpers import new_event

NOW = datetime(2026, 10, 26, 18, 20, tzinfo=UTC)
PARTIAL = ("ix_events_alert_occurred_at", "ix_events_block_occurred_at")


def partial_indexes(session: Session, table: str) -> dict[str, str]:
    """The partial indexes of a table, by name, each with its definition."""
    rows = session.execute(
        text("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = :table"),
        {"table": table},
    )
    return {name: definition for name, definition in rows if " WHERE " in definition}


def plan_of(session: Session, query: ClauseElement) -> str:
    """How the database would run a query, when it has to choose an index if it can."""
    session.execute(text("SET LOCAL enable_seqscan = off"))
    session.execute(text("SET LOCAL enable_bitmapscan = off"))
    compiled = str(query.compile(compile_kwargs={"literal_binds": True}))
    return "\n".join(row[0] for row in session.execute(text("EXPLAIN " + compiled)))


class TestThePartialIndexes:
    def test_the_events_have_an_index_of_the_alerts_and_one_of_the_refused_connections(
        self, session: Session
    ) -> None:
        found = partial_indexes(session, "events")

        assert sorted(found) == sorted(PARTIAL)
        assert "WHERE ((kind)::text = 'alert'::text)" in found["ix_events_alert_occurred_at"]
        assert "(kind)::text = 'firewall'::text" in found["ix_events_block_occurred_at"]
        assert "severity >= 1" in found["ix_events_block_occurred_at"]

    def test_a_week_made_later_has_them_too(self, session: Session) -> None:
        week = Partition("events", datetime(2026, 12, 28, tzinfo=UTC))
        EVENTS.ensure(session, [week])

        found = partial_indexes(session, week.name)

        assert len(found) == 2
        assert any("occurred_at_source_severity" in name for name in found)
        assert any("occurred_at_src_address_dst" in name for name in found)

    def test_the_dashboard_says_what_it_is_after_in_words_not_in_parameters(self) -> None:
        # The database keeps a plan for a statement it has run a few times, and a plan made for any
        # value can't tell a query's rows are the index's, so it would read every event again.
        for condition in (dashboard.IS_ALERT, dashboard.IS_BLOCK):
            compiled = condition.compile()

            assert compiled.params == {}
        assert str(dashboard.IS_ALERT.compile()) == "events.kind = 'alert'"
        assert "severity >= 1" in str(dashboard.IS_BLOCK.compile())

    def test_a_refused_connection_is_read_from_its_index_alone(
        self, session: Session, settings: Settings
    ) -> None:
        record_events(
            session,
            settings,
            [
                new_event(
                    kind="firewall",
                    severity=Severity.LOW,
                    src_address="203.0.113.7",
                    occurred_at=NOW,
                )
            ],
            NOW,
        )
        window = NOW - timedelta(hours=1)

        plan = plan_of(
            session,
            select(Event.src_address).where(
                dashboard.IS_BLOCK, Event.src_address.is_not(None), Event.occurred_at >= window
            ),
        )

        assert "Index Only Scan" in plan
        assert "occurred_at_src_address_dst" in plan

    def test_an_alert_is_read_from_its_index_alone(
        self, session: Session, settings: Settings
    ) -> None:
        record_events(session, settings, [new_event(occurred_at=NOW)], NOW)

        plan = plan_of(
            session,
            select(Event.source, Event.severity, Event.twin_of).where(
                dashboard.IS_ALERT, Event.occurred_at >= NOW - timedelta(hours=1)
            ),
        )

        assert "Index Only Scan" in plan
        assert "occurred_at_source_severity" in plan

    def test_the_other_kinds_of_events_are_in_neither(
        self, session: Session, settings: Settings
    ) -> None:
        record_events(
            session,
            settings,
            [new_event(kind="authentication", occurred_at=NOW)],
            NOW,
        )

        plan = plan_of(
            session,
            select(Event.source).where(Event.kind == "authentication"),
        )

        assert "occurred_at_source_severity" not in plan
        assert "occurred_at_src_address_dst" not in plan
