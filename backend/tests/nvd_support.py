"""Incidents that name CVEs, and what NVD said of them, for the tests of what reads them."""

import itertools
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models import Incident, IncidentSignal, NvdCve
from app.nvd import lookup, store
from tests.nvd_body import LOG4SHELL
from tests.test_incidents_search import incident as make_incident

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
_events = itertools.count(9_000_000)


def incident_naming(
    session: Session,
    *texts: str,
    seen: timedelta = timedelta(hours=1),
    evidence: dict[str, Any] | None = None,
    name: str | None = None,
) -> Incident:
    """An incident last seen ``seen`` before ``NOW``, one of whose signals says each text."""
    found = make_incident(
        session,
        name or f"incident-{next(_events)}",
        first_seen_at=NOW - seen - timedelta(minutes=5),
        last_seen_at=NOW - seen,
    )
    for text in texts:
        session.add(
            IncidentSignal(
                incident_id=found.id,
                event_id=next(_events),
                occurred_at=NOW - seen,
                source="wazuh",
                kind="alert",
                severity=2,
                summary=text,
                signature=None,
                evidence=evidence,
            )
        )
    session.flush()
    return found


def kept(
    session: Session,
    cve_id: str = LOG4SHELL,
    *,
    checked: timedelta = timedelta(0),
    **changes: Any,
) -> NvdCve:
    """What NVD said of a CVE, asked ``checked`` before ``NOW``, kept."""
    fields: dict[str, Any] = {
        "cve_id": cve_id,
        "status": "Analyzed",
        "cvss_version": "3.1",
        "score": 10.0,
        "severity": "CRITICAL",
        "description": "Apache Log4j2 JNDI features do not protect against LDAP.",
        "weaknesses": ["CWE-917"],
        "exploited": True,
        "exploited_on": date(2021, 12, 10),
    }
    fields.update(changes)
    record = lookup.Record(**fields)
    row = store.keep(session, cve_id, lookup.Found(record), NOW - checked)
    assert row is not None
    session.flush()
    return row
