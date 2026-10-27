"""AI: which providers are set up, setting one up, testing it, finding the models an Ollama has,
and whether AresGate uses AI at all. API keys only go in: no route here returns one, and a
failed request doesn't quote what was sent."""

from typing import Annotated, Literal, cast

import anyio.from_thread
from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response, status
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy.orm import Session

from app.ai import catalog, service, wire
from app.ai.catalog import Kind, ProviderDef
from app.ai.service import Submission
from app.api.deps import Db, SettingsDep, SignedIn, record_audit, signed_in
from app.api.integrations import RecorderDep
from app.audit import Action, Outcome
from app.integrations.netguard import AddressPolicy
from app.integrations.probes import Verdict
from app.integrations.registry import SettingsError
from app.integrations.service import Status
from app.models import AiProvider, utcnow
from app.security.credential_store import NAME_PATTERN

# Everything here is for someone who is signed in.
router = APIRouter(prefix="/ai", tags=["ai"], dependencies=[Depends(signed_in)])

Key = Annotated[str, Path(pattern=NAME_PATTERN, description="A provider, such as anthropic.")]


def policy_for(definition: ProviderDef, request: Request) -> AddressPolicy:
    """Which addresses a provider may be at: the home network for one on the owner's computer,
    the internet for the others. The app sets them when it is made."""
    state = request.app.state
    return cast(
        "AddressPolicy", state.address_policy if definition.kind is Kind.LOCAL else state.ai_policy
    )


def origins(request: Request) -> dict[str, str]:
    """Where hosted providers are when it isn't where they really are: only ever in the test
    server, which points them at stand-ins on its own machine."""
    return cast("dict[str, str]", request.app.state.ai_origins)


class PriceOut(BaseModel):
    """What a model costs, in US dollars per million tokens."""

    input: float
    output: float
    cached_input: float | None
    # Some models cost more for a prompt longer than this many tokens, and what that costs.
    long_over: int | None
    long_input: float | None
    long_output: float | None


class ModelOut(BaseModel):
    id: str
    label: str
    note: str
    price: PriceOut


class FoundModelOut(BaseModel):
    """A model an Ollama said it has."""

    name: str
    size: int | None
    family: str | None
    parameters: str | None
    quantization: str | None


class ProviderOut(BaseModel):
    key: str
    label: str
    summary: str
    kind: Literal["hosted", "local", "cloud"]
    needs_key: bool
    takes_url: bool
    key_url: str | None
    pricing_url: str | None
    models_url: str
    # The models it offers: none for one whose models are whatever it has.
    models: list[ModelOut]
    default_model: str | None
    # What is set up, if anything is. Never the key, only whether one is kept.
    configured: bool
    base_url: str | None
    model: str | None
    key_saved: bool
    status: Status
    last_attempt_at: AwareDatetime | None
    last_success_at: AwareDatetime | None
    last_error: str | None
    # The models it said it has when they were last asked for.
    found: list[FoundModelOut]
    found_at: AwareDatetime | None


class AiOut(BaseModel):
    enabled: bool
    provider: str | None
    # When the prices were read from the providers' pages.
    priced_as_of: str
    providers: list[ProviderOut]


class ProviderIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = Field(max_length=128)
    base_url: str | None = Field(default=None, max_length=255)
    # Left out or empty, the key that is kept stays.
    api_key: SecretStr | None = Field(default=None, max_length=1024)


class UseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    provider: str | None = Field(default=None, pattern=NAME_PATTERN)


class CheckOut(BaseModel):
    """How a test or a look for models went, and the provider as it is now."""

    ok: bool
    message: str
    provider: ProviderOut


def _definition(key: str) -> ProviderDef:
    definition = catalog.provider(key)
    if definition is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There is no such AI provider.")
    return definition


def _invalid(*location: str, message: str) -> dict[str, object]:
    return {"type": "value_error", "loc": ["body", *location], "msg": message}


def _price_out(model: catalog.ModelDef) -> PriceOut:
    price = model.price
    long = price.long
    return PriceOut(
        input=float(price.input),
        output=float(price.output),
        cached_input=float(price.cached_input) if price.cached_input is not None else None,
        long_over=price.long_over if long is not None else None,
        long_input=float(long.input) if long is not None else None,
        long_output=float(long.output) if long is not None else None,
    )


def _provider_out(db: Session, definition: ProviderDef, row: AiProvider | None) -> ProviderOut:
    return ProviderOut(
        key=definition.key,
        label=definition.label,
        summary=definition.summary,
        kind=definition.kind.value,
        needs_key=definition.needs_key,
        takes_url=definition.kind is Kind.LOCAL,
        key_url=definition.key_url,
        pricing_url=definition.pricing_url,
        models_url=definition.models_url,
        models=[
            ModelOut(id=model.id, label=model.label, note=model.note, price=_price_out(model))
            for model in definition.models
        ],
        default_model=definition.default_model,
        configured=row is not None,
        base_url=row.base_url if row else None,
        model=row.model if row else None,
        key_saved=service.key_saved(db, definition),
        status=service.status_of(row),
        last_attempt_at=row.last_attempt_at if row else None,
        last_success_at=row.last_success_at if row else None,
        last_error=row.last_error if row else None,
        found=[FoundModelOut.model_validate(found) for found in (row.models_found if row else [])],
        found_at=row.models_found_at if row else None,
    )


def _ai_out(db: Session) -> AiOut:
    now = utcnow()
    chosen = service.usage(db, now)
    rows = service.configured(db)
    return AiOut(
        enabled=chosen.enabled,
        provider=chosen.provider,
        priced_as_of=catalog.PRICES_AS_OF,
        providers=[
            _provider_out(db, definition, rows.get(definition.key))
            for definition in catalog.PROVIDERS
        ],
    )


@router.get("")
def get_ai(db: Db) -> AiOut:
    """Every provider AresGate can ask, with what it costs and how it is set up, and whether AI
    is used."""
    out = _ai_out(db)
    db.commit()
    return out


@router.put("/providers/{key}")
def set_up_provider(
    key: Key,
    body: ProviderIn,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
    settings: SettingsDep,
) -> ProviderOut:
    """Saves how to reach a provider, replacing what was saved, and keeps its key. It isn't
    tested yet: ``POST /providers/{key}/test`` does that."""
    definition = _definition(key)
    submission = Submission(
        model=body.model,
        base_url=body.base_url,
        api_key=body.api_key.get_secret_value() if body.api_key else None,
    )
    try:
        row = service.save(
            db, settings, policy_for(definition, request), definition, submission, utcnow()
        )
    except SettingsError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            [_invalid(name, message=text) for name, text in error.problems.items()],
        ) from error
    record_audit(
        db,
        request,
        Action.AI_PROVIDER_SAVED,
        Outcome.SUCCESS,
        user=auth.user,
        detail={"provider": key},
    )
    db.commit()
    return _provider_out(db, definition, row)


@router.delete("/providers/{key}", status_code=status.HTTP_204_NO_CONTENT)
def remove_provider(
    key: Key, auth: Annotated[SignedIn, Depends(signed_in)], request: Request, db: Db
) -> Response:
    """Forgets a provider and its key, and stops using AI if it was the one asked."""
    if not service.remove(db, _definition(key), utcnow()):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "It isn't set up.")
    record_audit(
        db,
        request,
        Action.AI_PROVIDER_REMOVED,
        Outcome.SUCCESS,
        user=auth.user,
        detail={"provider": key},
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _saved(db: Session, definition: ProviderDef) -> AiProvider:
    row = service.row_for(db, definition)
    if row is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Set it up first.")
    return row


@router.post("/providers/{key}/test")
def test_provider(
    key: Key,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
    settings: SettingsDep,
    recorder: RecorderDep,
) -> CheckOut:
    """Tests a provider with the least that proves it works, and keeps how it went."""
    definition = _definition(key)
    row = _saved(db, definition)
    policy = policy_for(definition, request)
    try:
        target = service.load_target(db, settings, definition, row, origins(request))
        verdict = anyio.from_thread.run(
            service.check, target, recorder, policy, definition, row.model
        )
    except service.Incomplete as incomplete:
        verdict = Verdict(False, str(incomplete))
    service.record_attempt(row, verdict, utcnow())
    record_audit(
        db,
        request,
        Action.AI_PROVIDER_TESTED,
        Outcome.SUCCESS if verdict.ok else Outcome.FAILURE,
        user=auth.user,
        detail={"provider": key},
    )
    db.commit()
    return CheckOut(
        ok=verdict.ok, message=verdict.message, provider=_provider_out(db, definition, row)
    )


@router.post("/providers/{key}/models")
def fetch_models(
    key: Key,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
    settings: SettingsDep,
    recorder: RecorderDep,
) -> CheckOut:
    """Asks an Ollama which models it has, and keeps the answer."""
    definition = _definition(key)
    if definition.fixed_models:
        raise HTTPException(status.HTTP_409_CONFLICT, "It has a list of models of its own.")
    row = _saved(db, definition)
    policy = policy_for(definition, request)
    failure: str | None = None
    found: list[wire.FoundModel] = []
    try:
        target = service.load_target(db, settings, definition, row, origins(request))
        answer = anyio.from_thread.run(service.find_models, target, recorder, policy, definition)
        if isinstance(answer, str):
            failure = answer
        else:
            found = answer
    except service.Incomplete as incomplete:
        failure = str(incomplete)
    now = utcnow()
    if failure is None:
        service.record_models(row, found, now)
        message = f"It has {len(found)} model{'' if len(found) == 1 else 's'}."
    else:
        service.record_attempt(row, Verdict(False, failure), now)
        message = failure
    record_audit(
        db,
        request,
        Action.AI_MODELS_FETCHED,
        Outcome.SUCCESS if failure is None else Outcome.FAILURE,
        user=auth.user,
        detail={"provider": key},
    )
    db.commit()
    return CheckOut(
        ok=failure is None, message=message, provider=_provider_out(db, definition, row)
    )


@router.put("/use")
def use_ai(
    body: UseIn, auth: Annotated[SignedIn, Depends(signed_in)], request: Request, db: Db
) -> AiOut:
    """Turns AI on or off, and says which provider it asks."""
    try:
        service.choose(db, enabled=body.enabled, provider=body.provider, now=utcnow())
    except SettingsError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            [_invalid(name, message=text) for name, text in error.problems.items()],
        ) from error
    record_audit(
        db,
        request,
        Action.AI_CHOSEN,
        Outcome.SUCCESS,
        user=auth.user,
        detail={"enabled": body.enabled, "provider": body.provider or "none"},
    )
    out = _ai_out(db)
    db.commit()
    return out
