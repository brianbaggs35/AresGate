"""What AresGate has learned is normal on this network, kept so that it survives a restart."""

from datetime import datetime
from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network

from sqlalchemy import BigInteger, CheckConstraint, Double, ForeignKey, Index, Integer, SmallInteger
from sqlalchemy.dialects.postgresql import CIDR, INET
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime


class TrafficBaseline(Base):
    """How much usually passes through one thing that is measured in an hour of the day: the
    middle of what it was over the weeks AresGate has watched, and how far it strays. A bucket
    is the hour of the day (0 to 23, in UTC) of a weekday, then of a weekend day (24 to 47), then
    of any day (48 to 71), which stands in for the first two where there is too little of those
    to learn from."""

    __tablename__ = "traffic_baselines"
    __table_args__ = (CheckConstraint("bucket BETWEEN 0 AND 71", name="bucket"),)

    series_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("metric_series.id", ondelete="CASCADE"), primary_key=True
    )
    bucket: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    # How many hours it was learned from.
    samples: Mapped[int] = mapped_column(Integer)
    # The median, in bytes in the hour, and the spread (the median absolute deviation, scaled to
    # stand for a standard deviation), which together say what is usual and how far is far.
    median: Mapped[float] = mapped_column(Double)
    spread: Mapped[float] = mapped_column(Double)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)


class KnownDestination(Base):
    """A place a device on the network has been seen to talk to: the network its address is in
    (a /24, or a /64 for IPv6) and the port. What a device has talked to before is normal for
    it; a place it has not is what is worth a look."""

    __tablename__ = "known_destinations"
    __table_args__ = (Index("ix_known_destinations_last_seen_at", "last_seen_at"),)

    client: Mapped[IPv4Address | IPv6Address] = mapped_column(INET, primary_key=True)
    network: Mapped[IPv4Network | IPv6Network] = mapped_column(CIDR, primary_key=True)
    # 0 where the traffic has no port, such as ICMP.
    port: Mapped[int] = mapped_column(Integer, primary_key=True)
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime)
    hits: Mapped[int] = mapped_column(BigInteger)
