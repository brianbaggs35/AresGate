"""How long a lookup must wait under an access level's limits, and how a lookup is kept once it may
go. Every lookup goes through ``reserve``, so the background loop and a search share the limits."""

from datetime import UTC, datetime, timedelta
from ipaddress import ip_address

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.intel import budget, store, subjects, virustotal
from app.models import IntelLookup, IntelSubject

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


def test_a_domain_report_is_kept_as_the_answer_about_the_domain_and_not_an_address(
    session: Session,
) -> None:
    lookup_id = budget.reserve(
        session, PROVIDER, budget.PREMIUM, NOW, kind="domain", subject="example.com"
    )

    store.finish(
        session,
        lookup_id,
        subjects.parse("example.com"),
        virustotal.Reported(report=REPORT),
        NOW,
    )

    row = session.get(IntelLookup, lookup_id)
    assert row is not None
    assert row.outcome == store.REPORTED
    [kept] = session.scalars(select(IntelSubject)).all()
    assert (kept.kind, kept.subject, kept.outcome) == ("domain", "example.com", store.REPORTED)
    assert store.report_for(session, PROVIDER, ADDRESS) is None


def test_the_background_loop_leaves_four_minutes_between_its_lookups_on_the_free_key(
    session: Session,
) -> None:
    lookup_at(session, NOW - timedelta(minutes=1))

    assert budget.wait_for(session, PROVIDER, budget.FREE, NOW, background=True) == timedelta(
        minutes=3
    )


def test_a_search_is_held_back_only_by_the_short_spacing_of_the_free_key(session: Session) -> None:
    lookup_at(session, NOW - timedelta(minutes=1))

    assert budget.wait_for(session, PROVIDER, budget.FREE, NOW) == timedelta(0)


def test_the_background_loop_may_look_up_once_its_spacing_has_passed(session: Session) -> None:
    lookup_at(session, NOW - timedelta(minutes=4))

    assert budget.wait_for(session, PROVIDER, budget.FREE, NOW, background=True) == timedelta(0)


def test_premium_background_lookups_keep_only_the_premium_spacing(session: Session) -> None:
    lookup_at(session, NOW - timedelta(seconds=2))

    assert budget.wait_for(session, PROVIDER, budget.PREMIUM, NOW, background=True) == timedelta(0)


def test_a_background_lookup_that_comes_too_soon_is_refused_and_keeps_nothing(
    session: Session,
) -> None:
    lookup_at(session, NOW - timedelta(minutes=1))

    with pytest.raises(budget.Wait) as waiting:
        budget.reserve(session, PROVIDER, budget.FREE, NOW, background=True, address=ADDRESS)

    assert waiting.value.wait == timedelta(minutes=3)
    assert len(session.scalars(select(IntelLookup)).all()) == 1


def test_the_free_key_spreads_its_background_lookups_over_the_day() -> None:
    # Four minutes apart is 360 a day, which leaves 140 of the 500 for searches by hand.
    assert timedelta(days=1) // budget.FREE.background_spacing == 360


# -- the limit VirusTotal sets itself


def outcome_at(session: Session, when: datetime, outcome: str) -> None:
    session.add(IntelLookup(provider=PROVIDER, address=ADDRESS, requested_at=when, outcome=outcome))
    session.flush()


def test_no_limit_holds_lookups_without_a_limit_answer(session: Session) -> None:
    lookup_at(session, NOW - timedelta(minutes=5))

    assert budget.paused(session, PROVIDER, NOW) is None


def test_a_used_up_daily_quota_holds_lookups_until_the_midnight_reset(session: Session) -> None:
    outcome_at(session, NOW - timedelta(hours=3), store.LIMITED)

    assert budget.paused(session, PROVIDER, NOW) == budget.Pause(
        until=datetime(2026, 11, 10, tzinfo=UTC), daily=True
    )


def test_a_used_up_daily_quota_no_longer_holds_once_the_reset_has_passed(session: Session) -> None:
    outcome_at(session, NOW - timedelta(hours=3), store.LIMITED)

    assert budget.paused(session, PROVIDER, datetime(2026, 11, 10, 0, 0, 1, tzinfo=UTC)) is None


def test_too_many_requests_holds_lookups_for_a_minute(session: Session) -> None:
    outcome_at(session, NOW - timedelta(seconds=20), store.THROTTLED)

    assert budget.paused(session, PROVIDER, NOW) == budget.Pause(
        until=NOW + timedelta(seconds=40), daily=False
    )
    assert budget.paused(session, PROVIDER, NOW + timedelta(seconds=40)) is None


def test_the_last_limit_answered_is_the_one_that_holds(session: Session) -> None:
    outcome_at(session, NOW - timedelta(days=1), store.LIMITED)
    outcome_at(session, NOW - timedelta(seconds=10), store.THROTTLED)

    assert budget.paused(session, PROVIDER, NOW) == budget.Pause(
        until=NOW + timedelta(seconds=50), daily=False
    )


def test_the_limits_of_another_provider_hold_nothing(session: Session) -> None:
    session.add(
        IntelLookup(
            provider="another",
            address=ADDRESS,
            requested_at=NOW - timedelta(hours=1),
            outcome=store.LIMITED,
        )
    )
    session.flush()

    assert budget.paused(session, PROVIDER, NOW) is None


def test_a_reservation_is_refused_while_the_daily_quota_holds(session: Session) -> None:
    outcome_at(session, NOW - timedelta(hours=1), store.LIMITED)

    with pytest.raises(budget.Paused) as refused:
        budget.reserve(session, PROVIDER, budget.FREE, NOW)

    assert refused.value.pause.daily is True
    assert refused.value.wait == timedelta(hours=12)
    pending = session.scalars(select(IntelLookup).where(IntelLookup.outcome == store.PENDING))
    assert pending.all() == []


def test_a_reservation_is_refused_for_a_minute_after_too_many_requests(session: Session) -> None:
    outcome_at(session, NOW - timedelta(seconds=10), store.THROTTLED)

    with pytest.raises(budget.Paused) as refused:
        budget.reserve(session, PROVIDER, budget.FREE, NOW)

    assert refused.value.pause.daily is False
    assert refused.value.wait == timedelta(seconds=50)


def test_no_lookup_may_go_while_a_limit_holds(session: Session) -> None:
    outcome_at(session, NOW - timedelta(seconds=10), store.THROTTLED)

    assert not budget.may_look_up(session, PROVIDER, budget.PREMIUM, NOW)
