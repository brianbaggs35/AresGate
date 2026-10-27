"""Setting up AI providers, testing them and choosing whether AresGate uses AI.

A provider's settings are a row in ``ai_providers`` and its API key is in the credential store.
Saving checks everything first and changes nothing unless all of it is acceptable, so a typing
mistake never leaves half a provider behind. Whether AresGate uses AI at all, and which provider
it asks, is the one row of ``ai_settings``.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.ai import wire
from app.ai.catalog import Kind, ProviderDef, Wire
from app.config import Settings
from app.integrations import netguard
from app.integrations.client import ApiClient, CallFailed, Recorder, Target
from app.integrations.netguard import AddressPolicy, Origin, Refused
from app.integrations.probes import Verdict
from app.integrations.registry import SettingsError
from app.integrations.service import Status
from app.models import AiProvider, AiSettings
from app.security import credential_store
from app.security.credential_store import Kind as CredentialKind
from app.security.vault import VaultError

# The one secret a provider takes.
API_KEY = "api_key"
MAX_KEY = 512
# What a test asks for: the least that proves the key, the model and the address work.
TEST_SYSTEM = "Answer with one word."
TEST_PROMPT = "Say OK."


@dataclass(frozen=True)
class Submission:
    """What was filled in for one provider. A key left out keeps the one already kept."""

    model: str
    base_url: str | None = None
    api_key: str | None = None
    # ``free`` or ``paid``, for a provider with plans. Left out, the one that is kept stays.
    plan: str | None = None


class Incomplete(Exception):
    """A provider that can't be used as it is, such as one whose key was removed."""


def row_for(db: Session, definition: ProviderDef) -> AiProvider | None:
    return db.get(AiProvider, definition.key)


def key_saved(db: Session, definition: ProviderDef) -> bool:
    """Whether the provider's API key is kept. Never the key itself."""
    return any(
        entry.kind == CredentialKind.AI_PROVIDER
        and entry.name == definition.key
        and entry.field == API_KEY
        for entry in credential_store.entries(db)
    )


def status_of(row: AiProvider | None) -> Status:
    if row is None:
        return Status.NOT_CONNECTED
    if row.last_attempt_at is None:
        return Status.UNTESTED
    return Status.PROBLEM if row.last_error else Status.CONNECTED


def usage(db: Session, now: datetime) -> AiSettings:
    """Whether AI is used and which provider is asked, made if this is the first look."""
    found = db.get(AiSettings, 1)
    if found is None:
        found = AiSettings(id=1, enabled=False, provider=None, updated_at=now)
        db.add(found)
        db.flush()
    return found


def _model(definition: ProviderDef, text: str, problems: dict[str, str]) -> str:
    """The model to keep. A provider with a list takes one of its models, and the others take
    the name of one, or none yet, since which exist is found by asking."""
    name = text.strip()
    if definition.fixed_models:
        if definition.model(name) is None:
            problems["model"] = "Choose one of the models in the list."
        return name
    if name and not wire.MODEL_NAME.fullmatch(name):
        problems["model"] = "That isn't a model name. It is letters, digits and . _ : / - only."
    return name


def _address(
    definition: ProviderDef, text: str | None, policy: AddressPolicy, problems: dict[str, str]
) -> str | None:
    """Where a provider on the owner's computer is, or None for one that is always in one place."""
    if definition.kind is not Kind.LOCAL:
        return None
    try:
        origin = netguard.parse_origin(text or "", allow_http=True)
        netguard.check_reachable(policy, origin)
    except Refused as refusal:
        problems["base_url"] = str(refusal)
        return None
    return origin.url


PLANS = ("free", "paid")


def _plan(definition: ProviderDef, text: str | None, problems: dict[str, str]) -> str | None:
    """The plan to keep, or none to keep the one that is kept."""
    if text is None:
        return None
    if not definition.has_plans:
        problems["plan"] = f"{definition.label} has no plans."
    elif text not in PLANS:
        problems["plan"] = "Choose free or paid."
    return text


def _key(
    db: Session, definition: ProviderDef, text: str | None, problems: dict[str, str]
) -> str | None:
    """The key to keep: what was typed, or none to keep the one that is kept."""
    value = (text or "").strip()
    if not definition.needs_key:
        if value:
            problems[API_KEY] = f"{definition.label} takes no key."
        return None
    if not value:
        if not key_saved(db, definition):
            problems[API_KEY] = "Enter the API key."
        return None
    if len(value) > MAX_KEY or any(character.isspace() for character in value):
        problems[API_KEY] = "That isn't an API key: a key has no spaces and is not very long."
        return None
    return value


def save(
    db: Session,
    settings: Settings,
    policy: AddressPolicy,
    definition: ProviderDef,
    submission: Submission,
    now: datetime,
) -> AiProvider:
    """Keeps a provider's settings and key, or raises ``SettingsError`` and keeps nothing. The
    caller commits."""
    problems: dict[str, str] = {}
    model = _model(
        definition, submission.model.strip() or (definition.default_model or ""), problems
    )
    base_url = _address(definition, submission.base_url, policy, problems)
    new_key = _key(db, definition, submission.api_key, problems)
    plan = _plan(definition, submission.plan, problems)
    if problems:
        raise SettingsError(problems)
    row = row_for(db, definition)
    if row is None:
        row = AiProvider(provider=definition.key, created_at=now, models_found=[])
        db.add(row)
    row.base_url = base_url
    row.model = model
    # Free until the owner says otherwise: that is what an account starts as.
    if definition.has_plans:
        row.plan = plan or row.plan or "free"
    # What the last attempt found was about the old settings.
    row.last_attempt_at = None
    row.last_error = None
    row.updated_at = now
    if new_key is not None:
        credential_store.store(
            db, settings, CredentialKind.AI_PROVIDER, definition.key, API_KEY, new_key, now
        )
    return row


def remove(db: Session, definition: ProviderDef, now: datetime) -> bool:
    """Forgets a provider's settings and key, and stops using AI if it was the one asked. False
    if there was nothing to forget. The caller commits."""
    row = row_for(db, definition)
    chosen = usage(db, now)
    if chosen.provider == definition.key:
        chosen.provider = None
        chosen.enabled = False
        chosen.updated_at = now
    found = row is not None
    if row is not None:
        db.delete(row)
        db.flush()
    found |= credential_store.remove(db, CredentialKind.AI_PROVIDER, definition.key, API_KEY)
    return found


def choose(db: Session, *, enabled: bool, provider: str | None, now: datetime) -> AiSettings:
    """Whether AI is used and which provider is asked, or raises ``SettingsError``. The caller
    commits."""
    problems: dict[str, str] = {}
    row = db.get(AiProvider, provider) if provider is not None else None
    if provider is not None and row is None:
        problems["provider"] = "Set that provider up first."
    elif row is not None and enabled and not row.model:
        problems["provider"] = "Choose a model for it first."
    elif enabled and provider is None:
        problems["provider"] = "Choose which provider to ask."
    if problems:
        raise SettingsError(problems)
    chosen = usage(db, now)
    chosen.enabled = enabled
    chosen.provider = provider
    chosen.updated_at = now
    return chosen


def origin_of(definition: ProviderDef, row: AiProvider, overrides: Mapping[str, str]) -> Origin:
    """Where a provider is. A hosted provider is at one address, except in the test server,
    which points it at a stand-in on the same machine."""
    if definition.kind is Kind.LOCAL:
        return netguard.parse_origin(row.base_url or "", allow_http=True)
    override = overrides.get(definition.key)
    return netguard.parse_origin(override or definition.origin or "", allow_http=bool(override))


def load_target(
    db: Session,
    settings: Settings,
    definition: ProviderDef,
    row: AiProvider,
    overrides: Mapping[str, str],
) -> Target:
    """A saved provider with its key opened, for the code that makes requests to it. Raises
    ``Incomplete`` if its key is gone or can't be opened."""
    secrets: dict[str, str] = {}
    if definition.needs_key:
        try:
            key = credential_store.reveal(
                db, settings, CredentialKind.AI_PROVIDER, definition.key, API_KEY
            )
        except VaultError:
            key = None
        if key is None:
            raise Incomplete("The API key is missing or can't be opened. Enter it again.")
        secrets[API_KEY] = key
    return Target(
        integration="ai",
        connection=definition.key,
        origin=origin_of(definition, row, overrides),
        tls_mode="system",
        tls_ca_pem=None,
        tls_fingerprint=None,
        options={},
        secrets=secrets,
    )


def _plan_note(
    definition: ProviderDef, model: str, plan: str | None, failure: CallFailed | wire.AiFailed
) -> str:
    """Why a model was not answered: for a 402 from a provider with plans, what the plan the
    owner said they have means for the model, and else what the failure says."""
    if definition.has_plans and getattr(failure, "status", None) == 402:
        if plan == "paid":
            return (
                "Ollama Cloud says payment is required (HTTP 402) for it, though the plan is "
                "set to paid. Check the plan and the credits at ollama.com/settings/usage."
            )
        if model not in definition.free_models:
            return (
                f"{model} isn't one of the models free usage credits cover (HTTP 402), so it "
                f"needs a paid plan. Choose one of {', '.join(definition.free_models)}, or set "
                "the plan to paid if it is."
            )
    return str(failure)


async def check(
    target: Target,
    recorder: Recorder,
    policy: AddressPolicy,
    definition: ProviderDef,
    model: str,
    plan: str | None = None,
) -> Verdict:
    """Tests a provider with the least that proves it works: an Ollama is asked what it has and
    then for one token, the others for one token."""
    key = target.secrets.get(API_KEY)
    try:
        async with ApiClient(target, recorder, policy) as client:
            if definition.wire is Wire.OLLAMA:
                found = await wire.list_models(client, definition, key)
                count = f"{len(found)} model{'' if len(found) == 1 else 's'}"
                if not model:
                    return Verdict(True, f"Reached it. It has {count}: choose one to use.")
                try:
                    await wire.complete(
                        client,
                        definition,
                        model,
                        key,
                        system=TEST_SYSTEM,
                        prompt=TEST_PROMPT,
                        max_tokens=1,
                    )
                except (CallFailed, wire.AiFailed) as failure:
                    # Listing the models worked, so it is this model that was not answered.
                    return Verdict(
                        False,
                        f"Reached it ({count}), but {model} didn't answer. "
                        f"{_plan_note(definition, model, plan, failure)}",
                    )
                return Verdict(True, f"Reached it ({count}), and {model} answered.")
            answer = await wire.complete(
                client,
                definition,
                model,
                key,
                system=TEST_SYSTEM,
                prompt=TEST_PROMPT,
                max_tokens=1,
            )
    except (CallFailed, wire.AiFailed) as failure:
        return Verdict(False, str(failure))
    return Verdict(
        True,
        f"{model} answered. It counted {answer.input_tokens} tokens in and "
        f"{answer.output_tokens} out.",
    )


async def find_models(
    target: Target, recorder: Recorder, policy: AddressPolicy, definition: ProviderDef
) -> list[wire.FoundModel] | str:
    """The models an Ollama has, or why they could not be had."""
    try:
        async with ApiClient(target, recorder, policy) as client:
            return await wire.list_models(client, definition, target.secrets.get(API_KEY))
    except (CallFailed, wire.AiFailed) as failure:
        return str(failure)


def record_attempt(row: AiProvider, verdict: Verdict, now: datetime) -> None:
    """Keeps how an attempt went. A success clears the last failure's reason."""
    row.last_attempt_at = now
    if verdict.ok:
        row.last_success_at = now
        row.last_error = None
    else:
        row.last_error = audit.clean(verdict.message, 500)


def record_models(row: AiProvider, found: list[wire.FoundModel], now: datetime) -> None:
    """Keeps the models an Ollama said it has, and counts the asking as an attempt that worked."""
    row.models_found = [
        {
            "name": model.name,
            "size": model.size,
            "family": model.family,
            "parameters": model.parameters,
            "quantization": model.quantization,
        }
        for model in found
    ]
    row.models_found_at = now
    record_attempt(row, Verdict(True, ""), now)


def configured(db: Session) -> dict[str, AiProvider]:
    """The providers that are set up, by key."""
    return {row.provider: row for row in db.scalars(select(AiProvider))}
