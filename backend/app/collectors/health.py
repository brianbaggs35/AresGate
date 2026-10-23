"""How a collector, and the worker that runs them, are doing, worked out from what they have
written down. Nothing here touches the database."""

from datetime import datetime, timedelta
from enum import StrEnum

from app.models import CollectorHealth, WorkerBeat

# What the worker's one heartbeat is called, and how long without one means it has stopped
# (it beats every 15 seconds).
WORKER = "collectors"
WORKER_SILENCE = timedelta(seconds=60)
# How far past its time a run may be before it counts as late: half an interval, and at least
# this much, so a slow disk or a busy moment isn't a problem.
MIN_GRACE = timedelta(seconds=60)


class State(StrEnum):
    # It has not finished a run yet.
    WAITING = "waiting"
    OK = "ok"
    # Its last run failed.
    PROBLEM = "problem"
    # It should have run by now and hasn't, which is what a stopped worker looks like.
    LATE = "late"


class WorkerState(StrEnum):
    RUNNING = "running"
    # It was running, and has gone quiet.
    STOPPED = "stopped"
    # It has never reported in.
    UNKNOWN = "unknown"
    # Collecting is turned off.
    OFF = "off"


def grace(interval_seconds: int) -> timedelta:
    return max(MIN_GRACE, timedelta(seconds=interval_seconds) / 2)


def state_of(row: CollectorHealth, now: datetime) -> State:
    if row.consecutive_failures > 0:
        return State.PROBLEM
    if row.last_finished_at is None:
        return State.WAITING
    if row.next_run_at and now > row.next_run_at + grace(row.interval_seconds):
        return State.LATE
    return State.OK


def worker_state(beat: WorkerBeat | None, now: datetime, enabled: bool) -> WorkerState:
    if not enabled:
        return WorkerState.OFF
    if beat is None:
        return WorkerState.UNKNOWN
    return WorkerState.RUNNING if now - beat.beat_at <= WORKER_SILENCE else WorkerState.STOPPED


def retry_delay(interval: timedelta, failures: int, first: timedelta) -> timedelta:
    """How long to wait after a run. One that worked waits a whole interval. A failure is tried
    again sooner, then less often as it keeps failing, but never later than a whole interval."""
    if failures <= 0:
        return interval
    # The exponent is capped so that a collector that has failed for months can't overflow.
    return min(interval, first * 2 ** min(failures - 1, 20))
