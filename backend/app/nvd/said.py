"""What NVD says of a CVE, as sentences for the AI to read, and the CVEs a set of signals name."""

from collections.abc import Callable, Iterable

from sqlalchemy.orm import Session

from app.models import IncidentSignal, NvdCve
from app.nvd import cves, store

# The most CVEs one incident is told of, so that a scanner's report can't fill the prompt.
MOST = 8
HEADING = (
    "What the National Vulnerability Database says of the CVEs the incident names (CVSS is the "
    "severity score of the vulnerability itself, not of this attack; a CVE on CISA's exploited "
    "list has been seen exploited in the wild):"
)
NOT_RECORDED = "NVD has no record of it yet, so nothing is known of how severe it is"


def named_in(db: Session, signals: Iterable[IncidentSignal]) -> list[tuple[str, NvdCve | None]]:
    """The CVEs the signals name, the first named first, each with what NVD said of it if it was
    asked."""
    ids = cves.merge(cves.named_by(each.summary, each.signature, each.evidence) for each in signals)
    kept = store.load(db, ids[:MOST])
    return [(cve_id, kept.get(cve_id)) for cve_id in ids[:MOST]]


def said(row: NvdCve | None, cve_id: str, text: Callable[[str, int], str]) -> str:
    """What NVD says of one CVE, in a sentence, with what NVD gave as text passed through ``text``
    (the redaction)."""
    if row is None:
        return f"{cve_id}: NVD has not been asked about it"
    if row.state == store.UNKNOWN:
        return f"{cve_id}: {NOT_RECORDED}"
    parts: list[str] = []
    if row.score is not None:
        parts.append(f"CVSS {row.cvss_version} score {row.score:.1f}, rated {row.severity}")
    else:
        parts.append(f"no CVSS score yet ({row.status or 'not analysed'})")
    if row.exploited:
        since = f" since {row.exploited_on:%Y-%m-%d}" if row.exploited_on else ""
        parts.append(f"on CISA's Known Exploited Vulnerabilities list{since}, so it has been seen")
        parts[-1] += " exploited in the wild"
    if row.status == "Rejected":
        parts.append("NVD marks it Rejected, so it is not a real vulnerability")
    if row.weaknesses:
        parts.append(f"weakness {', '.join(row.weaknesses[:3])}")
    if row.description:
        parts.append(f"described as: {text(row.description, 300)}")
    return f"{cve_id}: " + "; ".join(parts)
