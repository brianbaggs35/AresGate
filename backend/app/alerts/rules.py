"""What a destination is told about, and when: one function that decides, and a preview of it.

The owner sets rules for each destination (a phone that should hear only of confirmed attacks,
a channel for the household that hears of everything serious). ``decide`` is the one place those
rules meet an incident, so that what the preview shows is what the sender (see the delivery
worker) does, and neither can drift from the other.

What is never sent, whatever the rules say: an incident the owner's verdicts quiet (every
signal in it is not suspicious or low priority), and one that is resolved or dismissed. An
incident the owner said is a real threat passes the severity and confidence floors, since they
have already decided, but still has to be of the programs and kinds the rules name. Quiet hours
hold a message, they do not drop it.

A new destination is told only of what is serious (medium or worse) and what AresGate is sure
of (the "high" band, 65 or more): the point of an alert is that it is worth being woken for.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta
from typing import Final, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.orm import Session, load_only

from app.events.event import Severity
from app.incidents import verdicts
from app.models import AlertDestination, Incident

Reason = Literal["muted", "settled", "severity", "confidence", "source", "activity"]
# In the order they are checked, which is the order a person would want to hear them in.
REASONS: Final[tuple[Reason, ...]] = (
    "muted",
    "settled",
    "severity",
    "confidence",
    "source",
    "activity",
)
# The status of an incident the owner has dealt with.
SETTLED: Final = ("resolved", "dismissed")
SEVERITY_WORDS: Final = {1: "low", 2: "medium", 3: "high", 4: "critical"}
MINUTES_A_DAY: Final = 24 * 60
# A preview goes through at most this many incidents, newest first.
PREVIEW_LIMIT: Final = 2000
PREVIEW_HOURS: Final = 24
PREVIEW_EXAMPLES: Final = 5


@dataclass(frozen=True)
class Quiet:
    """Hours in which nothing is sent: from ``start`` to ``end`` (minutes after midnight, in
    ``zone``), over midnight if ``end`` is the earlier."""

    start: int
    end: int
    zone: str
    # Whether a critical incident is still sent.
    critical_passes: bool


@dataclass(frozen=True)
class Rules:
    """What one destination is told about."""

    min_severity: int
    min_confidence: int
    # None chosen means any.
    sources: tuple[str, ...]
    activities: tuple[str, ...]
    quiet: Quiet | None
    max_per_hour: int
    detail: str
    again_when_worse: bool


def of(destination: AlertDestination) -> Rules:
    """The rules a destination was given."""
    quiet = (
        Quiet(
            destination.quiet_from,
            destination.quiet_until,
            destination.time_zone,
            destination.quiet_critical,
        )
        if destination.quiet_hours
        else None
    )
    return Rules(
        min_severity=destination.min_severity,
        min_confidence=destination.min_confidence,
        sources=tuple(destination.sources),
        activities=tuple(destination.activities),
        quiet=quiet,
        max_per_hour=destination.max_per_hour,
        detail=destination.detail,
        again_when_worse=destination.again_when_worse,
    )


@dataclass(frozen=True)
class Decision:
    """What the rules say of an incident."""

    send: bool
    # Why not, when not.
    reason: Reason | None = None
    # It is to be sent, but not until quiet hours end.
    held: bool = False


def zone_of(name: str) -> ZoneInfo | None:
    """A time zone by its name (``Europe/Berlin``), or none if there is no such zone."""
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError, ValueError, OSError:
        return None


def _local(quiet: Quiet, now: datetime) -> datetime:
    # A zone that was valid when saved can be missing after the system's zone data changes.
    return now.astimezone(zone_of(quiet.zone) or UTC)


def in_quiet(quiet: Quiet, now: datetime) -> bool:
    """Whether quiet hours are on at this moment."""
    if quiet.start == quiet.end:
        return False
    local = _local(quiet, now)
    minute = local.hour * 60 + local.minute
    if quiet.start < quiet.end:
        return quiet.start <= minute < quiet.end
    return minute >= quiet.start or minute < quiet.end


def quiet_ends(quiet: Quiet, now: datetime) -> datetime:
    """When the quiet hours that are on, or the next ones, end."""
    local = _local(quiet, now)
    ends = datetime.combine(
        local.date(), time(quiet.end // 60, quiet.end % 60), tzinfo=local.tzinfo
    )
    if ends <= local:
        ends = datetime.combine(
            local.date() + timedelta(days=1),
            time(quiet.end // 60, quiet.end % 60),
            tzinfo=local.tzinfo,
        )
    return ends.astimezone(UTC)


def set_aside(incident: Incident) -> Reason | None:
    """Why an incident is never sent to anyone, if it is not. This is the owner's word on it, and
    no rule can overrule it."""
    if incident.verdict in verdicts.MUTING:
        return "muted"
    if incident.status in SETTLED:
        return "settled"
    return None


def decide(rules: Rules, incident: Incident, now: datetime) -> Decision:
    """Whether to tell a destination of an incident, and if now."""
    aside = set_aside(incident)
    if aside is not None:
        return Decision(False, aside)
    # Having said it is a threat, the owner does not need the floors to agree.
    certain = incident.verdict == verdicts.THREAT
    if not certain and incident.severity < rules.min_severity:
        return Decision(False, "severity")
    if not certain and incident.confidence < rules.min_confidence:
        return Decision(False, "confidence")
    if rules.sources and not set(rules.sources) & set(incident.sources):
        return Decision(False, "source")
    if rules.activities and not set(rules.activities) & set(incident.activities):
        return Decision(False, "activity")
    quiet = rules.quiet
    if quiet and in_quiet(quiet, now):
        passes = quiet.critical_passes and incident.severity >= Severity.CRITICAL
        return Decision(True, held=not passes)
    return Decision(True)


def explain(reason: Reason, rules: Rules) -> str:
    """Why an incident was left out, in words."""
    if reason == "muted":
        return "You called it not suspicious or low priority"
    if reason == "settled":
        return "Already resolved or dismissed"
    if reason == "severity":
        return f"Less serious than {SEVERITY_WORDS.get(rules.min_severity, 'chosen')}"
    if reason == "confidence":
        return f"AresGate is less than {rules.min_confidence}% sure"
    if reason == "source":
        return "None of the programs you chose reported it"
    return "Not one of the kinds of activity you chose"


@dataclass(frozen=True)
class Preview:
    """What a set of rules would have done in the last day."""

    hours: int
    # Incidents that were going on in that time (those looked at, if there were too many).
    considered: int
    would_send: int
    # Of those, how many quiet hours would have held back until they ended.
    held: int
    left_out: dict[Reason, int]
    # The most that would have come in one hour, and how many of all would have been put in
    # a summary because of the limit on messages an hour. Rough: it goes by when an incident
    # began, not by when it first met the rules.
    busiest_hour: int
    over_limit: int
    # The newest few that would have been sent.
    examples: Sequence[Incident] = field(default_factory=tuple)
    # Whether there were more incidents than could be looked at.
    truncated: bool = False


def preview(db: Session, rules: Rules, now: datetime) -> Preview:
    """What the rules would have done with the incidents of the last day, so that the owner can
    see what they let through before they are saved."""
    since = now - timedelta(hours=PREVIEW_HOURS)
    going_on = Incident.last_seen_at >= since
    total = db.scalar(select(func.count()).select_from(Incident).where(going_on)) or 0
    found = db.scalars(
        select(Incident)
        .where(going_on)
        .options(
            load_only(
                Incident.id,
                Incident.title,
                Incident.severity,
                Incident.confidence,
                Incident.status,
                Incident.verdict,
                Incident.sources,
                Incident.activities,
                Incident.first_seen_at,
                Incident.last_seen_at,
            )
        )
        .order_by(Incident.last_seen_at.desc(), Incident.id.desc())
        .limit(PREVIEW_LIMIT)
    ).all()
    left_out: dict[Reason, int] = dict.fromkeys(REASONS, 0)
    sent: list[Incident] = []
    held = 0
    for incident in found:
        decision = decide(rules, incident, now)
        if decision.reason is not None:
            left_out[decision.reason] += 1
        else:
            sent.append(incident)
            held += decision.held
    hours: dict[datetime, int] = {}
    for incident in sent:
        began = (
            max(incident.first_seen_at, since)
            .astimezone(UTC)
            .replace(minute=0, second=0, microsecond=0)
        )
        hours[began] = hours.get(began, 0) + 1
    return Preview(
        hours=PREVIEW_HOURS,
        considered=len(found),
        would_send=len(sent),
        held=held,
        left_out=left_out,
        busiest_hour=max(hours.values(), default=0),
        over_limit=sum(max(0, count - rules.max_per_hour) for count in hours.values()),
        examples=tuple(sent[:PREVIEW_EXAMPLES]),
        truncated=total > len(found),
    )
