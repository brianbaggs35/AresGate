"""How it travelled: where each program that saw an incident sits between the internet and the
device, drawn as the path the traffic took.

A traceroute lists the routers a packet crossed. AresGate does not send probes into anyone's
network (a security tool that scans back is its own kind of problem), and it does not need to: each
program it reads sits at a known place on the way in. The firewall is at the edge, an intrusion
detection system watches just behind it, a traffic monitor watches the interface, and a host agent
is on the device itself. An incident that the firewall, Suricata and Wazuh all reported therefore
crossed all three, in that order, and what each did about it (turned it away, banned it, stopped
it) is what happened at that hop. The path is drawn from what was read, never guessed at: a program
that did not report it is not on the path.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import Final, Literal

from app.incidents import rules
from app.models import Device, Incident, IncidentSignal

Direction = Literal["inbound", "outbound"]
Kind = Literal["internet", "firewall", "detector", "monitor", "agent", "device"]

# Where each program sits on the way in, nearest the internet first, and what that makes it.
_PLACES: Final[dict[str, tuple[int, Kind]]] = {
    "opnsense": (1, "firewall"),
    "zenarmor": (1, "firewall"),
    "crowdsec": (2, "detector"),
    "suricata": (2, "detector"),
    "ntopng": (3, "monitor"),
    "wazuh": (4, "agent"),
}
_UNKNOWN: Final[tuple[int, Kind]] = (2, "detector")


@dataclass(frozen=True)
class Hop:
    kind: Kind
    # The address, the device or the program's name.
    subject: str
    # The program's key, for the hops that are one.
    source: str | None
    # How many of the incident's signals this program reported.
    alerts: int = 0
    first_at: datetime | None = None
    last_at: datetime | None = None
    # What it did about it, in words, where it says.
    note: str | None = None


@dataclass(frozen=True)
class Path:
    direction: Direction
    hops: list[Hop]


def _inside(address: str) -> bool:
    return not ip_address(address).is_global


def _direction(incident: Incident, signals: list[IncidentSignal]) -> Direction | None:
    """Which way the traffic went: in from the internet, or out from the device. None for an
    incident that is about a rule, or a network that has no inside and outside end."""
    outside = incident.subject
    try:
        if not ip_address(outside).is_global:
            return None
    except ValueError:
        return None
    for signal in signals:
        if signal.src_address is not None and signal.dst_address is not None:
            return "inbound" if str(signal.src_address) == outside else "outbound"
    return None


def _note(kind: Kind, *, blocked: int, dropped: int, banned: bool) -> str | None:
    if kind == "firewall" and blocked:
        return f"Turned it away {blocked} {'time' if blocked == 1 else 'times'}."
    if kind == "detector" and dropped:
        return f"Stopped {dropped} {'alert' if dropped == 1 else 'alerts'}."
    if kind == "detector" and banned:
        return "Banned the address."
    return None


def build(
    incident: Incident,
    signals: list[IncidentSignal],
    *,
    blocked: int,
    dropped: int,
    banned: bool,
    devices: Sequence[tuple[IPv4Address | IPv6Address, Device]],
) -> Path | None:
    """The path of an incident, or None where there is not one to draw: it has no outside address,
    no signal that says which way it went, or it is not about a device on the network."""
    direction = _direction(incident, signals)
    inside = next((str(each) for each in incident.addresses if _inside(str(each))), None)
    if direction is None or inside is None:
        return None
    seen: dict[str, list[IncidentSignal]] = {}
    for signal in signals:
        seen.setdefault(signal.source, []).append(signal)
    hops = [
        Hop(
            kind=(place := _PLACES.get(source, _UNKNOWN))[1],
            subject=rules.name_of(source),
            source=source,
            alerts=len(found),
            first_at=min(each.occurred_at for each in found),
            last_at=max(each.occurred_at for each in found),
            note=_note(place[1], blocked=blocked, dropped=dropped, banned=banned),
        )
        for source, found in sorted(
            seen.items(), key=lambda item: (_PLACES.get(item[0], _UNKNOWN)[0], item[0])
        )
    ]
    named = {str(address): device.hostname for address, device in devices}
    near = Hop("device", named.get(inside) or inside, None)
    far = Hop("internet", incident.subject, None)
    return Path(
        direction, [far, *hops, near] if direction == "inbound" else [near, *hops[::-1], far]
    )
