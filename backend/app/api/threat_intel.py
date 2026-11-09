"""Searches threat intelligence by hand: an internet address, a domain or a web address, and what
VirusTotal reported of it. A search shares its limits with the background lookups, so the two
together never ask VirusTotal more often than its free API allows."""

import math
from datetime import datetime
from typing import Annotated, Literal

import anyio.from_thread
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.api.deps import Db, SettingsDep, signed_in
from app.api.integrations import api_log_recorder
from app.integrations import netguard, service
from app.integrations.client import Recorder
from app.intel import budget, candidates, store, subjects, virustotal
from app.intel.run import CONNECTION, DEFINITION
from app.models import utcnow

RecorderDep = Annotated[Recorder, Depends(api_log_recorder)]

router = APIRouter(prefix="/threat-intel", tags=["threat-intel"], dependencies=[Depends(signed_in)])


class LookupIn(BaseModel):
    """What to search for: an internet address, a domain or a web address."""

    model_config = ConfigDict(extra="forbid")

    subject: str = Field(max_length=subjects.MAX_LENGTH)


class DetailOut(BaseModel):
    label: str
    value: str


class LookupOut(BaseModel):
    """What VirusTotal reported of the subject, with the counts its judgement is made from."""

    kind: Literal["ip", "domain", "url"]
    subject: str
    judgement: Literal["malicious", "suspicious", "clean", "unknown"]
    checked_at: AwareDatetime
    analysed_at: AwareDatetime | None
    malicious: int
    suspicious: int
    harmless: int
    undetected: int
    reputation: int | None
    categories: list[str]
    details: list[DetailOut]
    link: str


@router.post("/lookups")
def look_up(
    body: LookupIn,
    db: Db,
    settings: SettingsDep,
    recorder: RecorderDep,
) -> LookupOut:
    """Asks VirusTotal about one subject, if the access level's limits allow a lookup now."""
    row = service.rows_for(db, DEFINITION.key).get(CONNECTION.key)
    if row is None or row.last_success_at is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Connect VirusTotal and test it before searching."
        )
    try:
        subject = subjects.parse(body.subject)
    except subjects.Refusal as refusal:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(refusal)) from refusal
    if subject.address is not None and not candidates.sendable(
        subject.address, candidates.own_networks(db)
    ):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "That is this home's own address on the internet, so it isn't sent to VirusTotal.",
        )
    try:
        target = service.load_target(db, settings, DEFINITION, CONNECTION, row)
    except service.Incomplete as incomplete:
        raise HTTPException(status.HTTP_409_CONFLICT, str(incomplete)) from incomplete
    now = utcnow()
    level = budget.level_of(row.options)
    address, name = subject.recorded()
    try:
        lookup_id = budget.reserve(
            db,
            virustotal.PROVIDER,
            level,
            now,
            kind=subject.kind,
            address=address,
            subject=name,
        )
    except budget.Wait as wait:
        db.rollback()
        seconds = math.ceil(wait.wait.total_seconds())
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"VirusTotal's limit on searches is reached. Try again in {seconds} seconds.",
            headers={"Retry-After": str(seconds)},
        ) from wait
    db.commit()
    policy = service.policy_for(CONNECTION, netguard.HOME_NETWORK)
    answer = anyio.from_thread.run(virustotal.ask, target, recorder, policy, subject, now)
    store.finish(db, lookup_id, answer)
    db.commit()
    if isinstance(answer, virustotal.Failed):
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, answer.message)
    return _out(subject, answer, now)


def _out(subject: subjects.Subject, answer: virustotal.Answer, checked_at: datetime) -> LookupOut:
    report = answer.report if isinstance(answer, virustotal.Reported) else None
    if report is None:
        return LookupOut(
            kind=subject.kind,
            subject=subject.text,
            judgement=virustotal.judge(None),
            checked_at=checked_at,
            analysed_at=None,
            malicious=0,
            suspicious=0,
            harmless=0,
            undetected=0,
            reputation=None,
            categories=[],
            details=[],
            link=virustotal.link_for(subject),
        )
    return LookupOut(
        kind=subject.kind,
        subject=subject.text,
        judgement=virustotal.judge(report),
        checked_at=checked_at,
        analysed_at=report.analysed_at,
        malicious=report.malicious,
        suspicious=report.suspicious,
        harmless=report.harmless,
        undetected=report.undetected,
        reputation=report.reputation,
        categories=list(report.categories),
        details=[DetailOut(label=label, value=value) for label, value in report.details],
        link=virustotal.link_for(subject),
    )
