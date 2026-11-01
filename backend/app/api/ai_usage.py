"""What AI has been used for and what it cost, the spending limits, and the record of each call.
For someone signed in. The costs are estimates from the catalog's price list, and say so."""

import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy import select

from app.ai import catalog, limits, usage
from app.api.deps import Db, SignedIn, record_audit, signed_in
from app.audit import Action, Outcome
from app.models import AiCall, utcnow

router = APIRouter(prefix="/ai", tags=["ai"], dependencies=[Depends(signed_in)])

Range = Literal["7d", "30d", "90d"]
Zone = Annotated[
    str,
    Query(
        max_length=64,
        description="The time zone days are counted in, such as America/Halifax.",
    ),
]
PAGE = 25
MAX_PAGE = 100
# What an incident is called in what a call was about (see app/ai/triage.py).
INCIDENT = re.compile(r"incident (\d+)")


class TotalsOut(BaseModel):
    calls: int
    failed: int
    input_tokens: int
    cached_tokens: int
    output_tokens: int
    # What the calls with a known price cost, and how many calls have none. Millionths of a
    # US dollar.
    cost_micros: int
    unpriced: int


class UseOut(BaseModel):
    """What one use of AI (reading incidents, chat) took on each of the days."""

    purpose: str
    calls: list[int]
    tokens: list[int]
    cost_micros: list[int]


class GroupOut(BaseModel):
    key: str
    label: str
    provider: str | None
    calls: int
    tokens: int
    cost_micros: int
    unpriced: int


class ConsumerOut(BaseModel):
    about: str
    purpose: str
    calls: int
    tokens: int
    cost_micros: int
    # The incident it was about, for a link to it.
    incident_id: int | None


class MonthOut(BaseModel):
    start: AwareDatetime
    end: AwareDatetime
    spent_micros: int
    unpriced: int
    projected_micros: int | None


class LimitOut(BaseModel):
    period: Literal["day", "month"]
    limit_micros: int | None
    spent_micros: int
    state: Literal["none", "ok", "warning", "reached"]


class SourceOut(BaseModel):
    provider: str
    url: str


class PricesOut(BaseModel):
    """Where the prices the costs are worked out from were read, and when."""

    as_of: str
    sources: list[SourceOut]


class UsageOut(BaseModel):
    range: Range
    start: AwareDatetime
    end: AwareDatetime
    # When each day begins, and what each use took on each day.
    days: list[AwareDatetime]
    uses: list[UseOut]
    totals: TotalsOut
    previous: TotalsOut
    by_provider: list[GroupOut]
    by_model: list[GroupOut]
    by_purpose: list[GroupOut]
    top: list[ConsumerOut]
    month: MonthOut
    limits: list[LimitOut]
    prices: PricesOut
    # Whether AI has ever been asked, so a page with nothing in this range can tell a new
    # install from a quiet week.
    ever: bool


class CallOut(BaseModel):
    id: int
    occurred_at: AwareDatetime
    purpose: str
    about: str | None
    provider: str
    provider_label: str
    model: str
    model_label: str
    level: str
    ok: bool
    input_tokens: int
    cached_tokens: int
    output_tokens: int
    cost_micros: int | None
    duration_ms: int
    truncated: bool
    error: str | None


class CallPage(BaseModel):
    total: int
    items: list[CallOut]


class CallDetail(CallOut):
    """A call with what the provider was sent and answered, exactly as it read them: with
    stand-ins for the addresses and names it was not shown."""

    prompt: str
    answer: str | None


class LimitsIn(BaseModel):
    """What may be spent, in US dollars, or None for no limit."""

    daily: Annotated[Decimal | None, Field(gt=0, le=limits.MAX_DOLLARS, decimal_places=2)] = None
    monthly: Annotated[Decimal | None, Field(gt=0, le=limits.MAX_DOLLARS, decimal_places=2)] = None


def _window(key: Range, name: str) -> usage.Span:
    zone = usage.zone_of(name)
    if zone is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "That isn't a time zone.")
    return usage.span(key, utcnow(), zone)


def _totals(found: usage.Totals) -> TotalsOut:
    return TotalsOut(
        calls=found.calls,
        failed=found.failed,
        input_tokens=found.input_tokens,
        cached_tokens=found.cached_tokens,
        output_tokens=found.output_tokens,
        cost_micros=found.cost_micros,
        unpriced=found.unpriced,
    )


def _provider_label(key: str) -> str:
    definition = catalog.provider(key)
    return definition.label if definition else key


def _model_label(provider: str, model: str) -> str:
    definition = catalog.provider(provider)
    known = definition.model(model) if definition else None
    return known.label if known else model


def _group(found: usage.Group, label: str) -> GroupOut:
    return GroupOut(
        key=found.key,
        label=label,
        provider=found.provider,
        calls=found.calls,
        tokens=found.tokens,
        cost_micros=found.cost_micros,
        unpriced=found.unpriced,
    )


def _uses(window: usage.Span, days: dict[date, list[usage.Day]]) -> list[UseOut]:
    purposes = sorted({entry.purpose for entries in days.values() for entry in entries})
    uses: list[UseOut] = []
    for purpose in purposes:
        calls: list[int] = []
        tokens: list[int] = []
        cost: list[int] = []
        for day in window.dates:
            entry = next((e for e in days.get(day, []) if e.purpose == purpose), None)
            calls.append(entry.calls if entry else 0)
            tokens.append(entry.tokens if entry else 0)
            cost.append(entry.cost_micros if entry else 0)
        uses.append(UseOut(purpose=purpose, calls=calls, tokens=tokens, cost_micros=cost))
    return uses


def _limit(found: limits.Limit) -> LimitOut:
    return LimitOut(
        period=found.period,
        limit_micros=found.limit_micros,
        spent_micros=found.spent_micros,
        state=found.state,
    )


def _consumer(found: usage.Consumer) -> ConsumerOut:
    match = INCIDENT.fullmatch(found.about)
    return ConsumerOut(
        about=found.about,
        purpose=found.purpose,
        calls=found.calls,
        tokens=found.tokens,
        cost_micros=found.cost_micros,
        incident_id=int(match.group(1)) if match else None,
    )


def _prices() -> PricesOut:
    return PricesOut(
        as_of=catalog.PRICES_AS_OF,
        sources=[
            SourceOut(provider=definition.label, url=definition.pricing_url)
            for definition in catalog.PROVIDERS
            if definition.pricing_url
        ],
    )


@router.get("/usage")
def get_usage(db: Db, range: Range = "30d", timezone: Zone = "UTC") -> UsageOut:
    """What AI took over the last 7, 30 or 90 days, and how the month is going."""
    now = utcnow()
    window = _window(range, timezone)
    out = UsageOut(
        range=range,
        start=window.start,
        end=window.end,
        days=list(window.days),
        uses=_uses(window, usage.by_day(db, window)),
        totals=_totals(usage.totals(db, window.start, window.end)),
        previous=_totals(usage.totals(db, window.previous_start, window.start)),
        by_provider=[_group(g, _provider_label(g.key)) for g in usage.by_provider(db, window)],
        by_model=[
            _group(g, _model_label(g.provider or "", g.key)) for g in usage.by_model(db, window)
        ],
        by_purpose=[_group(g, g.key) for g in usage.by_purpose(db, window)],
        top=[_consumer(c) for c in usage.top_consumers(db, window)],
        month=MonthOut.model_validate(usage.month(db, now), from_attributes=True),
        limits=[_limit(limit) for limit in limits.status(db, now)],
        prices=_prices(),
        ever=db.scalar(select(AiCall.id).limit(1)) is not None,
    )
    db.commit()
    return out


def _call_out(call: AiCall) -> CallOut:
    return CallOut(
        id=call.id,
        occurred_at=call.occurred_at,
        purpose=call.purpose,
        about=call.about,
        provider=call.provider,
        provider_label=_provider_label(call.provider),
        model=call.model,
        model_label=_model_label(call.provider, call.model),
        level=call.level,
        ok=call.ok,
        input_tokens=call.input_tokens,
        cached_tokens=call.cached_tokens,
        output_tokens=call.output_tokens,
        cost_micros=call.cost_micros,
        duration_ms=call.duration_ms,
        truncated=call.truncated,
        error=call.error,
    )


@router.get("/usage/calls")
def list_calls(
    db: Db,
    range: Range = "30d",
    timezone: Zone = "UTC",
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = PAGE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CallPage:
    """The calls in the range, newest first, without what was asked and answered."""
    found, total = usage.calls(db, _window(range, timezone), limit, offset)
    return CallPage(total=total, items=[_call_out(call) for call in found])


@router.get("/usage/calls/{call_id}")
def get_call(call_id: int, db: Db) -> CallDetail:
    """One call, with what the provider was sent and what it answered."""
    call = db.get(AiCall, call_id)
    if call is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There is no such call.")
    return CallDetail(**_call_out(call).model_dump(), prompt=call.prompt, answer=call.answer)


# A cell that starts with one of these is read by a spreadsheet as a formula.
_FORMULA = ("=", "+", "-", "@", "\t", "\r")


def _cell(value: object) -> str:
    text = "" if value is None else str(value)
    return f"'{text}" if text.startswith(_FORMULA) else text


def _dollars(micros: int | None) -> str:
    return "" if micros is None else f"{Decimal(micros) / limits.MICROS:.6f}"


COLUMNS = (
    "time (UTC)",
    "use",
    "about",
    "provider",
    "model",
    "shown",
    "succeeded",
    "input tokens",
    "cached tokens",
    "output tokens",
    "cost (US dollars, estimated)",
    "seconds",
    "error",
)


def _csv_row(call: AiCall) -> list[str]:
    return [
        call.occurred_at.isoformat(timespec="seconds"),
        _cell(call.purpose),
        _cell(call.about),
        _cell(call.provider),
        _cell(call.model),
        _cell(call.level),
        "yes" if call.ok else "no",
        str(call.input_tokens),
        str(call.cached_tokens),
        str(call.output_tokens),
        _dollars(call.cost_micros),
        f"{call.duration_ms / 1000:.1f}",
        _cell(call.error),
    ]


@router.get("/usage.csv")
def download_usage(db: Db, range: Range = "30d", timezone: Zone = "UTC") -> Response:
    """Every call in the range as a spreadsheet, without what was asked and answered."""
    window = _window(range, timezone)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(COLUMNS)
    for call in usage.export(db, window):
        writer.writerow(_csv_row(call))
    name = f"aresgate-ai-usage-{window.dates[-1].isoformat()}-{range}.csv"
    return Response(
        buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.put("/limits")
def set_limits(
    body: LimitsIn, auth: Annotated[SignedIn, Depends(signed_in)], request: Request, db: Db
) -> list[LimitOut]:
    """Sets what may be spent on AI that is paid for by the token, in a day and in a month."""
    now: datetime = utcnow()
    changed = limits.set_limits(db, body.daily, body.monthly, now)
    record_audit(
        db,
        request,
        Action.AI_LIMITS_CHANGED,
        Outcome.SUCCESS,
        user=auth.user,
        detail={
            "daily": "none" if body.daily is None else str(body.daily),
            "monthly": "none" if body.monthly is None else str(body.monthly),
        },
    )
    out = [_limit(limit) for limit in changed]
    db.commit()
    return out
