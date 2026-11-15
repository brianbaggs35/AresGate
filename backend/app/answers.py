"""Answers that are built from many queries, kept for a few seconds so that the polls of every open
tab and phone share one build.

Each API worker keeps its own, since the aim is to collapse repeated polls, not to share state.
What the owner changes (any change that succeeded) is written down in the database as a new stamp,
and an answer built under an older stamp is never used, so a change is seen by the very next
request whichever worker serves it. What the program hears from the network is not a change in
this sense: it shows within the seconds the answer is kept for.
"""

import hashlib
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.models.system import ANSWERS_STAMP

SECONDS = 15.0


def current_stamp(db: Session) -> int | None:
    """Where the stamp is: the number the last change took, or nothing where there has been none.
    One cheap lookup, with no row to lock."""
    return db.scalar(select(func.pg_sequence_last_value(ANSWERS_STAMP.name)))


def stamp_change(sessions: sessionmaker[Session]) -> None:
    """Writes down that something the owner can see has changed, in a session of its own so that
    it doesn't depend on the request's. The next number is taken even if the session's own
    transaction later fails, which only makes an answer be built again."""
    with sessions() as db:
        db.scalar(select(ANSWERS_STAMP.next_value()))
        db.commit()


@dataclass(frozen=True)
class Answer:
    """What was built, as it is sent, and the tag that says which version of it this is."""

    body: bytes
    etag: str


@dataclass(frozen=True)
class _Kept:
    stamp: int | None
    born: float
    answer: Answer


def etag_of(body: bytes) -> str:
    """A tag that changes when, and only when, the body does."""
    return f'"{hashlib.sha256(body).hexdigest()[:32]}"'


class AnswerCache:
    """The answers kept, by name. A request that finds a fresh one built under the current stamp
    gets it; one that doesn't builds it, and one that comes while another is building waits for
    that and uses what it built."""

    def __init__(
        self, seconds: float = SECONDS, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.seconds = seconds
        self._clock = clock
        self._kept: dict[str, _Kept] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def _lock(self, name: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(name, threading.Lock())

    def fetch(self, name: str, db: Session, build: Callable[[], bytes]) -> Answer:
        # Read before the build, so a change that lands while it runs leaves the stamp behind.
        stamp = current_stamp(db)
        with self._lock(name):
            kept = self._kept.get(name)
            if kept and kept.stamp == stamp and self._clock() - kept.born < self.seconds:
                return kept.answer
            born = self._clock()
            body = build()
            answer = Answer(body, etag_of(body))
            self._kept[name] = _Kept(stamp, born, answer)
            return answer
