"""The signed-in person's own account: its password, and where it is signed in."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.api.auth import require_password
from app.api.deps import Db, SettingsDep, SignedIn, record_audit, signed_in
from app.audit import Action, Outcome
from app.models import UserSession, utcnow
from app.security import passwords, sessions

router = APIRouter(prefix="/auth", tags=["account"])


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=1024)
    new_password: str = Field(max_length=1024)


class SignIn(BaseModel):
    """A browser that is signed in to the account."""

    id: UUID
    # Whether it's the one asking.
    current: bool
    address: str | None
    # What the browser called itself, for the web app to put in words such as "Firefox on Linux".
    user_agent: str | None
    started_at: datetime
    last_seen_at: datetime
    # When it ends if nothing more happens.
    expires_at: datetime

    @classmethod
    def of(cls, row: UserSession, current: UserSession, expires_at: datetime) -> SignIn:
        return cls(
            id=row.id,
            current=row.id == current.id,
            address=row.address,
            user_agent=row.user_agent,
            started_at=row.created_at,
            last_seen_at=row.last_seen_at,
            expires_at=expires_at,
        )


class EndedSignIns(BaseModel):
    ended: int


@router.post("/password")
def change_password(
    body: PasswordChange,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
    settings: SettingsDep,
) -> EndedSignIns:
    """Changes the password, which takes the current one. Every other sign-in ends, so whoever
    had the old password or a stolen sign-in is out; this one stays. Says how many ended."""
    require_password(db, request, auth, body.current_password, purpose="changing_password")
    user = auth.user
    try:
        passwords.check_policy(
            body.new_password, username=user.username, server_name=settings.server_name
        )
    except passwords.PasswordPolicyError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    if passwords.verify_password(body.new_password, user.password_hash):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Choose a password you aren't using now."
        )

    now = utcnow()
    user.password_hash = passwords.hash_password(body.new_password)
    user.password_changed_at = now
    ended = sessions.end_all_but(db, user, auth.session)
    record_audit(
        db,
        request,
        Action.PASSWORD_CHANGED,
        Outcome.SUCCESS,
        user=user,
        detail={"sessions_ended": ended},
    )
    db.commit()
    return EndedSignIns(ended=ended)


@router.get("/sessions")
def list_sign_ins(
    auth: Annotated[SignedIn, Depends(signed_in)], db: Db, settings: SettingsDep
) -> list[SignIn]:
    rows = sessions.live_for(db, auth.user, settings, utcnow())
    return [SignIn.of(row, auth.session, sessions.expires_at(row, settings)) for row in rows]


@router.post("/sessions/end-others")
def end_other_sign_ins(
    auth: Annotated[SignedIn, Depends(signed_in)], request: Request, db: Db
) -> EndedSignIns:
    """Signs out everywhere but here."""
    ended = sessions.end_all_but(db, auth.user, auth.session)
    if ended:
        record_audit(
            db,
            request,
            Action.SESSIONS_ENDED,
            Outcome.SUCCESS,
            user=auth.user,
            detail={"count": ended},
        )
    db.commit()
    return EndedSignIns(ended=ended)


@router.post("/sessions/{session_id}/end", status_code=status.HTTP_204_NO_CONTENT)
def end_sign_in(
    session_id: UUID, auth: Annotated[SignedIn, Depends(signed_in)], request: Request, db: Db
) -> None:
    """Signs out one other browser. This one signs out from the account menu instead."""
    if session_id == auth.session.id:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "That's the browser you're using. Sign out instead."
        )
    if sessions.end_one(db, auth.user, session_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That sign-in has already ended.")
    record_audit(
        db,
        request,
        Action.SESSIONS_ENDED,
        Outcome.SUCCESS,
        user=auth.user,
        detail={"count": 1},
    )
    db.commit()
