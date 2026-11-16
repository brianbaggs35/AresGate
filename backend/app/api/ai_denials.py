"""What the owner denied the assistant: recorded when they press *Deny* on a proposal in the chat,
listed, and forgotten, one at a time or all together. For someone signed in. A denial only stops
the same proposal being made again (app/ai/denials.py); it changes nothing else."""

from typing import Annotated, Literal, Self

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response, status
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.ai import chat, denials
from app.api.deps import Db, SignedIn, record_audit, signed_in
from app.audit import Action, Outcome
from app.models import utcnow
from app.models.verdicts import VERDICTS

router = APIRouter(prefix="/ai/denials", tags=["ai"], dependencies=[Depends(signed_in)])

DenialId = Annotated[int, Path(ge=1, le=2**63 - 1)]
Value = Literal[
    "open",
    "investigating",
    "resolved",
    "dismissed",
    "not_suspicious",
    "low_priority",
    "threat",
]


class DenyIn(BaseModel):
    """A proposal the owner denied: the kind of change, to what, and the incidents it was for."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["status", "verdict"]
    value: Value
    incident_ids: list[Annotated[int, Field(ge=1, le=2**63 - 1)]] = Field(
        min_length=1, max_length=chat.MAX_INCIDENTS
    )

    @model_validator(mode="after")
    def _fits(self) -> Self:
        if (self.value in VERDICTS) != (self.kind == "verdict"):
            raise ValueError(f"{self.value} is not a {self.kind}.")
        return self


class DenialOut(BaseModel):
    id: int
    kind: Literal["status", "verdict"]
    value: str
    incident_id: int
    title: str
    denied_at: AwareDatetime
    # When it stops standing by itself, if the incident does not change first.
    expires_at: AwareDatetime


class DenialsOut(BaseModel):
    items: list[DenialOut]
    # How long a denial stands, in days.
    days: int


class RecordedOut(BaseModel):
    recorded: int


class ForgottenOut(BaseModel):
    forgotten: int


def _shown(db: Db) -> DenialsOut:
    return DenialsOut(
        items=[
            DenialOut.model_validate(item, from_attributes=True)
            for item in denials.listed(db, utcnow())
        ],
        days=denials.DAYS,
    )


@router.get("")
def list_denials(db: Db) -> DenialsOut:
    """What stands denied, the latest first."""
    return _shown(db)


@router.post("", status_code=status.HTTP_201_CREATED)
def deny(
    body: DenyIn, auth: Annotated[SignedIn, Depends(signed_in)], request: Request, db: Db
) -> RecordedOut:
    """Records a proposal as denied, for the incidents of it that exist."""
    recorded = denials.record(db, body.kind, body.value, body.incident_ids, utcnow())
    record_audit(
        db,
        request,
        Action.AI_PROPOSAL_DENIED,
        Outcome.SUCCESS,
        user=auth.user,
        detail={"kind": body.kind, "value": body.value, "incidents": recorded},
    )
    db.commit()
    return RecordedOut(recorded=recorded)


@router.delete("/{denial_id}", status_code=status.HTTP_204_NO_CONTENT)
def forget(
    denial_id: DenialId, auth: Annotated[SignedIn, Depends(signed_in)], request: Request, db: Db
) -> Response:
    """Forgets one denial, so that the assistant may propose it again."""
    if not denials.forget(db, denial_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There is no such denial.")
    record_audit(
        db,
        request,
        Action.AI_DENIALS_FORGOTTEN,
        Outcome.SUCCESS,
        user=auth.user,
        detail={"count": 1},
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("")
def forget_all(
    auth: Annotated[SignedIn, Depends(signed_in)], request: Request, db: Db
) -> ForgottenOut:
    """Forgets every denial."""
    count = denials.forget_all(db)
    if count:
        record_audit(
            db,
            request,
            Action.AI_DENIALS_FORGOTTEN,
            Outcome.SUCCESS,
            user=auth.user,
            detail={"count": count},
        )
    db.commit()
    return ForgottenOut(forgotten=count)
