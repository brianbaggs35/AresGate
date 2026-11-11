"""Whether an agent has what it needs to do its job, in words the owner can act on.

A kind of agent is only as good as what AresGate can show it: an intelligence analyst with no
VirusTotal key has nothing to read, and a threat hunter with no firewall connected has few
alerts. Each template names what it needs (app/agents/catalog.py) and this says, for each, whether
it is there and, when it is not, where to get it.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Final

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.catalog import Template
from app.ai import gateway
from app.models import Device, IntegrationConnection

PURPOSE: Final = "agent"
# The programs that tell AresGate about alerts and what the firewall turned away.
ALERT_SOURCES: Final = ("opnsense", "wazuh", "crowdsec", "ntopng")


@dataclass(frozen=True)
class Check:
    """One thing an agent needs: whether it is there, what it is, and, when it is not, what to do
    and where in the web app to do it."""

    key: str
    ok: bool
    text: str
    fix: str
    link: str


def _connected(db: Session, names: tuple[str, ...]) -> bool:
    return bool(
        db.scalar(
            select(func.count())
            .select_from(IntegrationConnection)
            .where(IntegrationConnection.integration.in_(names))
        )
    )


def _ai(db: Session, now: datetime) -> Check:
    reason = gateway.availability(db, now, PURPOSE)
    return Check(
        "ai",
        reason is None,
        "An AI provider for the agents to ask",
        reason or "",
        "/settings/agents",
    )


def _alerts(db: Session, now: datetime) -> Check:
    return Check(
        "alerts",
        _connected(db, ALERT_SOURCES),
        "A firewall or sensor that reports alerts, such as OPNsense or Wazuh",
        "Connect OPNsense, Wazuh, ntopng or CrowdSec, so that there is something to look at.",
        "/integrations",
    )


def _firewall(db: Session, now: datetime) -> Check:
    return Check(
        "firewall",
        _connected(db, ("opnsense",)),
        "OPNsense connected, for what the firewall turned away",
        "Connect OPNsense, which AresGate asks what the firewall blocked.",
        "/integrations/opnsense",
    )


def _intel(db: Session, now: datetime) -> Check:
    return Check(
        "intel",
        _connected(db, ("virustotal",)),
        "VirusTotal connected, for what is known about addresses",
        "Add a free VirusTotal key, which AresGate uses to ask who an address belongs to.",
        "/integrations/virustotal",
    )


def _integrations(db: Session, now: datetime) -> Check:
    return Check(
        "integrations",
        _connected(db, (*ALERT_SOURCES, "virustotal")),
        "At least one integration connected, to watch",
        "Connect an integration first: there is nothing to watch the health of yet.",
        "/integrations",
    )


def _devices(db: Session, now: datetime) -> Check:
    return Check(
        "devices",
        bool(db.scalar(select(func.count()).select_from(Device))),
        "Devices AresGate has seen on the network",
        "Connect OPNsense or ntopng, which tell AresGate which devices are on the network.",
        "/integrations",
    )


NEEDS: Final = {
    "ai": _ai,
    "alerts": _alerts,
    "firewall": _firewall,
    "intel": _intel,
    "integrations": _integrations,
    "devices": _devices,
}


def checks(db: Session, now: datetime, template: Template) -> list[Check]:
    """What the template needs, each with whether it is there."""
    return [NEEDS[key](db, now) for key in template.needs]


def ready(found: list[Check]) -> bool:
    return all(check.ok for check in found)
