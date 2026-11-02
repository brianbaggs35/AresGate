"""Noise filters: how sure AresGate has to be of an incident before it asks about it, and which
signals are set aside without a verdict (see ``app/incidents/filters.py``). For someone signed
in."""

from datetime import timedelta
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, Request
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select

from app.api.dashboard import SEVERITY_NAMES, SeverityName
from app.api.deps import Db, SignedIn, record_audit, signed_in
from app.audit import Action, Outcome
from app.events.event import Severity
from app.incidents import attention, engine, filters, rules
from app.incidents.filters import Filters
from app.integrations import registry
from app.models import Incident, IncidentSignal, NoiseSettings, VerdictRule
from app.models.base import utcnow

router = APIRouter(
    prefix="/noise-filters", tags=["noise filters"], dependencies=[Depends(signed_in)]
)

# A floor for a program has to be something: below medium, a floor would set aside nothing the
# engine reads.
FloorName = Literal["medium", "high", "critical"]
FLOORS: dict[FloorName, Severity] = {
    "medium": Severity.MEDIUM,
    "high": Severity.HIGH,
    "critical": Severity.CRITICAL,
}
# How far back the counts of what each program reports look.
WEEK = timedelta(days=7)


class SourceOut(BaseModel):
    """A program that reports alerts, and what it has reported."""

    key: str
    name: str
    # The lowest severity that counts, or None when every alert does.
    floor: FloorName | None
    # How many alerts it reported in the last week, by severity.
    week: dict[SeverityName, int]


class NoiseOut(BaseModel):
    confidence_floor: int
    # What it is until it is changed, and where the words medium and high are drawn.
    default_floor: int
    medium_from: int
    high_from: int
    quiet_inside: bool
    sources: list[SourceOut]
    # How many verdicts there are, which set aside signals too (and are managed on their own page).
    verdicts: int
    updated_at: AwareDatetime | None


class NoiseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confidence_floor: int = Field(ge=1, le=rules.MAX_CONFIDENCE)
    quiet_inside: bool
    source_floors: dict[str, FloorName]

    @field_validator("source_floors")
    @classmethod
    def _known(cls, value: dict[str, FloorName]) -> dict[str, FloorName]:
        unknown = sorted(set(value) - set(registry.INTEGRATIONS))
        if unknown:
            raise ValueError("That isn't a program AresGate works with.")
        return value


class TallyOut(BaseModel):
    """The incidents that are going on, by how they stand."""

    active: int
    needs_you: int
    urgent: int
    unsure: int
    muted: int


class SetAsideOut(BaseModel):
    """The signals of the incidents that are going on that the filters set aside."""

    total: int
    inside: int
    severity: int
    by_source: dict[str, int]


class EffectOut(BaseModel):
    incidents: TallyOut
    set_aside: SetAsideOut


class PreviewOut(BaseModel):
    """What the filters do now, and what they would do if they were as asked."""

    now: EffectOut
    after: EffectOut


def _filters(body: NoiseIn) -> Filters:
    return Filters(
        confidence_floor=body.confidence_floor,
        quiet_inside=body.quiet_inside,
        source_floors={source: int(FLOORS[name]) for source, name in body.source_floors.items()},
    )


def _floor_name(value: int) -> FloorName | None:
    return next((name for name, level in FLOORS.items() if level == value), None)


def _sources(db: Db, noise: Filters) -> list[SourceOut]:
    """The programs that reported an alert in the last week or have a floor, in the order the
    integrations are listed in."""
    rows = db.execute(
        select(IncidentSignal.source, IncidentSignal.severity, func.count())
        .where(
            IncidentSignal.kind != "decision",
            IncidentSignal.occurred_at >= utcnow() - WEEK,
        )
        .group_by(IncidentSignal.source, IncidentSignal.severity)
    ).all()
    week: dict[str, dict[SeverityName, int]] = {}
    for source, severity, count in rows:
        week.setdefault(source, {})[SEVERITY_NAMES[Severity(severity)]] = count
    known = [key for key in registry.INTEGRATIONS if key in week or key in noise.source_floors]
    return [
        SourceOut(
            key=key,
            name=rules.name_of(key),
            floor=_floor_name(noise.source_floors[key]) if key in noise.source_floors else None,
            week=week.get(key, {}),
        )
        for key in known
    ]


def _shown(db: Db) -> NoiseOut:
    noise = filters.load(db)
    row = db.get(NoiseSettings, 1)
    return NoiseOut(
        confidence_floor=noise.confidence_floor,
        default_floor=filters.DEFAULT_FLOOR,
        medium_from=rules.MEDIUM_FROM,
        high_from=rules.HIGH_FROM,
        quiet_inside=noise.quiet_inside,
        sources=_sources(db, noise),
        verdicts=db.scalar(select(func.count()).select_from(VerdictRule)) or 0,
        updated_at=row.updated_at if row else None,
    )


def _effect(db: Db, floor: int) -> EffectOut:
    """What the filters do to the incidents that are going on, as they are stored."""
    found = attention.tally(db, floor)
    rows = db.execute(
        select(IncidentSignal.source, IncidentSignal.filtered_by, func.count())
        .join(Incident, Incident.id == IncidentSignal.incident_id)
        .where(Incident.status.in_(attention.ACTIVE), IncidentSignal.filtered_by.is_not(None))
        .group_by(IncidentSignal.source, IncidentSignal.filtered_by)
    ).all()
    by_source: dict[str, int] = {}
    by_reason = {filters.INSIDE: 0, filters.SEVERITY: 0}
    for source, reason, count in rows:
        by_source[source] = by_source.get(source, 0) + count
        by_reason[cast(str, reason)] += count
    return EffectOut(
        incidents=TallyOut(
            active=found.active,
            needs_you=found.needs_you,
            urgent=found.urgent,
            unsure=found.unsure,
            muted=found.muted,
        ),
        set_aside=SetAsideOut(
            total=sum(by_source.values()),
            inside=by_reason[filters.INSIDE],
            severity=by_reason[filters.SEVERITY],
            by_source=by_source,
        ),
    )


def _facts(was: Filters, now: Filters) -> dict[str, str | int | bool]:
    """What the audit log says of a change: each setting that changed, and what it was."""
    facts: dict[str, str | int | bool] = {}
    if was.confidence_floor != now.confidence_floor:
        facts["confidence_floor"] = now.confidence_floor
        facts["from_confidence_floor"] = was.confidence_floor
    if was.quiet_inside != now.quiet_inside:
        facts["quiet_inside"] = now.quiet_inside
        facts["from_quiet_inside"] = was.quiet_inside
    if dict(was.source_floors) != dict(now.source_floors):
        facts["source_floors"] = _written(now)
        facts["from_source_floors"] = _written(was)
    return facts


def _written(noise: Filters) -> str:
    """``wazuh=high, ntopng=medium``: the floors of the programs that have one."""
    return ", ".join(
        f"{source}={_floor_name(level) or level}"
        for source, level in sorted(noise.source_floors.items())
    )


@router.get("")
def get_noise_filters(db: Db) -> NoiseOut:
    """The filters as they are saved, and what each program reported in the last week."""
    return _shown(db)


@router.put("")
def change_noise_filters(
    body: NoiseIn,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
) -> NoiseOut:
    """Sets the filters. The incidents that are going on are judged again at once, so what they
    say and what the dashboard counts follow the filters; those that are over keep what was said
    at the time."""
    engine.hold(db)
    was = filters.load(db)
    noise = _filters(body)
    if filters.save(db, noise):
        record_audit(
            db,
            request,
            Action.NOISE_FILTERS_CHANGED,
            Outcome.SUCCESS,
            user=auth.user,
            detail=_facts(was, noise),
        )
        engine.reapply(db)
        db.commit()
    return _shown(db)


@router.post("/preview")
def preview_noise_filters(body: NoiseIn, db: Db) -> PreviewOut:
    """What the filters would do if they were as asked, without changing them: the incidents are
    judged as they would be, counted, and put back."""
    now = _effect(db, filters.load(db).confidence_floor)
    asked = _filters(body)
    trial = db.begin_nested()
    try:
        engine.hold(db)
        filters.save(db, asked)
        engine.reapply(db)
        db.flush()
        after = _effect(db, asked.confidence_floor)
    finally:
        trial.rollback()
    return PreviewOut(now=now, after=after)
