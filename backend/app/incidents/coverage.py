"""What more an incident would say if more of the programs were connected.

Each program sees the network its own way, and what it adds to an incident is different: the more
of them are connected, the more an incident says. Here is what each of the ones AresGate reads
would add, for the ones that are not connected, so that a page can say what is being missed and
point to where to connect it.
"""

from dataclasses import dataclass
from typing import Final

from sqlalchemy.orm import Session

from app.integrations import registry, service

# What each integration adds to an incident, in a sentence, by its key.
OFFERS: Final = {
    "opnsense": (
        "Suricata's rule details, the host names and web addresses seen in the traffic, "
        "and every time the firewall turned the address away."
    ),
    "wazuh": (
        "The log line an alert came from, the MITRE ATT&CK technique, the machine it was about "
        "and the vulnerabilities found on it."
    ),
    "ntopng": (
        "Who each flow was between, what service it was, how long it lasted and how much it "
        "carried, ntopng's own score and where the address is."
    ),
    "crowdsec": "The bans the community's blocklist gave the address and why.",
    "virustotal": (
        "What the antivirus and security engines make of each address on the internet, and who "
        "it belongs to."
    ),
}


@dataclass(frozen=True)
class Missing:
    """An integration that is not connected, and what it would add."""

    source: str
    adds: str


def missing(db: Session) -> list[Missing]:
    """The integrations that are not connected (one that is saved but failing counts as not), with
    what each would add, in the order they are listed in."""
    return [
        Missing(key, adds)
        for key, adds in OFFERS.items()
        if key in registry.INTEGRATIONS
        and service.integration_status(service.rows_for(db, key)) != service.Status.CONNECTED
    ]
