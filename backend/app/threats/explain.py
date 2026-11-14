"""Why an incident is where it is, in plain words, one fact to a line.

A person told "this is a threat" or "this is background" can only trust it if they can see why, and
disagree. The reasons are worked out from the same facts ``app/incidents/attention.py`` judges by,
and a test holds them to agreeing with its lanes.
"""

from app.incidents import attention
from app.incidents.attention import Lane, Standing
from app.models import Incident
from app.threats import calls, stages
from app.threats.settings import Tuning

KINDS = {
    "compromise": "a compromise",
    "attack": "an attack",
    "probe": "a probe",
    "noise": "noise",
    "unclear": "unclear",
}
BASES = {
    "owner": "You said so",
    "reading": "The AI read this incident",
    "family": "The AI judged this kind of incident",
}


def _said(incident: Incident) -> str:
    """What the AI or the owner thinks of the incident, as a sentence."""
    basis = BASES.get(incident.ai_basis or "", "The AI")
    kind = KINDS.get(incident.ai_class or "", "unclear")
    return f"{basis}: it is {kind}, {incident.ai_confidence}% sure."


def _chain(incident: Incident) -> str:
    seen = " then ".join(incident.stages or [])
    if stages.FOOTHOLD in (incident.stages or []):
        return f"It shows a sign that an attack worked, not only an attempt ({seen})."
    return f"It is more than scanning: it went through {len(incident.stages)} stages ({seen})."


def _linked(incident: Incident) -> str:
    kind = "an attack" if incident.chain_link == "confirmed" else "a possible attack"
    where = "got in" if incident.chain_role == "attacker" else "called out afterwards"
    said = f"It is a step of {kind} across two devices: it {where}."
    return f"{said} {incident.chain_reason}" if incident.chain_reason else said


def _threat(incident: Incident, tuning: Tuning) -> list[str]:
    lines: list[str] = []
    if incident.verdict == "threat":
        lines.append("You said it is a real threat.")
    if incident.chain_id is not None:
        lines.append(_linked(incident))
    if stages.is_chain(incident.stages or []):
        lines.append(_chain(incident))
    sure = incident.ai_confidence
    if incident.ai_class in calls.LOUD and sure is not None and sure >= tuning.threat_from:
        lines.append(_said(incident))
    if incident.confidence >= tuning.threat_from:
        critical = incident.severity >= attention.CLEARABLE_BELOW
        if critical and tuning.confirming:
            lines.append(
                f"AresGate's rules are {incident.confidence}% sure and it is critical, which "
                "does not wait for the AI to agree."
            )
        elif not tuning.confirming:
            lines.append(f"AresGate's rules are {incident.confidence}% sure it is a real attack.")
    return lines


def _suspect(incident: Incident, tuning: Tuning) -> list[str]:
    lines = [f"AresGate's rules are {incident.confidence}% sure it is a real attack."]
    if tuning.confirming and incident.confidence >= tuning.threat_from:
        if incident.ai_class is None:
            lines.append("It becomes a threat when the AI agrees, and it hasn't judged this yet.")
        else:
            lines.append(_said(incident))
            lines.append("That isn't enough to call it a threat, or to set it aside.")
    elif incident.ai_class is not None:
        lines.append(_said(incident))
    if incident.ai_basis == "owner" and incident.ai_class is None:
        lines.append("You asked to keep an eye on this kind, so it is never set aside.")
    return lines


def why(incident: Incident, floor: int, tuning: Tuning) -> list[str]:
    """The reasons for the lane an incident is in."""
    found = attention.standing(incident, floor, tuning)
    if found is Standing.HANDLED:
        return [f"It is {incident.status}: someone has dealt with it."]
    if found is Standing.MUTED:
        return ["You called it not suspicious or low priority, so it never raises an alarm."]
    if found is Standing.UNSURE:
        asked = floor + tuning.shift(incident.importance)
        return [
            f"AresGate's rules are {incident.confidence}% sure it is a real attack, below the "
            f"{asked}% you ask for before it is shown to you."
        ]
    if found is Standing.AI_CLEARED:
        return [
            _said(incident),
            f"That is at least the {tuning.clear_from}% you ask for before the AI sets "
            "something aside, and nothing in it is more than scanning.",
        ]
    if attention.is_threat(incident, floor, tuning):
        return _threat(incident, tuning)
    return _suspect(incident, tuning)


def lane_name(lane: Lane | None) -> str:
    """A lane as the API says it: ``none`` for an incident that is in no lane."""
    return "none" if lane is None else lane.value
