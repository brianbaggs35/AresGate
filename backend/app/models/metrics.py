"""Numbers that integrations report over time, such as a firewall's load or an interface's
traffic, kept as a series of samples."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Double,
    ForeignKey,
    Identity,
    Index,
    PrimaryKeyConstraint,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime
from app.models.retention import SourceRetention


class MetricSeries(Base):
    """One thing that is measured: a name from one connection, with the labels that tell it apart
    from the same name measured elsewhere, such as ``interface.bytes_in`` with ``interface:
    igc0``. A series is made the first time a sample for it is stored, and goes when its last
    sample does, so there are as many rows as there are things measured, and the samples are
    kept small by naming theirs with a number."""

    __tablename__ = "metric_series"
    __table_args__ = (Index("ix_metric_series_source_name", "source", "name"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    # Which integration and which of its connections reported it, such as opnsense and api.
    source: Mapped[str] = mapped_column(String(32))
    connection: Mapped[str] = mapped_column(String(32))
    # What is measured, in lowercase words, digits, underscores and dots: system.load_1m.
    name: Mapped[str] = mapped_column(String(64))
    labels: Mapped[dict[str, str]] = mapped_column(JSONB)
    # A hash of the four above, which is what tells one series from another.
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True)


class MetricSample(Base):
    """One reading of a series at a moment.

    The table is split into one partition for each week of ``sampled_at`` (see
    ``app/partitions.py``), so old samples leave by dropping a table instead of by deleting rows.
    That is why the key holds the time. The same series read at the same moment is kept once. The
    source is repeated from the series so that each source can be kept for its own time without
    looking the series up."""

    __tablename__ = "metric_samples"
    __table_args__ = (
        PrimaryKeyConstraint("series_id", "sampled_at"),
        Index("ix_metric_samples_source_sampled_at", "source", "sampled_at"),
        {"postgresql_partition_by": "RANGE (sampled_at)"},
    )

    series_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("metric_series.id", ondelete="CASCADE")
    )
    sampled_at: Mapped[datetime] = mapped_column(UTCDateTime)
    source: Mapped[str] = mapped_column(String(32))
    value: Mapped[float] = mapped_column(Double)


class MetricRetention(SourceRetention):
    """How long one source's samples are kept, when that isn't the default. A source without a
    row here keeps them for ``ARESGATE_METRIC_RETENTION_DAYS``."""

    __tablename__ = "metric_retention"
    __table_args__ = (CheckConstraint("days BETWEEN 1 AND 3650", name="days"),)
