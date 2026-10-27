"""What the routes that take a search have in common: reading it in words, and not letting it hold
the database up."""

from collections.abc import Callable, Generator
from contextlib import contextmanager
from datetime import UTC
from functools import lru_cache
from zoneinfo import ZoneInfo, available_timezones

from fastapi import HTTPException, status
from psycopg.errors import QueryCanceled
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.models import utcnow
from app.querylang import Context, Search, SearchError

# How long a search may take before the database gives up on it, so that nothing a person types
# can keep it busy.
SEARCH_TIMEOUT_MS = 5000


@lru_cache
def _zones() -> frozenset[str]:
    return frozenset(available_timezones())


def context(zone: str | None) -> Context:
    """Where the person is and when, for the words in a search that depend on it."""
    if zone is not None and zone not in _zones():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "That isn't a time zone.")
    return Context(zone=ZoneInfo(zone) if zone else UTC, now=utcnow())


def ask(
    db: Session, text: str, zone: str | None, parse: Callable[[str, Context], Search]
) -> Search:
    """What a search says. One that says something is limited in time: whatever it asks for, the
    database stops it before it holds anything up."""
    try:
        asked = parse(text, context(zone))
    except SearchError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    if asked.terms:
        db.execute(select(func.set_config("statement_timeout", str(SEARCH_TIMEOUT_MS), True)))
    return asked


@contextmanager
def in_time(db: Session) -> Generator[None]:
    """Turns the database giving up on a search into what a person is told about it."""
    try:
        yield
    except OperationalError as error:
        if not isinstance(error.orig, QueryCanceled):
            raise
        db.rollback()
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "That search took too long. Narrow it, for example with since:7d.",
        ) from None
