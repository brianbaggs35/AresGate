"""Incident response: what was done about the incidents of the last few days, and which still
wait for an answer, from what AresGate has read of CrowdSec, the firewall and Suricata. For
someone signed in."""

from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime, BaseModel

from app.api.dashboard import SEVERITY_NAMES, SeverityName
from app.api.deps import Db, signed_in
from app.events.event import Severity
from app.incidents import respond
from app.incidents.response import State

router = APIRouter(
    prefix="/incident-response", tags=["incident response"], dependencies=[Depends(signed_in)]
)

Status = Literal["open", "investigating", "resolved", "dismissed"]


class ResponseItem(BaseModel):
    """One incident and what was done about it."""

    id: int
    title: str
    # The address it is about, or rule:<integration>:<rule> where it names none.
    subject: str
    severity: SeverityName
    status: Status
    last_seen_at: AwareDatetime
    # What was done, as the incident's own page says it, and in words.
    state: State
    label: str
    # Why it needs a response, for one that does.
    why: str | None
    # How many addresses are banned now and how many it has to have banned, and when the last
    # of the bans runs out (none when one doesn't say how long it lasts).
    banned_now: int
    attackers: int
    ban_ends_at: AwareDatetime | None
    # How often the firewall turned the address away, and how many alerts Suricata stopped.
    blocked: int
    dropped: int


class ResponseGroup(BaseModel):
    key: respond.GroupKey
    label: str
    description: str
    # All the incidents in it, the most serious first.
    items: list[ResponseItem]


class ResponseOverview(BaseModel):
    days: int
    # How serious an incident has to be to be here.
    minimum: SeverityName
    # How many incidents there were in all, which is more than the groups hold past the limit.
    total: int
    shown: int
    # Whether CrowdSec and OPNsense are connected: if not, nothing can be seen of what they did.
    crowdsec_connected: bool
    opnsense_connected: bool
    groups: list[ResponseGroup]


def _out(item: respond.Item) -> ResponseItem:
    incident = item.incident
    return ResponseItem(
        id=incident.id,
        title=incident.title,
        subject=incident.subject,
        severity=SEVERITY_NAMES[Severity(incident.severity)],
        status=cast(Status, incident.status),
        last_seen_at=incident.last_seen_at,
        state=item.done.state,
        label=item.done.label,
        why=item.why,
        banned_now=item.banned_now,
        attackers=item.attackers,
        ban_ends_at=item.ban_ends_at,
        blocked=item.done.tally.blocked,
        dropped=item.done.tally.dropped,
    )


@router.get("")
def get_overview(
    db: Db,
    days: Annotated[
        int,
        Query(ge=1, le=max(respond.DAYS), description="How many days back to look."),
    ] = 7,
) -> ResponseOverview:
    """Every incident of medium severity or higher that went on in the last days, in the group
    that says what was done about it: those that need a response first."""
    found = respond.overview(db, days)
    return ResponseOverview(
        days=found.days,
        minimum=SEVERITY_NAMES[respond.MINIMUM],
        total=found.total,
        shown=len(found.items),
        crowdsec_connected=found.crowdsec_connected,
        opnsense_connected=found.opnsense_connected,
        groups=[
            ResponseGroup(
                key=key,
                label=label,
                description=description,
                items=[_out(item) for item in found.items if item.group == key],
            )
            for key, (label, description) in respond.GROUPS.items()
        ],
    )
