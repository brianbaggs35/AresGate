"""Verdicts: what the owner says of a kind of signal (that it is not suspicious, is low priority,
or is a real threat), remembered as rules that are applied to the signals that follow. For
someone signed in."""

from datetime import datetime
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

from app.api.deps import Db, SignedIn, record_audit, signed_in
from app.audit import Action, Outcome
from app.incidents import engine, rules, verdicts
from app.integrations import registry
from app.models import VerdictRule

router = APIRouter(prefix="/verdicts", tags=["verdicts"], dependencies=[Depends(signed_in)])

Verdict = Literal["not_suspicious", "low_priority", "threat"]
RuleId = Annotated[int, Path(ge=1, le=2**63 - 1)]
Signature = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=256)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


class VerdictOut(BaseModel):
    id: int
    verdict: Verdict
    # What it is about. At least one is set, and a signal has to match all that are.
    address: str | None
    source: str | None
    source_name: str | None
    signature: str | None
    note: str | None
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
    source: str | None = None
    signature: Signature | None = None
    note: Note | None = None

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
        return self


class VerdictChange(BaseModel):
    """What can be changed of a verdict. What it is about can't: that is another verdict."""

    model_config = ConfigDict(extra="forbid")

    verdict: Verdict | None = None
    # Said as null, the note is taken off.
    note: Note | None = None


def _out(rule: VerdictRule, hits: tuple[int, datetime | None]) -> VerdictOut:
    return VerdictOut(
        id=rule.id,
        verdict=cast(Verdict, rule.verdict),
        address=str(rule.address) if rule.address is not None else None,
        source=rule.source,
        source_name=rules.name_of(rule.source) if rule.source is not None else None,
        signature=rule.signature,
        note=rule.note,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
        hits=hits[0],
        last_hit_at=hits[1],
    )


def _shown(db: Db, rule: VerdictRule) -> VerdictOut:
    return _out(rule, verdicts.hits(db, [rule.id]).get(rule.id, (0, None)))


def _given(db: Db, rule: VerdictRule, replaced: Verdict | None) -> VerdictGiven:
    return VerdictGiven(**_shown(db, rule).model_dump(), replaced=replaced)


def _found(db: Db, rule_id: int) -> VerdictRule:
    rule = db.get(VerdictRule, rule_id)
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There's no such verdict.")
    return rule


def _facts(rule: VerdictRule) -> dict[str, str | int | bool]:
    """What the audit log says of a verdict: which it is and what it is about."""
    facts: dict[str, str | int | bool] = {"verdict_id": rule.id, "verdict": rule.verdict}
    if rule.address is not None:
        facts["address"] = str(rule.address)
    if rule.source is not None:
        facts["source"] = rule.source
    if rule.signature is not None:
        facts["signature"] = rule.signature
    return facts


@router.get("")
def list_verdicts(db: Db) -> VerdictList:
    """The verdicts, the one given last first, with how many signals each has been applied to."""
    found = db.scalars(
        select(VerdictRule).order_by(VerdictRule.updated_at.desc(), VerdictRule.id.desc())
    ).all()
    hits = verdicts.hits(db, [rule.id for rule in found])
    return VerdictList(items=[_out(rule, hits.get(rule.id, (0, None))) for rule in found])


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
    rule = db.scalars(
        select(VerdictRule).where(
            VerdictRule.address.is_not_distinct_from(body.address),
            VerdictRule.source.is_not_distinct_from(body.source),
            VerdictRule.signature.is_not_distinct_from(body.signature),
        )
    ).first()
    if rule is None:
        rule = VerdictRule(
            verdict=body.verdict,
            address=body.address,
            source=body.source,
            signature=body.signature,
            note=body.note or None,
        )
        db.add(rule)
        db.flush()
        record_audit(
            db, request, Action.VERDICT_GIVEN, Outcome.SUCCESS, user=auth.user, detail=_facts(rule)
        )
        was = None
    else:
        response.status_code = status.HTTP_200_OK
        was = cast(Verdict, rule.verdict)
        rule.verdict = body.verdict
        if body.note:
            rule.note = body.note
        if not db.is_modified(rule):
            return _given(db, rule, was)
        record_audit(
            db,
            request,
            Action.VERDICT_CHANGED,
            Outcome.SUCCESS,
            user=auth.user,
            detail={**_facts(rule), "from": was},
        )
    engine.reapply(db)
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
    if db.is_modified(rule):
        record_audit(
            db,
            request,
            Action.VERDICT_CHANGED,
            Outcome.SUCCESS,
            user=auth.user,
            detail={**_facts(rule), "from": was},
        )
        engine.reapply(db)
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
    said, in the incidents that are not over."""
    engine.hold(db)
    rule = _found(db, rule_id)
    record_audit(
        db, request, Action.VERDICT_REMOVED, Outcome.SUCCESS, user=auth.user, detail=_facts(rule)
    )
    db.delete(rule)
    db.flush()
    engine.reapply(db)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
