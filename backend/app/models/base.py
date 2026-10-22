"""Declarative base and column types shared by all ORM models."""

from datetime import UTC, datetime
from typing import override

from sqlalchemy import DateTime, Dialect, MetaData
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator

# Deterministic constraint names keep Alembic migrations stable across databases.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """A timezone-aware timestamp that always comes back in UTC, whatever the connection's
    time zone. Naive values are refused on the way in."""

    impl = DateTime(timezone=True)
    cache_ok = True

    @override
    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @override
    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return None if value is None else value.astimezone(UTC)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
