"""What the National Vulnerability Database says of the CVEs that incidents name.

A CVE is asked about once and kept: its score, its severity, whether CISA lists it as exploited in
the wild, and what it is. The answer is asked for again when it has gone stale, since NVD scores a
new CVE days after it is published and CISA adds to its list as exploitation is seen.
"""

from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, Float, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime


class NvdCve(Base):
    """What NVD last said of one CVE, or that it has no record of it yet."""

    __tablename__ = "nvd_cves"
    __table_args__ = (
        CheckConstraint("state IN ('found', 'unknown')", name="state"),
        CheckConstraint(
            "severity IS NULL OR severity IN ('NONE', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="severity",
        ),
        CheckConstraint("score IS NULL OR score BETWEEN 0 AND 10", name="score"),
        Index("ix_nvd_cves_checked_at", "checked_at"),
    )

    # The CVE's identifier in capitals, such as ``CVE-2021-44228``.
    cve_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    # ``found``: NVD has a record. ``unknown``: it has none yet, as for a CVE it has not received.
    state: Mapped[str] = mapped_column(String(8))
    checked_at: Mapped[datetime] = mapped_column(UTCDateTime)
    # NVD's own status for the record (``Analyzed``, ``Awaiting Analysis``, ``Rejected``).
    status: Mapped[str | None] = mapped_column(String(40), default=None)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    modified_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    # The newest CVSS score the record has: its version (``4.0``, ``3.1``, ``3.0``, ``2.0``), the
    # base score from 0 to 10, its rating and its vector.
    cvss_version: Mapped[str | None] = mapped_column(String(4), default=None)
    score: Mapped[float | None] = mapped_column(Float, default=None)
    severity: Mapped[str | None] = mapped_column(String(8), default=None)
    vector: Mapped[str | None] = mapped_column(String(200), default=None)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    # The weaknesses it names (``CWE-287``), in the order NVD lists them.
    weaknesses: Mapped[list[str]] = mapped_column(JSONB, default=list)
    # Whether CISA lists it in its Known Exploited Vulnerabilities catalog, which says it has been
    # exploited in the wild, and what CISA says of that: when it was added, the date federal
    # agencies must act by, what they are to do and what CISA calls it.
    exploited: Mapped[bool] = mapped_column(default=False)
    exploited_on: Mapped[date | None] = mapped_column(Date, default=None)
    action_due: Mapped[date | None] = mapped_column(Date, default=None)
    required_action: Mapped[str | None] = mapped_column(String(600), default=None)
    kev_name: Mapped[str | None] = mapped_column(String(200), default=None)
