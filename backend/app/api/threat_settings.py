"""Threat detection settings: how sure it takes to call an incident a threat, whether the AI may set
things aside as background, and what the network is like, so that what is normal there is known.
For someone signed in."""

from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, Request
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app.api.deps import Db, SignedIn, record_audit, signed_in
from app.audit import Action, Outcome
from app.incidents import attention, filters
from app.models import ThreatSettings
from app.threats import settings
from app.threats.settings import Tuning

router = APIRouter(
    prefix="/threat-settings", tags=["threat detection"], dependencies=[Depends(signed_in)]
)

Exposure = Literal["none", "some", "unknown"]
MAX_PORT = 65535


class ThreatSettingsOut(BaseModel):
    threat_from: int
    ai_may_clear: bool
    clear_from: int
    ai_confirms: bool
    exposure: Exposure
    exposed_ports: list[int]
    notes: str
    # How many points the bar to be shown moves for an incident that touched an important device
    # (down) and one that touched only guest or IoT devices (up).
    important_drop: int
    low_raise: int
    # Whether the AI may give a verdict that clears an incident it is sure is a false positive.
    ai_gives_verdicts: bool
    # What each is until it is changed, and the lowest the AI's bar can be.
    default_threat_from: int
    default_clear_from: int
    default_important_drop: int
    default_low_raise: int
    max_shift: int
    min_clear_from: int
    max_notes: int
    max_ports: int
    # Whether an AI is watching (on, with a provider, and reading by itself), which is when its
    # agreement is needed for a threat and what it may set aside.
    watching: bool
    updated_at: AwareDatetime | None


class ThreatSettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    threat_from: int = Field(ge=1, le=100)
    ai_may_clear: bool
    clear_from: int = Field(ge=settings.MIN_CLEAR_FROM, le=100)
    ai_confirms: bool
    exposure: Exposure
    exposed_ports: list[Annotated[int, Field(ge=1, le=MAX_PORT)]] = Field(
        default_factory=list[int], max_length=settings.MAX_PORTS
    )
    notes: str = Field(default="", max_length=settings.MAX_NOTES)
    important_drop: int = Field(
        default=settings.DEFAULT_IMPORTANT_DROP, ge=0, le=settings.MAX_SHIFT
    )
    low_raise: int = Field(default=settings.DEFAULT_LOW_RAISE, ge=0, le=settings.MAX_SHIFT)
    ai_gives_verdicts: bool = False

    @field_validator("notes")
    @classmethod
    def _plain(cls, value: str) -> str:
        return " ".join(value.split())


class LanesOut(BaseModel):
    """The incidents that are going on, by where they stand."""

    threats: int
    suspects: int
    # Unsure, or set aside by the AI.
    background: int
    cleared: int
    muted: int


class PreviewOut(BaseModel):
    """What the lanes come to now, and what they would if the settings were as asked."""

    now: LanesOut
    after: LanesOut


def _tuning(body: ThreatSettingsIn) -> Tuning:
    return Tuning(
        threat_from=body.threat_from,
        ai_may_clear=body.ai_may_clear,
        clear_from=body.clear_from,
        ai_confirms=body.ai_confirms,
        exposure=body.exposure,
        exposed_ports=tuple(sorted(set(body.exposed_ports))),
        notes=body.notes,
        important_drop=body.important_drop,
        low_raise=body.low_raise,
        ai_gives_verdicts=body.ai_gives_verdicts,
    )


def _shown(db: Db) -> ThreatSettingsOut:
    tuning = settings.load(db)
    row = db.get(ThreatSettings, 1)
    return ThreatSettingsOut(
        threat_from=tuning.threat_from,
        ai_may_clear=tuning.ai_may_clear,
        clear_from=tuning.clear_from,
        ai_confirms=tuning.ai_confirms,
        exposure=cast(Exposure, tuning.exposure),
        exposed_ports=list(tuning.exposed_ports),
        notes=tuning.notes,
        important_drop=tuning.important_drop,
        low_raise=tuning.low_raise,
        ai_gives_verdicts=tuning.ai_gives_verdicts,
        default_threat_from=settings.DEFAULT_THREAT_FROM,
        default_clear_from=settings.DEFAULT_CLEAR_FROM,
        default_important_drop=settings.DEFAULT_IMPORTANT_DROP,
        default_low_raise=settings.DEFAULT_LOW_RAISE,
        max_shift=settings.MAX_SHIFT,
        min_clear_from=settings.MIN_CLEAR_FROM,
        max_notes=settings.MAX_NOTES,
        max_ports=settings.MAX_PORTS,
        watching=settings.watching(db),
        updated_at=row.updated_at if row else None,
    )


def lanes(db: Db, tuning: Tuning) -> LanesOut:
    """How the incidents that are going on stand under those settings."""
    found = attention.tally(db, filters.load(db).confidence_floor, tuning)
    return LanesOut(
        threats=found.urgent,
        suspects=found.suspects,
        background=found.unsure + found.cleared,
        cleared=found.cleared,
        muted=found.muted,
    )


def _facts(was: Tuning, now: Tuning) -> dict[str, str | int | bool]:
    """What the audit log says of a change: each setting that changed, and what it was. What the
    owner wrote in their notes is not quoted."""
    facts: dict[str, str | int | bool] = {}
    for name in (
        "threat_from",
        "ai_may_clear",
        "clear_from",
        "ai_confirms",
        "exposure",
        "important_drop",
        "low_raise",
        "ai_gives_verdicts",
    ):
        before, after = getattr(was, name), getattr(now, name)
        if before != after:
            facts[name] = after
            facts[f"from_{name}"] = before
    if was.exposed_ports != now.exposed_ports:
        facts["exposed_ports"] = ",".join(str(port) for port in now.exposed_ports)
        facts["from_exposed_ports"] = ",".join(str(port) for port in was.exposed_ports)
    if was.notes != now.notes:
        facts["notes_changed"] = True
    return facts


@router.get("")
def get_threat_settings(db: Db) -> ThreatSettingsOut:
    """The settings as they are saved, or what they are until they are."""
    return _shown(db)


@router.put("")
def change_threat_settings(
    body: ThreatSettingsIn,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
) -> ThreatSettingsOut:
    """Sets them. Nothing is stored about an incident that depends on them, so the lanes follow at
    once."""
    was = settings.load(db)
    asked = _tuning(body)
    if settings.save(db, asked):
        record_audit(
            db,
            request,
            Action.THREATS_SETTINGS_CHANGED,
            Outcome.SUCCESS,
            user=auth.user,
            detail=_facts(was, asked),
        )
        db.commit()
    return _shown(db)


@router.post("/preview")
def preview_threat_settings(body: ThreatSettingsIn, db: Db) -> PreviewOut:
    """What the lanes would come to if the settings were as asked, without changing them."""
    asked = _tuning(body).confirming_when(body.ai_confirms and settings.watching(db))
    return PreviewOut(now=lanes(db, settings.load(db)), after=lanes(db, asked))
