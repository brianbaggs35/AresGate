"""The secrets AresGate holds for integrations and AI providers. They only go in: nothing here
returns one, and a failed request doesn't quote what was sent."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.api.deps import Db, SettingsDep, SignedIn, record_audit, signed_in
from app.audit import Action, Detail, Outcome
from app.models import utcnow
from app.security import credential_store
from app.security.credential_store import NAME_PATTERN, Kind

# Everything here is for someone who is signed in.
router = APIRouter(prefix="/credentials", tags=["credentials"], dependencies=[Depends(signed_in)])

Name = Annotated[str, Path(pattern=NAME_PATTERN, description="A lowercase word, such as opnsense.")]


class CredentialInfo(BaseModel):
    """Which secret it is and when it was set, and nothing of the secret."""

    model_config = ConfigDict(from_attributes=True)

    kind: Kind
    name: str
    field: str
    created_at: datetime
    updated_at: datetime


class CredentialValue(BaseModel):
    value: SecretStr = Field(min_length=1, max_length=4096)

    @field_validator("value")
    @classmethod
    def not_blank(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("Enter a value.")
        return value


def _detail(kind: Kind, name: str, field: str) -> Detail:
    return {"kind": kind.value, "name": name, "field": field}


@router.get("")
def list_credentials(db: Db) -> list[CredentialInfo]:
    """Which secrets are set. Their values are never returned."""
    return [CredentialInfo.model_validate(row) for row in credential_store.entries(db)]


@router.put("/{kind}/{name}/{field}")
def set_credential(
    kind: Kind,
    name: Name,
    field: Name,
    body: CredentialValue,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
    settings: SettingsDep,
) -> CredentialInfo:
    """Keeps a secret, replacing the one already there."""
    row = credential_store.store(
        db, settings, kind, name, field, body.value.get_secret_value(), utcnow()
    )
    record_audit(
        db,
        request,
        Action.CREDENTIAL_STORED,
        Outcome.SUCCESS,
        user=auth.user,
        detail=_detail(kind, name, field),
    )
    db.commit()
    return CredentialInfo.model_validate(row)


@router.delete("/{kind}/{name}/{field}", status_code=status.HTTP_204_NO_CONTENT)
def delete_credential(
    kind: Kind,
    name: Name,
    field: Name,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
) -> Response:
    """Forgets a secret."""
    if not credential_store.remove(db, kind, name, field):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There is no such secret.")
    record_audit(
        db,
        request,
        Action.CREDENTIAL_DELETED,
        Outcome.SUCCESS,
        user=auth.user,
        detail=_detail(kind, name, field),
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
