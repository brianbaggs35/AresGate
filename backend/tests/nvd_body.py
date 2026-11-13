"""Answers shaped like the ones NVD's CVE API 2.0 gives, for the tests of what reads them."""

import json
from typing import Any

LOG4SHELL = "CVE-2021-44228"


def metric_v31(
    score: float = 10.0,
    rating: str = "CRITICAL",
    *,
    source: str = "nvd@nist.gov",
    primary: bool = True,
) -> dict[str, Any]:
    return {
        "source": source,
        "type": "Primary" if primary else "Secondary",
        "cvssData": {
            "version": "3.1",
            "vectorString": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H",
            "baseScore": score,
            "baseSeverity": rating,
        },
    }


def metric_v2(score: float = 9.3, rating: str = "HIGH") -> dict[str, Any]:
    """CVSS 2 gives the rating beside the data, not in it."""
    return {
        "source": "nvd@nist.gov",
        "type": "Primary",
        "cvssData": {
            "version": "2.0",
            "vectorString": "AV:N/AC:M/Au:N/C:C/I:C/A:C",
            "baseScore": score,
        },
        "baseSeverity": rating,
    }


def cve(cve_id: str = LOG4SHELL, **changes: Any) -> dict[str, Any]:
    """One entry of ``vulnerabilities``, listed in CISA's exploited catalog."""
    inner: dict[str, Any] = {
        "id": cve_id,
        "sourceIdentifier": "security@apache.org",
        "published": "2021-12-10T10:15:09.143",
        "lastModified": "2025-10-27T16:15:38.223",
        "vulnStatus": "Analyzed",
        "cveTags": [],
        "descriptions": [
            {"lang": "en", "value": "Apache Log4j2 JNDI features do not protect against LDAP."},
            {"lang": "es", "value": "Las caracteristicas JNDI de Apache Log4j2."},
        ],
        "metrics": {"cvssMetricV31": [metric_v31()], "cvssMetricV2": [metric_v2()]},
        "weaknesses": [
            {
                "source": "nvd@nist.gov",
                "type": "Primary",
                "description": [
                    {"lang": "en", "value": "CWE-917"},
                    {"lang": "en", "value": "CWE-20"},
                ],
            }
        ],
        "cisaExploitAdd": "2021-12-10",
        "cisaActionDue": "2021-12-24",
        "cisaRequiredAction": (
            "For all affected software assets, apply updates per vendor instructions."
        ),
        "cisaVulnerabilityName": "Apache Log4j2 Remote Code Execution Vulnerability",
        "references": [{"url": "https://example.org/advisory", "source": "security@apache.org"}],
    }
    inner.update(changes)
    return {"cve": {key: value for key, value in inner.items() if value is not None}}


def body(*entries: dict[str, Any]) -> str:
    """The text of an answer that lists the CVEs."""
    return json.dumps(
        {
            "resultsPerPage": len(entries),
            "startIndex": 0,
            "totalResults": len(entries),
            "format": "NVD_CVE",
            "version": "2.0",
            "timestamp": "2026-11-13T12:00:00.000",
            "vulnerabilities": list(entries),
        }
    )
