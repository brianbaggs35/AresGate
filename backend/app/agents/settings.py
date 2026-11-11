"""How the agents use AI: which provider they ask, with which model, and what they may spend.

An agent is a standing instruction that may run every hour, so how it asks the AI is worth a
choice of its own: a cheaper model than the one that answers a question, or a provider of its own,
or none. ``shared`` asks whatever Settings > AI chose (while AI is on there), ``own`` asks a
provider that is set up on that page, with a model of the agents' own if one is given, and
``off`` asks nobody: the agents still look and keep what they saw. Their spending has limits of
its own, which hold alongside the ones on the AI usage page.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Final

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.ai import catalog, limits, service
from app.integrations.registry import SettingsError
from app.models import AI_SOURCES, AgentSettings, AiProvider

# What the agents' requests are recorded as in ``ai_calls``.
PURPOSE: Final = "agent"


@dataclass(frozen=True)
class Pick:
    """Which provider the agents ask now, and which model of it (None for the one it was set up
    with), or why they ask none."""

    provider: str | None
    model: str | None
    reason: str | None


def get(db: Session, now: datetime) -> AgentSettings:
    """The agents' settings, made if this is the first look."""
    found = db.get(AgentSettings, 1)
    if found is None:
        # Two requests that look for the first time at once make it only once.
        db.execute(
            insert(AgentSettings)
            .values(id=1, ai_source="shared", updated_at=now)
            .on_conflict_do_nothing()
        )
        found = db.get_one(AgentSettings, 1)
    return found


def pick(db: Session, now: datetime) -> Pick:
    """Which provider the agents ask now, and why none if there is none."""
    chosen = get(db, now)
    if chosen.ai_source == "off":
        return Pick(
            None, None, "AI is turned off for the agents. Turn it on under Settings > Agents."
        )
    if chosen.ai_source == "own":
        if chosen.provider is None:
            return Pick(
                None,
                None,
                "No AI provider is chosen for the agents. Choose one under Settings > Agents.",
            )
        return Pick(chosen.provider, chosen.model, None)
    shared = service.usage(db, now)
    if not shared.enabled:
        return Pick(None, None, "AI is turned off. Turn it on under Settings > AI to use it.")
    return Pick(shared.provider, None, None)


def status(db: Session, now: datetime) -> tuple[limits.Limit, limits.Limit]:
    """The agents' day limit and month limit, with what the agents alone have spent against each."""
    chosen = get(db, now)
    return (
        limits.Limit(
            "day",
            chosen.daily_limit_micros,
            limits.spent(db, now - timedelta(hours=24), PURPOSE),
        ),
        limits.Limit(
            "month", chosen.monthly_limit_micros, limits.spent(db, limits.month_start(now), PURPOSE)
        ),
    )


def reached(db: Session, now: datetime) -> str | None:
    """Why the agents may not ask a provider that charges, if their own limit is used up."""
    for limit in status(db, now):
        words = limits.words_for(limit, "agents'", "under Settings > Agents")
        if words:
            return words
    return None


def _provider_problems(db: Session, provider: str, model: str | None) -> dict[str, str]:
    """What is wrong with asking ``provider`` with ``model`` (None for the one it was set up
    with), by the name of the setting."""
    row = db.get(AiProvider, provider)
    definition = catalog.provider(provider)
    if row is None or definition is None:
        return {"provider": "Set that provider up under Settings > AI first."}
    if not (model or row.model):
        return {"model": "Choose a model for it first."}
    if model and definition.fixed_models and definition.model(model) is None:
        return {"model": "Choose one of the models the provider offers."}
    return {}


def save(
    db: Session,
    *,
    source: str,
    provider: str | None,
    model: str | None,
    daily: Decimal | None,
    monthly: Decimal | None,
    now: datetime,
) -> AgentSettings:
    """Keeps which AI the agents ask and what they may spend, or raises ``SettingsError`` saying
    what is wrong. The caller commits."""
    problems: dict[str, str] = {}
    if source not in AI_SOURCES:
        problems["ai_source"] = "Choose shared, own or off."
    chosen_model = (model or "").strip() or None
    if source == "own":
        if provider is None:
            problems["provider"] = "Choose which provider the agents ask."
        else:
            problems |= _provider_problems(db, provider, chosen_model)
    if problems:
        raise SettingsError(problems)
    chosen = get(db, now)
    chosen.ai_source = source
    chosen.provider = provider if source == "own" else None
    chosen.model = chosen_model if source == "own" else None
    chosen.daily_limit_micros = limits.to_micros(daily)
    chosen.monthly_limit_micros = limits.to_micros(monthly)
    chosen.updated_at = now
    db.flush()
    return chosen
