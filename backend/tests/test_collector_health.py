from datetime import timedelta

import pytest

from app.collectors import health
from app.collectors.health import State, WorkerState
from app.models import CollectorHealth, WorkerBeat, utcnow


def row(**changes: object) -> CollectorHealth:
    found = CollectorHealth(
        collector="connection-check",
        integration="crowdsec",
        connection="lapi",
        interval_seconds=300,
        consecutive_failures=0,
        updated_at=utcnow(),
    )
    for name, value in changes.items():
        setattr(found, name, value)
    return found


def test_a_collector_that_has_not_finished_a_run_is_waiting() -> None:
    assert health.state_of(row(), utcnow()) == State.WAITING


def test_a_collector_whose_last_run_worked_and_is_not_due_is_ok() -> None:
    now = utcnow()

    found = row(last_finished_at=now, next_run_at=now + timedelta(minutes=5))

    assert health.state_of(found, now) == State.OK


def test_a_collector_that_failed_has_a_problem_even_before_its_next_try() -> None:
    now = utcnow()

    found = row(
        consecutive_failures=1, last_finished_at=now, next_run_at=now + timedelta(seconds=30)
    )

    assert health.state_of(found, now) == State.PROBLEM


def test_a_collector_that_failed_before_it_ever_finished_has_a_problem() -> None:
    assert health.state_of(row(consecutive_failures=3), utcnow()) == State.PROBLEM


def test_a_collector_is_late_only_once_it_is_well_past_its_time() -> None:
    now = utcnow()
    due = now - timedelta(seconds=150)
    found = row(last_finished_at=now - timedelta(minutes=7), next_run_at=due)

    # Five minutes between runs allows two and a half minutes' grace.
    assert health.grace(300) == timedelta(seconds=150)
    assert health.state_of(found, due + timedelta(seconds=150)) == State.OK
    assert health.state_of(found, due + timedelta(seconds=151)) == State.LATE


def test_a_short_interval_is_given_a_minute_of_grace() -> None:
    assert health.grace(10) == timedelta(minutes=1)


def test_the_worker_is_running_while_it_keeps_reporting_in() -> None:
    now = utcnow()
    beat = WorkerBeat(name="collectors", started_at=now - timedelta(hours=1), beat_at=now)

    assert health.worker_state(beat, now, enabled=True) == WorkerState.RUNNING
    assert health.worker_state(beat, now + health.WORKER_SILENCE, enabled=True) == (
        WorkerState.RUNNING
    )
    assert health.worker_state(
        beat, now + health.WORKER_SILENCE + timedelta(seconds=1), enabled=True
    ) == (WorkerState.STOPPED)


def test_a_worker_that_never_reported_in_is_unknown_and_one_turned_off_is_off() -> None:
    now = utcnow()
    beat = WorkerBeat(name="collectors", started_at=now, beat_at=now)

    assert health.worker_state(None, now, enabled=True) == WorkerState.UNKNOWN
    assert health.worker_state(None, now, enabled=False) == WorkerState.OFF
    assert health.worker_state(beat, now, enabled=False) == WorkerState.OFF


@pytest.mark.parametrize(
    ("failures", "seconds"),
    [(0, 300), (1, 30), (2, 60), (3, 120), (4, 240), (5, 300), (6, 300), (10_000, 300)],
)
def test_a_failing_collector_is_tried_again_sooner_and_then_less_often(
    failures: int, seconds: int
) -> None:
    delay = health.retry_delay(timedelta(minutes=5), failures, timedelta(seconds=30))

    assert delay == timedelta(seconds=seconds)


def test_a_retry_is_never_later_than_the_normal_interval() -> None:
    delay = health.retry_delay(timedelta(seconds=10), 1, timedelta(seconds=30))

    assert delay == timedelta(seconds=10)
