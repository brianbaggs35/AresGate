"""How long a lookup must wait under an access level's limits, and how a lookup is kept once it may
go. Every lookup goes through ``reserve``, so the background loop and a search share the limits."""

from datetime import UTC, datetime, timedelta
from ipaddress import ip_address

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.intel import budget, store, virustotal
from app.models import IntelLookup, IntelReport

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
PROVIDER = virustotal.PROVIDER
ADDRESS = ip_address("93.184.216.34")
REPORT = virustotal.Report(
    malicious=1,
    suspicious=0,
    harmless=40,
    undetected=10,
    reputation=0,
    analysed_at=NOW,
)


def lookup_at(session: Session, when: datetime) -> None:
    session.add(
        IntelLookup(
            provider=PROVIDER,
            address=ADDRESS,
            requested_at=when,
            outcome=store.REPORTED,
        )
    )
    session.flush()


def test_nothing_waits_when_no_lookup_has_been_made(session: Session) -> None:
    assert budget.wait_for(session, PROVIDER, budget.FREE, NOW) == timedelta(0)


def test_the_spacing_waits_for_the_time_left_since_the_last_lookup(session: Session) -> None:
    lookup_at(session, NOW - timedelta(seconds=10))

    assert budget.wait_for(session, PROVIDER, budget.FREE, NOW) == timedelta(seconds=5)


def test_the_day_limit_waits_until_the_lookup_that_must_leave_the_day_has_left(
    session: Session,
) -> None:
    level = budget.Level(spacing=timedelta(0), per_day=2, per_month=None)
    lookup_at(session, NOW - timedelta(hours=2))
    lookup_at(session, NOW - timedelta(hours=1))

    assert budget.wait_for(session, PROVIDER, level, NOW) == timedelta(hours=22)


def test_with_more_lookups_than_the_limit_the_one_at_the_limit_is_the_one_waited_for(
    session: Session,
) -> None:
    level = budget.Level(spacing=timedelta(0), per_day=2, per_month=None)
    lookup_at(session, NOW - timedelta(hours=23))
    lookup_at(session, NOW - timedelta(hours=20))
    lookup_at(session, NOW - timedelta(hours=1))

    # Once the lookup of 23 hours ago has left, two are still in the day: the next to go leaves
    # 4 hours from now, when the lookup of 20 hours ago does.
    assert budget.wait_for(session, PROVIDER, level, NOW) == timedelta(hours=4)


def test_the_month_limit_waits_for_the_lookup_that_must_leave_the_month(session: Session) -> None:
    level = budget.Level(spacing=timedelta(0), per_day=None, per_month=1)
    lookup_at(session, NOW - timedelta(days=3))

    assert budget.wait_for(session, PROVIDER, level, NOW) == timedelta(days=27)


def test_the_longest_wait_of_the_limits_is_the_one_given(session: Session) -> None:
    level = budget.Level(spacing=timedelta(seconds=15), per_day=1, per_month=None)
    lookup_at(session, NOW - timedelta(seconds=10))

    assert budget.wait_for(session, PROVIDER, level, NOW) == timedelta(
        hours=23, minutes=59, seconds=50
    )


def test_a_lookup_that_may_go_is_kept_as_pending_and_its_id_is_given(session: Session) -> None:
    lookup_id = budget.reserve(session, PROVIDER, budget.FREE, NOW, address=ADDRESS)

    row = session.get(IntelLookup, lookup_id)
    assert row is not None
    assert (row.kind, row.address, row.subject, row.outcome) == (
        "ip",
        ADDRESS,
        None,
        store.PENDING,
    )


def test_a_lookup_that_may_not_go_yet_says_how_long_to_wait_and_keeps_nothing(
    session: Session,
) -> None:
    lookup_at(session, NOW - timedelta(seconds=10))

    with pytest.raises(budget.Wait) as waiting:
        budget.reserve(session, PROVIDER, budget.FREE, NOW, address=ADDRESS)

    assert waiting.value.wait == timedelta(seconds=5)
    assert len(session.scalars(select(IntelLookup)).all()) == 1


def test_a_search_of_a_domain_is_kept_with_the_domain_and_no_address(session: Session) -> None:
    lookup_id = budget.reserve(
        session, PROVIDER, budget.PREMIUM, NOW, kind="domain", subject="example.com"
    )

    row = session.get(IntelLookup, lookup_id)
    assert row is not None
    assert (row.kind, row.address, row.subject) == ("domain", None, "example.com")


def test_a_domain_report_is_shown_but_not_kept_as_a_report_of_an_address(session: Session) -> None:
    lookup_id = budget.reserve(
        session, PROVIDER, budget.PREMIUM, NOW, kind="domain", subject="example.com"
    )

    store.finish(session, lookup_id, virustotal.Reported(report=REPORT))

    row = session.get(IntelLookup, lookup_id)
    assert row is not None
    assert row.outcome == store.REPORTED
    assert session.scalars(select(IntelReport)).all() == []
