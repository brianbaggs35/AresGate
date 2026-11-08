"""What a message to a destination says of an incident, in the words of the incident's own page.

Three levels of detail, chosen for each destination, because Discord keeps what is posted there:

- ``brief``: what kind of thing it is, how serious, how sure AresGate is, and a link. No address
  and no name of anything on the network.
- ``standard``: adds the address it came from when that is on the internet, and the programs that
  saw it.
- ``full``: adds what the strongest alert said and the devices on the network it touched, by name.
  For a channel only the owner can read.

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

# At most this many incidents are named in a summary; the rest are counted.
SUMMARY_NAMES: Final = 5
# What an incident is said to be when its kind of activity is not known.
GENERIC: Final = "suspicious activity"
_COLORS: Final = {1: discord.BLUE, 2: discord.AMBER, 3: discord.RED, 4: discord.RED}
# The most of an alert's own words, or a device's name, that is quoted.
_QUOTED: Final = 200

# A device on the network an incident touched: its address and what it is called.
Device = tuple[str, str]


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
        footer="AresGate · alert",
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
