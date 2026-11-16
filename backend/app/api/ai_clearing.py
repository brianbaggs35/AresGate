"""What the owner lets the AI clear as a false positive: whether it does, how sure it must be, of
which kinds of reading and which programs' incidents, how serious, and how many a day. For someone
signed in."""

from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, Request
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app import baselines
from app.ai import clearing, clearing_settings
from app.ai.clearing_settings import Policy
from app.api.deps import Db, SignedIn, record_audit, signed_in
from app.audit import Action, Outcome
from app.incidents import rules
from app.integrations import registry
from app.models import AiClearingSettings, utcnow
from app.threats import settings as threat_settings

router = APIRouter(prefix="/ai/clearing", tags=["ai"], dependencies=[Depends(signed_in)])

Mode = Literal["off", "suggest", "automatic"]
Kind = Literal["noise", "probe", "unclear"]
Ceiling = Literal["low", "medium", "high"]
Aggressiveness = Literal["careful", "balanced", "thorough", "custom"]

# What each way of asking the AI to be careful comes to, in words.
PRESET_WORDS: dict[str, str] = {
    "careful": "Clears only what it is nearly certain of. You will see the fewest, and the surest.",
    "balanced": "Clears what it is quite sure of. A fair share of the background goes away.",
    "thorough": "Clears what it thinks is probably nothing. The most goes away, and you may "
    "want to look at what it cleared more often.",
}


class PresetOut(BaseModel):
    key: str
    minimum: int
    summary: str


class SourceOut(BaseModel):
    key: str
    name: str


class ClearingOut(BaseModel):
    mode: Mode
    aggressiveness: Aggressiveness
    minimum: int
    kinds: list[Kind]
    # The programs whose incidents it may clear; none named is any program.
    sources: list[str]
    ceiling: Ceiling
    daily_cap: int
    # What is on offer.
    presets: list[PresetOut]
    available_sources: list[SourceOut]
    min_minimum: int
    max_minimum: int
    max_cap: int
    # How many verdicts it gave in the last 24 hours, and why it is not clearing by itself now.
    cleared_today: int
    held: str | None
    updated_at: AwareDatetime | None


class ClearingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Mode
    minimum: int = Field(ge=clearing_settings.MIN_MINIMUM, le=clearing_settings.MAX_MINIMUM)
    kinds: list[Kind] = Field(max_length=len(clearing_settings.KINDS))
    sources: list[str] = Field(default_factory=list[str], max_length=32)
    ceiling: Ceiling
    daily_cap: int = Field(ge=0, le=clearing_settings.MAX_CAP)

    @field_validator("sources")
    @classmethod
    def _known(cls, value: list[str]) -> list[str]:
        unknown = sorted(set(value) - set(_programs()))
        if unknown:
            raise ValueError(f"Unknown program: {', '.join(unknown)}")
        return sorted(set(value))


class PreviewOut(BaseModel):
    """How many incidents the AI read in the last days, and how many it would have cleared."""

    days: int
    read: int
    would_clear: int


def _programs() -> dict[str, str]:
    """The programs whose incidents there are, by what they are called."""
    return {
        **{key: item.name for key, item in registry.INTEGRATIONS.items()},
        baselines.SOURCE: baselines.NAME,
    }


def _policy(body: ClearingIn) -> Policy:
    return Policy(
        mode=body.mode,
        minimum=body.minimum,
        kinds=tuple(kind for kind in clearing_settings.KINDS if kind in body.kinds),
        sources=tuple(body.sources),
        ceiling=body.ceiling,
        daily_cap=body.daily_cap,
    )


def _shown(db: Db) -> ClearingOut:
    now = utcnow()
    policy = clearing_settings.load(db)
    row = db.get(AiClearingSettings, 1)
    return ClearingOut(
        mode=cast(Mode, policy.mode),
        aggressiveness=cast(Aggressiveness, policy.aggressiveness),
        minimum=policy.minimum,
        kinds=cast(list[Kind], list(policy.kinds)),
        sources=list(policy.sources),
        ceiling=cast(Ceiling, policy.ceiling),
        daily_cap=policy.daily_cap,
        presets=[
            PresetOut(key=key, minimum=value, summary=PRESET_WORDS[key])
            for key, value in clearing_settings.PRESETS.items()
        ],
        available_sources=[
            SourceOut(key=key, name=rules.name_of(key)) for key in sorted(_programs())
        ],
        min_minimum=clearing_settings.MIN_MINIMUM,
        max_minimum=clearing_settings.MAX_MINIMUM,
        max_cap=clearing_settings.MAX_CAP,
        cleared_today=clearing_settings.cleared_lately(db, now),
        held=clearing_settings.held(db, policy, now),
        updated_at=row.updated_at if row else None,
    )


def _facts(was: Policy, now: Policy) -> dict[str, str | int | bool]:
    """What the audit log says of a change: each setting that changed, and what it was."""
    facts: dict[str, str | int | bool] = {}
    for name in ("mode", "minimum", "ceiling", "daily_cap"):
        before, after = getattr(was, name), getattr(now, name)
        if before != after:
            facts[name] = after
            facts[f"from_{name}"] = before
    for name in ("kinds", "sources"):
        before, after = getattr(was, name), getattr(now, name)
        if before != after:
            facts[name] = ",".join(after) or "any"
            facts[f"from_{name}"] = ",".join(before) or "any"
    return facts


@router.get("")
def get_clearing(db: Db) -> ClearingOut:
    """The settings as they are saved, or what they are until they are."""
    return _shown(db)


@router.put("")
def change_clearing(
    body: ClearingIn,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
) -> ClearingOut:
    """Sets them."""
    was = clearing_settings.load(db)
    asked = _policy(body)
    if clearing_settings.save(db, asked, utcnow()):
        record_audit(
            db,
            request,
            Action.AI_CLEARING_CHANGED,
            Outcome.SUCCESS,
            user=auth.user,
            detail=_facts(was, asked),
        )
        db.commit()
    return _shown(db)


@router.post("/preview")
def preview_clearing(body: ClearingIn, db: Db) -> PreviewOut:
    """How many of the incidents the AI read in the last 7 days the settings would have cleared,
    without changing them."""
    found = clearing.preview(db, _policy(body), threat_settings.load(db), utcnow())
    return PreviewOut(days=clearing.PREVIEW_DAYS, read=found.read, would_clear=found.would_clear)
