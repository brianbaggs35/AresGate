"""Retention settings: how long data is kept and how big the database may get, with how much it
uses now. For someone signed in."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app import quota, retention_policy
from app.api.deps import Db, SettingsDep, SignedIn, record_audit, signed_in
from app.audit import Action, Outcome
from app.models import Event
from app.partitions import EVENTS, METRIC_SAMPLES
from app.retention_policy import Policy

router = APIRouter(
    prefix="/retention-settings", tags=["retention"], dependencies=[Depends(signed_in)]
)


class PeriodsOut(BaseModel):
    """How long each kind of data is kept while retention isn't managed on the page: what each
    one's own setting says."""

    events: int
    metrics: int
    api_log: int
    ai_log: int
    alert_log: int
    audit: int


class UsageOut(BaseModel):
    """How much the database holds, and how much of that is events and measurements."""

    database_bytes: int
    events_bytes: int
    metrics_bytes: int
    oldest_event_at: AwareDatetime | None
    # The quota in bytes while one is in force, and whether the database is over it.
    quota_bytes: int | None
    over_quota: bool


class RetentionSettingsOut(BaseModel):
    managed: bool
    keep_forever: bool
    days: int
    quota_gb: int | None
    default_days: int
    min_days: int
    max_days: int
    min_quota_gb: int
    max_quota_gb: int
    built_in: PeriodsOut
    usage: UsageOut
    updated_at: AwareDatetime | None


class RetentionSettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    managed: bool
    keep_forever: bool
    days: int = Field(ge=retention_policy.MIN_DAYS, le=retention_policy.MAX_DAYS)
    quota_gb: int | None = Field(
        default=None, ge=retention_policy.MIN_QUOTA_GB, le=retention_policy.MAX_QUOTA_GB
    )


def _usage(db: Db, policy: Policy) -> UsageOut:
    size = quota.database_bytes(db)
    limit = policy.quota_bytes
    return UsageOut(
        database_bytes=size,
        events_bytes=quota.table_bytes(db, EVENTS),
        metrics_bytes=quota.table_bytes(db, METRIC_SAMPLES),
        oldest_event_at=db.scalar(select(func.min(Event.occurred_at))),
        quota_bytes=limit,
        over_quota=limit is not None and size > limit,
    )


def _shown(db: Db, settings: SettingsDep) -> RetentionSettingsOut:
    policy = retention_policy.load(db)
    return RetentionSettingsOut(
        managed=policy.managed,
        keep_forever=policy.keep_forever,
        days=policy.days,
        quota_gb=policy.quota_gb,
        default_days=retention_policy.DEFAULT_DAYS,
        min_days=retention_policy.MIN_DAYS,
        max_days=retention_policy.MAX_DAYS,
        min_quota_gb=retention_policy.MIN_QUOTA_GB,
        max_quota_gb=retention_policy.MAX_QUOTA_GB,
        built_in=PeriodsOut(
            events=settings.event_retention_days,
            metrics=settings.metric_retention_days,
            api_log=settings.api_log_retention_days,
            ai_log=settings.ai_log_retention_days,
            alert_log=settings.alert_log_retention_days,
            audit=settings.audit_retention_days,
        ),
        usage=_usage(db, policy),
        updated_at=retention_policy.updated_at(db),
    )


def _facts(was: Policy, now: Policy) -> dict[str, str | int | bool]:
    """What the audit log says of a change: each choice that changed, and what it was."""
    facts: dict[str, str | int | bool] = {}
    for name in ("managed", "keep_forever", "days", "quota_gb"):
        before, after = getattr(was, name), getattr(now, name)
        if before != after:
            facts[name] = "none" if after is None else after
            facts[f"from_{name}"] = "none" if before is None else before
    return facts


@router.get("")
def get_retention_settings(db: Db, settings: SettingsDep) -> RetentionSettingsOut:
    """The choices as they are saved, or what they are until they are, with how much the database
    holds now."""
    return _shown(db, settings)


@router.put("")
def change_retention_settings(
    body: RetentionSettingsIn,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
    settings: SettingsDep,
) -> RetentionSettingsOut:
    """Sets them. What is past its period, and what the quota asks to make room for, goes at the
    next clean-up: every six hours for age, every fifteen minutes for the quota."""
    was = retention_policy.load(db)
    asked = Policy(body.managed, body.keep_forever, body.days, body.quota_gb)
    if retention_policy.save(db, asked):
        record_audit(
            db,
            request,
            Action.RETENTION_SETTINGS_CHANGED,
            Outcome.SUCCESS,
            user=auth.user,
            detail=_facts(was, asked),
        )
        db.commit()
    return _shown(db, settings)
