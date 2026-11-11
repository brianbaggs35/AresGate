"""Trust: what the owner has said is safe, in one place. A trust decision is a verdict that keeps
what it matches from ever raising an alarm (``not_suspicious``, or ``low_priority`` for what is
only worth a glance), so it holds for every program AresGate reads: it is judged on the signals,
not on where they came from. This is the page's own view of those verdicts, with what each has been
applied to, an edit that can change what it is about, and what the AI would trust. For someone
signed in."""

from datetime import datetime
from ipaddress import ip_address, ip_network
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response, status
from pydantic import AwareDatetime, BaseModel
from sqlalchemy import and_, func, select

from app.api import verdicts as verdicts_api
from app.api.dashboard import SEVERITY_NAMES, SeverityName
from app.api.deps import Db, SignedIn, record_audit, signed_in
from app.audit import Action, Outcome
from app.events.event import Severity
from app.incidents import engine, verdicts
from app.incidents.trust import about
from app.models import AiTriage, Incident, IncidentSignal, VerdictRule

router = APIRouter(prefix="/trust", tags=["trust"], dependencies=[Depends(signed_in)])

RuleId = Annotated[int, Path(ge=1, le=2**63 - 1)]
Level = Literal["not_suspicious", "low_priority"]
# How many incidents a decision lists as what it was applied to, and how many suggestions there are.
MAX_APPLIED = 25
MAX_SUGGESTED = 10
# The least an AI has to be sure of to suggest trusting something.
MIN_CONFIDENCE = 60
OVER = ("resolved", "dismissed")


class TrustIn(verdicts_api.VerdictIn):
    """A trust decision: what it is about, and how much to trust it. Safe by default."""

    verdict: Level = "not_suspicious"  # type: ignore[assignment]


class TrustOut(verdicts_api.VerdictOut):
    verdict: Level  # type: ignore[assignment]
    # What it is about, in a sentence.
    about: str
    # How many incidents it has been applied to.
    incidents: int


class TrustList(BaseModel):
    items: list[TrustOut]
    safe: int
    low_priority: int
    # How many signals, in all, have been kept from raising an alarm by one of them.
    applied: int


class AppliedIncident(BaseModel):
    id: int
    title: str
    severity: SeverityName
    status: str
    last_seen_at: AwareDatetime
    # How many of its signals this decision was applied to.
    signals: int


class TrustDetail(TrustOut):
    applied_to: list[AppliedIncident]


class Suggestion(BaseModel):
    """An incident the AI read and thinks is nothing to worry about, and that nothing says is
    trusted yet. Trusting it is the owner's call."""

    incident_id: int
    title: str
    subject: str
    severity: SeverityName
    last_seen_at: AwareDatetime
    verdict: Level
    confidence: int
    headline: str
    reason: str | None


class Suggestions(BaseModel):
    items: list[Suggestion]


def _counts(db: Db, ids: list[int]) -> dict[int, int]:
    rows = db.execute(
        select(
            IncidentSignal.verdict_rule_id, func.count(func.distinct(IncidentSignal.incident_id))
        )
        .where(IncidentSignal.verdict_rule_id.in_(ids))
        .group_by(IncidentSignal.verdict_rule_id)
    ).all()
    return {rule_id: count for rule_id, count in rows if rule_id is not None}


def _out(rule: VerdictRule, hits: tuple[int, datetime | None], incidents: int) -> TrustOut:
    base = verdicts_api.rule_out(rule, hits)
    return TrustOut(**base.model_dump(), about=about(rule), incidents=incidents)  # type: ignore[arg-type]


def _shown(db: Db, rule: VerdictRule) -> TrustOut:
    hits = verdicts.hits(db, [rule.id]).get(rule.id, (0, None))
    return _out(rule, hits, _counts(db, [rule.id]).get(rule.id, 0))


def _found(db: Db, rule_id: int) -> VerdictRule:
    rule = db.get(VerdictRule, rule_id)
    if rule is None or rule.verdict not in verdicts.MUTING:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There's no such trust decision.")
    return rule


@router.get("")
def list_trust(db: Db) -> TrustList:
    """The trust decisions, the one changed last first, with what each has been applied to."""
    found = list(
        db.scalars(
            select(VerdictRule)
            .where(VerdictRule.verdict.in_(verdicts.MUTING))
            .order_by(VerdictRule.updated_at.desc(), VerdictRule.id.desc())
        )
    )
    ids = [rule.id for rule in found]
    hits = verdicts.hits(db, ids)
    counts = _counts(db, ids)
    items = [_out(rule, hits.get(rule.id, (0, None)), counts.get(rule.id, 0)) for rule in found]
    return TrustList(
        items=items,
        safe=sum(1 for each in items if each.verdict == "not_suspicious"),
        low_priority=sum(1 for each in items if each.verdict == "low_priority"),
        applied=sum(each.hits for each in items),
    )


@router.get("/suggestions")
def suggest_trust(db: Db) -> Suggestions:
    """Incidents the AI read and is sure are nothing to worry about, that no decision covers yet:
    one that is about an address and that it suggests to trust, the most sure first."""
    trusted = select(VerdictRule.address).where(VerdictRule.address.is_not(None))
    rows = db.execute(
        select(Incident, AiTriage)
        .join(AiTriage, AiTriage.incident_id == Incident.id)
        .where(
            AiTriage.verdict.in_(verdicts.MUTING),
            AiTriage.confidence >= MIN_CONFIDENCE,
            Incident.status.notin_(OVER),
        )
        .order_by(AiTriage.confidence.desc(), Incident.last_seen_at.desc())
        .limit(MAX_SUGGESTED * 4)
    ).all()
    held = {str(address) for address in db.scalars(trusted)}
    items: list[Suggestion] = []
    for incident, reading in rows:
        if incident.subject in held or not _is_address(incident.subject):
            continue
        items.append(
            Suggestion(
                incident_id=incident.id,
                title=incident.title,
                subject=incident.subject,
                severity=SEVERITY_NAMES[Severity(incident.severity)],
                last_seen_at=incident.last_seen_at,
                verdict=cast(Level, reading.verdict),
                confidence=reading.confidence,
                headline=reading.headline,
                reason=reading.verdict_reason,
            )
        )
        if len(items) == MAX_SUGGESTED:
            break
    return Suggestions(items=items)


def _is_address(text: str) -> bool:
    try:
        ip_address(text)
    except ValueError:
        return False
    return True


@router.get("/{rule_id}")
def get_trust(rule_id: RuleId, db: Db) -> TrustDetail:
    """One decision, with the incidents it has been applied to."""
    rule = _found(db, rule_id)
    rows = db.execute(
        select(Incident, func.count())
        .join(IncidentSignal, IncidentSignal.incident_id == Incident.id)
        .where(IncidentSignal.verdict_rule_id == rule.id)
        .group_by(Incident.id)
        .order_by(Incident.last_seen_at.desc())
        .limit(MAX_APPLIED)
    ).all()
    return TrustDetail(
        **_shown(db, rule).model_dump(),
        applied_to=[
            AppliedIncident(
                id=incident.id,
                title=incident.title,
                severity=SEVERITY_NAMES[Severity(incident.severity)],
                status=incident.status,
                last_seen_at=incident.last_seen_at,
                signals=signals,
            )
            for incident, signals in rows
        ],
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def trust(
    body: TrustIn,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    response: Response,
    db: Db,
) -> TrustOut:
    """Trusts what the decision is about, and applies it at once to the incidents that are not
    over. Saying it again of the same thing changes how much it is trusted."""
    given = verdicts_api.give_verdict(
        verdicts_api.VerdictIn(**body.model_dump()), auth, request, response, db
    )
    return _shown(db, db.get_one(VerdictRule, given.id))


def _same(db: Db, rule: VerdictRule, body: TrustIn) -> VerdictRule | None:
    destination = ip_network(body.destination) if body.destination is not None else None
    return db.scalars(
        select(VerdictRule).where(
            and_(
                VerdictRule.id != rule.id,
                VerdictRule.address.is_not_distinct_from(body.address),
                VerdictRule.destination.is_not_distinct_from(destination),
                VerdictRule.source.is_not_distinct_from(body.source),
                VerdictRule.signature.is_not_distinct_from(body.signature),
            )
        )
    ).first()


@router.put("/{rule_id}")
def edit_trust(
    rule_id: RuleId,
    body: TrustIn,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
) -> TrustOut:
    """Changes everything about a decision: what it is about, how much it is trusted and why. The
    incidents it was applied to, and those it now reaches, are judged again."""
    engine.hold(db)
    rule = _found(db, rule_id)
    if _same(db, rule, body) is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "There is already a decision about that. Change that one, or take it back first.",
        )
    was = {**verdicts_api.facts(rule)}
    reached = engine.reach(db, rule)
    rule.verdict = body.verdict
    rule.address = body.address
    rule.destination = ip_network(body.destination) if body.destination is not None else None
    rule.source = body.source
    rule.signature = body.signature
    rule.note = body.note or None
    if db.is_modified(rule):
        db.flush()
        record_audit(
            db,
            request,
            Action.VERDICT_CHANGED,
            Outcome.SUCCESS,
            user=auth.user,
            detail={**verdicts_api.facts(rule), "from": str(was.get("verdict"))},
        )
        engine.reapply(db, reached | engine.reach(db, rule))
        db.commit()
    return _shown(db, rule)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_trust(
    rule_id: RuleId,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
) -> Response:
    """Takes the decision back: what it kept from raising an alarm is judged as if it had never
    been said, in the incidents that are not over."""
    _found(db, rule_id)
    return verdicts_api.remove_verdict(rule_id, auth, request, db)
