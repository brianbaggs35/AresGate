"""What a message to a destination says of an incident, in the words of the incident's own page.

Three levels of detail, chosen for each destination, because Discord keeps what is posted there:

- ``brief``: what kind of thing it is, how serious, how sure AresGate is, and a link. No address
  and no name of anything on the network.
- ``standard``: adds the address it came from when that is on the internet, and the programs that
  saw it.
- ``full``: adds what the strongest alert said and the devices on the network it touched, by name.
  For a channel only the owner can read.

A destination that is told of threats only gets a different message (``threat_message``): it
says what stage the attack has reached and why AresGate thinks it is real, in the words of the
incident's Where it stands card, so the owner can judge from the channel whether to get up. Such a
message is later changed to say it was stood down (``stood_down_message``) when the incident turns
out not to be a threat, instead of being left standing.

Whatever the level, a message holds no credential and no raw log line, and what the network said
(an alert's words, a device's name, which an attacker can choose) is put in a code span, where
Discord shows it as plain text: it can't format the message, make a link or ping anyone. The
message itself is built by ``app.alerts.discord.message``, which also says nobody may be pinged.
"""

from collections.abc import Sequence
from datetime import datetime
from ipaddress import ip_address
from typing import Final

from app.alerts import discord
from app.alerts.rules import SEVERITY_WORDS
from app.incidents.episode import ACTIVITY_NAMES
from app.integrations import registry
from app.models import Incident
from app.threats import explain, stages
from app.threats.settings import Tuning

# At most this many incidents are named in a summary; the rest are counted.
SUMMARY_NAMES: Final = 5
# What an incident is said to be when its kind of activity is not known.
GENERIC: Final = "suspicious activity"
_COLORS: Final = {1: discord.BLUE, 2: discord.AMBER, 3: discord.RED, 4: discord.RED}
# The most of an alert's own words, or a device's name, that is quoted.
_QUOTED: Final = 200

# A device on the network an incident touched: its address and what it is called.
Device = tuple[str, str]
# What a threat is called by how far it has got, as the start of the title of its message.
_THREAT_TITLES: Final = {
    stages.FOOTHOLD: "Possible break-in",
    stages.ACCESS: "Attack in progress",
}
_THREAT: Final = "Threat"
_SAMPLE_ADDRESS: Final = "93.184.216.34"


def _code(text: str, limit: int = _QUOTED) -> str:
    """Words from the network, as plain text in a message: collapsed to one line, cut short, and
    in a code span, which Discord does not format, link or ping from. A backtick would end the span,
    so none is let through."""
    said = " ".join(text.replace("`", "'").split())
    return f"`{said if len(said) <= limit else said[: limit - 1] + '…'}`"


def link_to(origin: str, incident_id: int | None = None) -> str:
    """Where the incident is in AresGate, or the list when there is none."""
    return f"{origin}/incidents/{incident_id}" if incident_id else f"{origin}/incidents"


def what_of(incident: Incident) -> str:
    """What kind of thing the incident is, in a few words and with no address in them."""
    names = [name for key, name in ACTIVITY_NAMES.items() if key in incident.activities]
    return " and ".join(names) if names else GENERIC


def _outside(subject: str) -> str | None:
    """The subject of an incident if it is an address on the internet. (A device on the network is
    not told except at the full level, and a rule is not an address.)"""
    try:
        return subject if ip_address(subject).is_global else None
    except ValueError:
        return None


def _headline(incident: Incident, detail: str) -> str:
    word = SEVERITY_WORDS.get(incident.severity, "unusual")
    text = f"{word.capitalize()}-severity {what_of(incident)}"
    outside = _outside(incident.subject) if detail != "brief" else None
    return f"{text} from {outside}" if outside else text


def _programs(incident: Incident) -> str:
    names = [
        registry.INTEGRATIONS[key].name if key in registry.INTEGRATIONS else key
        for key in incident.sources
    ]
    return ", ".join([*names[:-2], " and ".join(names[-2:])]) if names else "a program"


def incident_message(
    incident: Incident,
    *,
    reason: str,
    detail: str,
    origin: str,
    devices: Sequence[Device] = (),
    sample: bool = False,
    at: datetime,
) -> dict[str, object]:
    """The message for an incident that is new to a destination, got worse or was reopened."""
    headline = _headline(incident, detail)
    title = {
        "worse": f"Got worse: {headline}",
        "reopened": f"Reopened: {headline}",
    }.get(reason, headline)
    sure = f"AresGate is {incident.confidence}% sure this is a real attack."
    lines = [f"You said it is a real threat. {sure}" if incident.verdict == "threat" else sure]
    if reason == "worse":
        lines.insert(0, "It has got worse since the last message about it.")
    elif reason == "reopened":
        lines.insert(0, "You had dealt with this, and it is open again.")
    if detail != "brief":
        lines.append(f"Reported by {_programs(incident)}, {incident.signal_count} signals so far.")
    if detail == "full":
        lines.append(f"The strongest alert said: {_code(incident.top_summary)}")
        if devices:
            named = ", ".join(_code(f"{name} ({address})", 80) for address, name in devices[:5])
            lines.append(f"On your network: {named}.")
    url = link_to(origin, incident.id)
    lines.append(f"[Open the incident]({url}) to see what was seen and why.")
    return discord.message(
        title=title,
        description="\n".join(lines),
        color=_COLORS.get(incident.severity, discord.BLUE),
        footer="AresGate · sample alert" if sample else "AresGate · alert",
        link=url,
        at=at,
    )


def summary_message(
    *,
    reason: str,
    covers: int,
    named: Sequence[Incident],
    detail: str,
    origin: str,
    max_per_hour: int,
    at: datetime,
) -> dict[str, object]:
    """One message in place of several: what was held back because a destination allows only so
    many an hour, or what came in during quiet hours."""
    many = f"{covers} incident" + ("" if covers == 1 else "s")
    if reason == "quiet":
        title = f"{many} came in during quiet hours"
        why = "These came in while quiet hours were on, so they were held until now."
    else:
        title = f"{many} held back"
        why = (
            f"This channel allows {max_per_hour} messages an hour, so these were not sent one "
            "by one."
        )
    lines = [why]
    shown = named[:SUMMARY_NAMES]
    lines.extend(
        f"• {_headline(incident, detail)}: [open]({link_to(origin, incident.id)})"
        for incident in shown
    )
    if covers > len(shown):
        lines.append(f"…and {covers - len(shown)} more.")
    lines.append(f"[Open the incidents]({link_to(origin)}) to see them all.")
    return discord.message(
        title=title,
        description="\n".join(lines),
        color=discord.AMBER,
        footer="AresGate · summary",
        link=link_to(origin),
        at=at,
    )


def _stage_path(incident: Incident) -> str | None:
    """The stages an incident went through, in the order of the path, the furthest in bold."""
    names = [stages.NAMES[stage] for stage in stages.STAGES if stage in incident.stages]
    if not names:
        return None
    return " → ".join([*names[:-1], f"**{names[-1]}**"])


def _threat_title(incident: Incident, detail: str) -> str:
    furthest = stages.STAGES[stages.depth(incident.stages) - 1] if incident.stages else ""
    return f"{_THREAT_TITLES.get(furthest, _THREAT)}: {_headline(incident, detail)}"


def _bullets(lines: Sequence[str]) -> list[str]:
    return [f"• {line}" for line in lines]


def threat_message(
    incident: Incident,
    *,
    reason: str,
    detail: str,
    origin: str,
    why: Sequence[str],
    devices: Sequence[Device] = (),
    sample: bool = False,
    at: datetime,
) -> dict[str, object]:
    """The message for an incident that has become a threat, or has escalated. ``why`` is what put
    it on the Threats page, one fact to a line (see ``app.threats.explain``)."""
    title = _threat_title(incident, detail)
    lead = f"AresGate is {incident.confidence}% sure this is a real attack, and it is going on now."
    if incident.verdict == "threat":
        lead = f"You said it is a real threat. {lead}"
    if reason == "worse":
        title = f"Escalated: {title}"
        lead = f"It has gone further since the last message about it. {lead}"
    elif reason == "reopened":
        title = f"Reopened: {title}"
        lead = f"This was dealt with or stood down earlier, and it is a threat again. {lead}"
    lines = [lead]
    if why:
        lines.extend(["", "**Why AresGate thinks so**", *_bullets(why)])
    url = link_to(origin, incident.id)
    lines.extend(["", f"[Open the incident]({url}) to see what was seen and why."])
    fields: list[discord.Field] = []
    path = _stage_path(incident)
    if path:
        fields.append(("How far it got", path, False))
    fields.append(("How sure", f"{incident.confidence}%", True))
    fields.append(
        ("How serious", SEVERITY_WORDS.get(incident.severity, "unusual").capitalize(), True)
    )
    outside = _outside(incident.subject) if detail != "brief" else None
    if outside:
        fields.append(("Seen from", f"`{outside}`", True))
    if detail == "full":
        if devices:
            named = ", ".join(_code(f"{name} ({address})", 80) for address, name in devices[:5])
            fields.append(("On your network", named, False))
        fields.append(("The strongest alert said", _code(incident.top_summary), False))
    return discord.message(
        title=title,
        description="\n".join(lines),
        color=_COLORS.get(incident.severity, discord.BLUE),
        footer="AresGate · sample alert" if sample else "AresGate · threat alert",
        link=url,
        fields=fields,
        at=at,
    )


def stood_down_message(
    incident: Incident,
    *,
    detail: str,
    origin: str,
    why: Sequence[str],
    at: datetime,
) -> dict[str, object]:
    """What a message about a threat is changed to when the incident is no longer one: the owner
    called it harmless, someone resolved it, or the AI judged it background. It says so and why,
    in place of leaving a warning standing in the channel."""
    url = link_to(origin, incident.id)
    lines = ["This is no longer a threat, so there is nothing to do about it now."]
    if why:
        lines.extend(["", *_bullets(why)])
    lines.extend(
        [
            "",
            "AresGate will not alert on it again unless that changes.",
            f"[Open the incident]({url}) to see it.",
        ]
    )
    return discord.message(
        title=f"Stood down: {_headline(incident, detail)}",
        description="\n".join(lines),
        color=discord.GREY,
        footer="AresGate · stood down",
        link=url,
        at=at,
    )


def sample_incident(at: datetime) -> Incident:
    """An incident that is made up, for showing the owner what a message looks like. It is never
    saved."""
    return Incident(
        id=0,
        subject=_SAMPLE_ADDRESS,
        title="Sample",
        severity=3,
        confidence=88,
        status="open",
        first_seen_at=at,
        last_seen_at=at,
        signal_count=14,
        sources=["opnsense", "wazuh"],
        activities=["scan"],
        stages=[stages.RECON, stages.ACCESS],
        top_source="wazuh",
        top_summary="Exploit attempt against the web server on port 8080",
        verdict=None,
    )


def sample_message(
    *, mode: str, reason: str, detail: str, origin: str, at: datetime
) -> dict[str, object]:
    """The message a destination would send, for an incident that is made up: the same code as a
    real one, so that what is shown is what arrives."""
    found = sample_incident(at)
    devices = [("192.168.1.24", "living-room-tv")] if detail == "full" else []
    if mode == "threats":
        return threat_message(
            found,
            reason=reason,
            detail=detail,
            origin=origin,
            why=explain.why(found, 35, Tuning()),
            devices=devices,
            sample=True,
            at=at,
        )
    return incident_message(
        found, reason=reason, detail=detail, origin=origin, devices=devices, sample=True, at=at
    )
