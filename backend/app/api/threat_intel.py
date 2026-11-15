"""Searches threat intelligence by hand: an internet address, a domain or a web address, and what a
service (VirusTotal, AlienVault OTX or GreyNoise: VirusTotal unless the search says another)
reported of it. A search shares its limits with the background lookups, so the two together never
ask a service more often than its free API allows. Every answer is kept. A subject whose answer is
still fresh is shown from what was kept, and the service isn't asked about it again, unless the
search asks for that. While a limit the service set itself holds, nothing is sent: a search says
when it may go, or shows the answer kept if there is one. Everything kept can be looked through
too, which asks no service anything. The owner can rule a subject safe or suspicious whatever the
services made of it, to correct a false positive or a false negative: a ruling is shown in place
of a service's judgement, which is kept beside it as what the service said, and it is the same
ruling whichever service is asked."""

import math
from datetime import UTC, datetime
from typing import Annotated, Literal, cast

import anyio.from_thread
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app import audit
from app.api.deps import Db, SettingsDep, SignedIn, record_audit, signed_in
from app.api.integrations import api_log_recorder
from app.audit import Action, Outcome
from app.integrations import netguard, service
from app.integrations.client import Recorder, Target
from app.integrations.netguard import AddressPolicy
from app.intel import (
    budget,
    candidates,
    greynoise,
    known,
    otx,
    overrides,
    store,
    subjects,
    virustotal,
)
from app.intel.run import FEED_OF, Feed
from app.models import IntelOverride, IntelSubject, utcnow

RecorderDep = Annotated[Recorder, Depends(api_log_recorder)]

router = APIRouter(prefix="/threat-intel", tags=["threat-intel"], dependencies=[Depends(signed_in)])


type Provider = Literal["virustotal", "otx", "greynoise"]


class LookupIn(BaseModel):
    """What to search for: an internet address, a domain or a web address, and which service to
    ask."""

    model_config = ConfigDict(extra="forbid")

    subject: str = Field(max_length=subjects.MAX_LENGTH)
    provider: Provider = virustotal.PROVIDER
    # Ask the service again even if the answer kept is still fresh.
    refresh: bool = False


class DetailOut(BaseModel):
    label: str
    value: str


type Kind = Literal["ip", "domain", "url"]
type Judgement = Literal["malicious", "suspicious", "clean", "unknown"]
type Verdict = Literal["safe", "suspicious"]


class RulingIn(BaseModel):
    """What the owner makes of a subject: an internet address, a domain or a web address."""

    model_config = ConfigDict(extra="forbid")

    subject: str = Field(max_length=subjects.MAX_LENGTH)
    verdict: Verdict
    # Why, for whoever reads it later.
    note: str | None = Field(default=None, max_length=overrides.MAX_NOTE)


class RulingOut(BaseModel):
    """What the owner ruled of a subject, whatever the services made of it."""

    kind: Kind
    # The subject as it is shown: the address, the domain, or the host of a web address.
    subject: str
    verdict: Verdict
    note: str | None
    set_at: AwareDatetime
    # What the ruling comes to on the scale of a judgement.
    judgement: Judgement


class RulingsOut(BaseModel):
    items: list[RulingOut]


class LookupOut(BaseModel):
    """What a service reported of the subject, with the counts its judgement is made from, and what
    AresGate has kept of it. A ``cached`` answer was kept from an earlier check, so no answer came
    from the service this time. A ``stale`` one is past the time it is taken as fresh for, and the
    ``notice`` says why it could not be checked again."""

    # Which service it was, as its key and as it is called.
    provider: Provider
    provider_name: str
    kind: Kind
    # The subject as it was searched for. For a web address in the list of what is kept, its host.
    subject: str
    # What it comes to: the owner's ruling where there is one, else what the service made of it.
    judgement: Judgement
    # What the service made of it, which a ruling does not change.
    reported_judgement: Judgement
    # What the owner ruled of it, if they did.
    ruling: RulingOut | None
    checked_at: AwareDatetime
    cached: bool
    stale: bool
    notice: str | None
    # Whether a search for ``subject`` asks about this again: not so for a kept web address, which
    # is kept without its text.
    repeatable: bool
    first_checked_at: AwareDatetime
    checks: int
    # When the answer stops being taken as fresh, so the subject is asked about again.
    fresh_until: AwareDatetime
    # When a newer answer last changed the judgement, and what it was before.
    changed_at: AwareDatetime | None
    previous_judgement: Judgement | None
    analysed_at: AwareDatetime | None
    malicious: int
    suspicious: int
    harmless: int
    undetected: int
    reputation: int | None
    categories: list[str]
    details: list[DetailOut]
    # The subject's page on the service's own website, if it has one for this kind of subject.
    link: str | None


class CountsOut(BaseModel):
    malicious: int
    suspicious: int
    clean: int
    unknown: int


class KnownOut(BaseModel):
    """One page of the answers kept, newest first, and how many there are of each judgement."""

    total: int
    counts: CountsOut
    items: list[LookupOut]


@router.get("/subjects")
def list_known(
    db: Db,
    q: Annotated[
        str, Query(max_length=known.MAX_TEXT, description="Part of an address, name or owner.")
    ] = "",
    kind: Annotated[
        Kind | None, Query(description="Only addresses, domains or web addresses.")
    ] = None,
    judgement: Annotated[Judgement | None, Query(description="Only this judgement.")] = None,
    limit: Annotated[int, Query(ge=1, le=known.MAX_PAGE)] = 25,
    offset: Annotated[int, Query(ge=0, le=2**31 - 1)] = 0,
    provider: Annotated[Provider, Query(description="Which service's answers.")] = (
        virustotal.PROVIDER
    ),
) -> KnownOut:
    """Everything one service has answered and AresGate kept, newest first. It reads what is kept
    only, so it asks no service anything and counts toward no limit."""
    found = known.page(
        db,
        provider,
        text=q.strip(),
        kind=kind,
        judgement=judgement,
        limit=limit,
        offset=offset,
    )
    now = utcnow()
    return KnownOut(
        total=found.total,
        counts=CountsOut(**found.counts),
        items=[_out(row, None, now, cached=True, ruling=ruling) for row, ruling in found.rows],
    )


@router.post("/lookups")
def look_up(
    body: LookupIn,
    db: Db,
    settings: SettingsDep,
    recorder: RecorderDep,
) -> LookupOut:
    """Looks one subject up: from the answer kept for it while that is fresh, or else by asking the
    service, if the access level's limits and the service's own allow a lookup now."""
    feed = FEED_OF[body.provider]
    row = service.rows_for(db, feed.definition.key).get(feed.connection.key)
    if row is None or row.last_success_at is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Connect {feed.name} and test it before searching."
        )
    try:
        subject = subjects.parse(body.subject)
    except subjects.Refusal as refusal:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(refusal)) from refusal
    unasked = feed.refusal(subject)
    if unasked is not None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, unasked)
    if subject.address is not None and not candidates.sendable(
        subject.address, candidates.own_networks(db)
    ):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"That is this home's own address on the internet, so it isn't sent to {feed.name}.",
        )
    now = utcnow()
    kept = store.kept(db, feed.provider, subject)
    if kept is not None and not body.refresh and store.fresh(kept, now):
        return _out(kept, subject, now, cached=True, ruling=overrides.ruling_for(db, subject))
    try:
        target = service.load_target(db, settings, feed.definition, feed.connection, row)
    except service.Incomplete as incomplete:
        raise HTTPException(status.HTTP_409_CONFLICT, str(incomplete)) from incomplete
    level = feed.level_of(row.options)
    address, name = subject.recorded()
    try:
        lookup_id = budget.reserve(
            db, feed.provider, level, now, kind=subject.kind, address=address, subject=name
        )
    except budget.Paused as held:
        db.rollback()
        return _kept_or(db, feed, subject, now, _held(feed, held.pause, now))
    except budget.Wait as wait:
        db.rollback()
        seconds = math.ceil(wait.wait.total_seconds())
        refusal = HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"{feed.name}'s limit on searches is reached. Try again in {seconds} seconds.",
            headers={"Retry-After": str(seconds)},
        )
        return _kept_or(db, feed, subject, now, refusal)
    db.commit()
    policy = service.policy_for(feed.connection, netguard.HOME_NETWORK)
    answer = anyio.from_thread.run(_ask, feed, target, recorder, policy, subject, now)
    store.finish(db, lookup_id, subject, answer, now)
    if feed.remember is not None:
        feed.remember(row, answer, now)
    db.commit()
    if isinstance(answer, virustotal.Failed):
        failure = HTTPException(status.HTTP_502_BAD_GATEWAY, answer.message)
        return _kept_or(db, feed, subject, now, failure)
    if isinstance(answer, virustotal.Limited | virustotal.Throttled):
        pause = budget.Pause(until=answer.until, daily=isinstance(answer, virustotal.Limited))
        return _kept_or(db, feed, subject, now, _held(feed, pause, now))
    unkept = HTTPException(status.HTTP_502_BAD_GATEWAY, f"{feed.name}'s answer could not be kept.")
    return _kept_or(db, feed, subject, now, unkept, asked=True)


async def _ask(
    feed: Feed,
    target: Target,
    recorder: Recorder,
    policy: AddressPolicy,
    subject: subjects.Subject,
    now: datetime,
) -> virustotal.Answer:
    """Asks the service about a subject: what the thread that runs the search waits for."""
    return await feed.ask(target, recorder, policy, subject, now)


def _kept_or(
    db: Db,
    feed: Feed,
    subject: subjects.Subject,
    now: datetime,
    refusal: HTTPException,
    *,
    asked: bool = False,
) -> LookupOut:
    """What a search is answered with: the answer kept for its subject, or the refusal if nothing
    is kept. If the service wasn't ``asked``, or gave no answer, the answer is one kept from before,
    and the refusal's words say why it wasn't checked again."""
    kept = store.kept(db, feed.provider, subject)
    if kept is None:
        raise refusal
    ruling = overrides.ruling_for(db, subject)
    if asked:
        return _out(kept, subject, now, cached=False, ruling=ruling)
    return _out(kept, subject, now, cached=True, ruling=ruling, notice=str(refusal.detail))


def _held(feed: Feed, pause: budget.Pause, now: datetime) -> HTTPException:
    """The refusal of a search that a limit holds: which limit it is, and when it lifts."""
    seconds = math.ceil((pause.until - now).total_seconds())
    if pause.daily:
        message = (
            f"{feed.name}'s daily limit is reached. "
            f"Searches resume at {pause.until.astimezone(UTC):%H:%M} UTC."
        )
    else:
        message = f"{feed.name} asked for fewer requests. Try again in {seconds} seconds."
    return HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS, message, headers={"Retry-After": str(seconds)}
    )


def _link(row: IntelSubject) -> str | None:
    """The subject's page on its service's own website, if the service has one for it."""
    if row.provider == otx.PROVIDER:
        return otx.link_of(row.kind, row.subject)
    if row.provider == greynoise.PROVIDER:
        return greynoise.link_of(row.subject)
    return virustotal.link_of(row.kind, row.subject)


def _out(
    row: IntelSubject,
    subject: subjects.Subject | None,
    now: datetime,
    *,
    cached: bool,
    ruling: IntelOverride | None,
    notice: str | None = None,
) -> LookupOut:
    """The answer kept for a subject. A search shows the subject as it was searched for. The list
    of what is kept has no search, so it shows what the answer is kept as, and for a web address,
    which is kept as a hash, the host it was on. ``ruling`` is what the owner ruled of it."""
    answer = store.answer_of(row)
    report = answer.report if isinstance(answer, virustotal.Reported) else None
    reported = store.judge_for(row.provider, report)
    if subject is not None:
        text = subject.text
    elif row.kind == "url":
        text = row.host or "A web address"
    else:
        text = row.subject
    return LookupOut(
        provider=cast("Provider", row.provider),
        provider_name=FEED_OF[row.provider].name,
        kind=cast("Kind", row.kind),
        subject=text,
        judgement=cast("Judgement", overrides.effective(reported, ruling and ruling.verdict)),
        reported_judgement=reported,
        ruling=_ruling(ruling),
        checked_at=row.checked_at,
        cached=cached,
        stale=not store.fresh(row, now),
        notice=notice,
        repeatable=subject is not None or row.kind != "url",
        first_checked_at=row.first_checked_at,
        checks=row.checks,
        fresh_until=store.fresh_until(row),
        changed_at=row.changed_at,
        previous_judgement=cast("Judgement | None", row.previous_judgement),
        analysed_at=report.analysed_at if report else None,
        malicious=report.malicious if report else 0,
        suspicious=report.suspicious if report else 0,
        harmless=report.harmless if report else 0,
        undetected=report.undetected if report else 0,
        reputation=report.reputation if report else None,
        categories=list(report.categories) if report else [],
        details=[DetailOut(label=label, value=value) for label, value in report.details]
        if report
        else [],
        link=_link(row),
    )


def _ruling(found: IntelOverride | None) -> RulingOut | None:
    """What the owner ruled of a subject, as it is told, or nothing where they did not."""
    return None if found is None else _told(found)


def _told(found: IntelOverride) -> RulingOut:
    """What the owner ruled of a subject, as it is told."""
    return RulingOut(
        kind=cast("Kind", found.kind),
        subject=found.host,
        verdict=cast("Verdict", found.verdict),
        note=found.note,
        set_at=found.set_at,
        judgement=cast("Judgement", overrides.JUDGEMENT_OF[found.verdict]),
    )


def _subject_of(text: str) -> subjects.Subject:
    """What a ruling is about, or the refusal of it in words for the person ruling."""
    try:
        return subjects.parse(text)
    except subjects.Refusal as refusal:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(refusal)) from refusal


def _facts(found: IntelOverride) -> dict[str, str]:
    """What the audit log says of a ruling: what it is about and what it was. The owner's note is
    kept with the ruling, not in the log."""
    return {"kind": found.kind, "subject": found.host, "verdict": found.verdict}


@router.get("/overrides")
def list_rulings(db: Db) -> RulingsOut:
    """Everything the owner has ruled on, the latest first, whether or not any service has answered
    about it."""
    return RulingsOut(items=[_told(row) for row in overrides.listing(db)])


@router.put("/overrides")
def rule(
    body: RulingIn,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
) -> RulingOut:
    """Rules a subject safe or suspicious, whatever the services made of it, in place of any
    ruling there was. Nothing is sent to a service, and none is needed: a subject nobody has asked
    about can be ruled on too."""
    subject = _subject_of(body.subject)
    note = audit.clean(body.note, overrides.MAX_NOTE) if body.note else None
    found = overrides.rule(db, subject, body.verdict, note, utcnow())
    record_audit(
        db,
        request,
        Action.THREAT_INTEL_RULED,
        Outcome.SUCCESS,
        user=auth.user,
        detail=_facts(found),
    )
    db.commit()
    return _told(found)


@router.delete("/overrides", status_code=status.HTTP_204_NO_CONTENT)
def take_back(
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
    subject: Annotated[str, Query(max_length=subjects.MAX_LENGTH)],
) -> Response:
    """Takes back what the owner ruled of a subject, so it is what the services made of it again."""
    found = overrides.take_back(db, _subject_of(subject))
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nothing is ruled of that.")
    record_audit(
        db,
        request,
        Action.THREAT_INTEL_RULING_CLEARED,
        Outcome.SUCCESS,
        user=auth.user,
        detail=_facts(found),
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
