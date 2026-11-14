"""Verdicts: what the owner says of a kind of signal (that it is not suspicious, is low priority,
or is a real threat), remembered as rules that are applied to the signals that follow. For
someone signed in."""

from datetime import datetime
from ipaddress import ip_network
from typing import Annotated, Literal, Self, cast

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response, status
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    IPvAnyAddress,
    StringConstraints,
    field_validator,
    model_validator,
)
from sqlalchemy import select

from app.ai import clearing
from app.api.deps import Db, SignedIn, record_audit, signed_in
from app.audit import Action, Outcome
from app.incidents import engine, rules, verdicts
from app.incidents.trust import destination_text
from app.integrations import registry
from app.models import VerdictRule

router = APIRouter(prefix="/verdicts", tags=["verdicts"], dependencies=[Depends(signed_in)])

Verdict = Literal["not_suspicious", "low_priority", "threat"]
RuleId = Annotated[int, Path(ge=1, le=2**63 - 1)]
Signature = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=256)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


class GivenByAi(BaseModel):
    """How the AI came to give a verdict, as it said at the time."""

    confidence: int
    provider: str | None
    model: str | None
    # The incident it was reading, if that still exists.
    incident_id: int | None


class VerdictOut(BaseModel):
    id: int
    verdict: Verdict
    # What it is about. At least one is set, and a signal has to match all that are.
    address: str | None
    # Where that address sends its traffic, as one address or a network. Only with an address.
    destination: str | None
    source: str | None
    source_name: str | None
    signature: str | None
    # For the AI's, why it said so: its reason.
    note: str | None
    # Who gave it. The AI gives one only where the owner allows it, and it is theirs to take back.
    given_by: Literal["owner", "ai"]
    ai: GivenByAi | None
    created_at: AwareDatetime
    updated_at: AwareDatetime
    # How many signals in incidents it has been applied to, and when the latest happened.
    hits: int
    last_hit_at: AwareDatetime | None


class VerdictGiven(VerdictOut):
    """A verdict as it was just given, and what it said before when it changed one."""

    replaced: Verdict | None


class VerdictList(BaseModel):
    items: list[VerdictOut]


class VerdictIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Verdict
    # A signal matches by the address it is about, or came from, not the one it went to.
    address: IPvAnyAddress | None = None
    # Where that address sends its traffic: one address, or a whole network such as 52.0.0.0/8.
    destination: str | None = None
    source: str | None = None
    signature: Signature | None = None
    note: Note | None = None

    @field_validator("destination")
    @classmethod
    def _network(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return str(ip_network(value.strip(), strict=True))
        except ValueError as error:
            raise ValueError(
                "A destination is an address or a whole network, such as 52.0.0.0/8."
            ) from error

    @field_validator("source")
    @classmethod
    def _known(cls, value: str | None) -> str | None:
        if value is not None and value not in registry.INTEGRATIONS:
            raise ValueError("That isn't a program AresGate works with.")
        return value

    @model_validator(mode="after")
    def _about_something(self) -> Self:
        if self.address is None and self.source is None and self.signature is None:
            raise ValueError("Say what it is about: an address, a program or a signature.")
        if self.destination is not None and self.address is None:
            raise ValueError("A destination is where an address sends: name that address too.")
        return self


class VerdictChange(BaseModel):
    """What can be changed of a verdict. What it is about can't: that is another verdict."""

    model_config = ConfigDict(extra="forbid")

    verdict: Verdict | None = None
    # Said as null, the note is taken off.
    note: Note | None = None


def rule_out(rule: VerdictRule, hits: tuple[int, datetime | None]) -> VerdictOut:
    return VerdictOut(
        id=rule.id,
        verdict=cast(Verdict, rule.verdict),
        address=str(rule.address) if rule.address is not None else None,
        destination=(destination_text(rule.destination) if rule.destination is not None else None),
        source=rule.source,
        source_name=rules.name_of(rule.source) if rule.source is not None else None,
        signature=rule.signature,
        note=rule.note,
        given_by=cast(Literal["owner", "ai"], rule.given_by),
        ai=(
            GivenByAi(
                confidence=rule.ai_confidence or 0,
                provider=rule.ai_provider,
                model=rule.ai_model,
                incident_id=rule.ai_incident_id,
            )
            if rule.given_by == clearing.GIVER_AI
            else None
        ),
        created_at=rule.created_at,
        updated_at=rule.updated_at,
        hits=hits[0],
        last_hit_at=hits[1],
    )


def _shown(db: Db, rule: VerdictRule) -> VerdictOut:
    return rule_out(rule, verdicts.hits(db, [rule.id]).get(rule.id, (0, None)))


def _given(db: Db, rule: VerdictRule, replaced: Verdict | None) -> VerdictGiven:
    return VerdictGiven(**_shown(db, rule).model_dump(), replaced=replaced)


def _found(db: Db, rule_id: int) -> VerdictRule:
    rule = db.get(VerdictRule, rule_id)
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There's no such verdict.")
    return rule


def facts(rule: VerdictRule) -> dict[str, str | int | bool]:
    """What the audit log says of a verdict: which it is and what it is about."""
    said: dict[str, str | int | bool] = {"verdict_id": rule.id, "verdict": rule.verdict}
    if rule.address is not None:
        said["address"] = str(rule.address)
    if rule.destination is not None:
        said["destination"] = destination_text(rule.destination)
    if rule.source is not None:
        said["source"] = rule.source
    if rule.signature is not None:
        said["signature"] = rule.signature
    return said


@router.get("")
def list_verdicts(db: Db) -> VerdictList:
    """The verdicts, the one given last first, with how many signals each has been applied to."""
    found = db.scalars(
        select(VerdictRule).order_by(VerdictRule.updated_at.desc(), VerdictRule.id.desc())
    ).all()
    hits = verdicts.hits(db, [rule.id for rule in found])
    return VerdictList(items=[rule_out(rule, hits.get(rule.id, (0, None))) for rule in found])


@router.post("", status_code=status.HTTP_201_CREATED)
def give_verdict(
    body: VerdictIn,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    response: Response,
    db: Db,
) -> VerdictGiven:
    """Says what is thought of the signals that match. Saying it again of the same thing changes
    the verdict (and says what it was), and a verdict is applied at once to the incidents that
    are not over."""
    engine.hold(db)
    destination = ip_network(body.destination) if body.destination is not None else None
    rule = db.scalars(
        select(VerdictRule).where(
            VerdictRule.address.is_not_distinct_from(body.address),
            VerdictRule.destination.is_not_distinct_from(destination),
            VerdictRule.source.is_not_distinct_from(body.source),
            VerdictRule.signature.is_not_distinct_from(body.signature),
        )
    ).first()
    if rule is None:
        rule = VerdictRule(
            verdict=body.verdict,
            address=body.address,
            destination=destination,
            source=body.source,
            signature=body.signature,
            note=body.note or None,
        )
        db.add(rule)
        db.flush()
        record_audit(
            db, request, Action.VERDICT_GIVEN, Outcome.SUCCESS, user=auth.user, detail=facts(rule)
        )
        was = None
    else:
        response.status_code = status.HTTP_200_OK
        was = cast(Verdict, rule.verdict)
        rule.verdict = body.verdict
        if body.note:
            rule.note = body.note
        # Saying what the AI said makes it the owner's.
        claimed = clearing.claim(rule)
        if not (db.is_modified(rule) or claimed):
            return _given(db, rule, was)
        record_audit(
            db,
            request,
            Action.VERDICT_CHANGED,
            Outcome.SUCCESS,
            user=auth.user,
            detail={**facts(rule), "from": was},
        )
    engine.reapply(db, engine.reach(db, rule))
    db.commit()
    return _given(db, rule, was)


@router.patch("/{rule_id}")
def change_verdict(
    rule_id: RuleId,
    body: VerdictChange,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
) -> VerdictOut:
    """Changes what is said, or why."""
    engine.hold(db)
    rule = _found(db, rule_id)
    was = rule.verdict
    if body.verdict is not None:
        rule.verdict = body.verdict
    if "note" in body.model_fields_set:
        rule.note = body.note or None
    # A verdict the AI gave and the owner changed is theirs now.
    claimed = clearing.claim(rule) if db.is_modified(rule) else False
    if db.is_modified(rule) or claimed:
        record_audit(
            db,
            request,
            Action.VERDICT_CHANGED,
            Outcome.SUCCESS,
            user=auth.user,
            detail={**facts(rule), "from": was},
        )
        engine.reapply(db, engine.reach(db, rule))
        db.commit()
    return _shown(db, rule)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_verdict(
    rule_id: RuleId,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
) -> Response:
    """Takes a verdict back: the signals it was applied to are judged as if it had never been
    said, in the incidents that are not over. Taking back one the AI gave also tells it not to give
    that verdict again."""
    engine.hold(db)
    rule = _found(db, rule_id)
    if rule.given_by == clearing.GIVER_AI:
        clearing.take_back(db, rule)
        record_audit(
            db,
            request,
            Action.VERDICT_TAKEN_BACK_FROM_AI,
            Outcome.SUCCESS,
            user=auth.user,
            detail=facts(rule),
        )
    else:
        record_audit(
            db, request, Action.VERDICT_REMOVED, Outcome.SUCCESS, user=auth.user, detail=facts(rule)
        )
    reached = engine.reach(db, rule)
    db.delete(rule)
    db.flush()
    engine.reapply(db, reached)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
