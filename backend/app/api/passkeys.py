"""Passkeys: adding them to an account, taking them off, and signing in with one."""

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app import audit
from app.api.auth import SessionInfo, current_lockouts, open_session, too_many_attempts
from app.api.deps import Db, SettingsDep, SignedIn, client_address, record_audit, signed_in
from app.audit import Action, Detail, Outcome
from app.models import Passkey, User, utcnow
from app.security import passkeys, passwords, throttle
from app.security.throttle import Scope

router = APIRouter(prefix="/auth", tags=["auth"])


class PasskeyInfo(BaseModel):
    id: UUID
    name: str
    created_at: datetime
    last_used_at: datetime | None

    @classmethod
    def of(cls, passkey: Passkey) -> PasskeyInfo:
        return cls(
            id=passkey.id,
            name=passkey.name,
            created_at=passkey.created_at,
            last_used_at=passkey.last_used_at,
        )


class PasswordRequest(BaseModel):
    password: str = Field(max_length=1024)


class Challenge(BaseModel):
    # Sent back with the device's answer. ``options`` is what the browser asks the device to
    # sign, in the form its ``parseCreationOptionsFromJSON`` and
    # ``parseRequestOptionsFromJSON`` take.
    challenge_id: UUID
    options: dict[str, Any]


class NewPasskey(BaseModel):
    challenge_id: UUID
    # What the browser's ``PublicKeyCredential.toJSON()`` gives.
    credential: dict[str, Any]
    name: str = Field(min_length=1, max_length=256)


class PasskeySignIn(BaseModel):
    challenge_id: UUID
    credential: dict[str, Any]


def _sign_in_detail(**facts: str) -> Detail:
    """What the audit log keeps about a sign-in with a passkey, on top of how it was done."""
    return {"method": "passkey", **facts}


def _require_password(
    db: Db, request: Request, auth: SignedIn, password: str, *, purpose: str
) -> None:
    """Refuses unless the password is right, since a sign-in left open on a borrowed computer
    shouldn't be able to put its own passkey on the account. Wrong guesses count towards the
    same lockout as at the sign-in page."""
    now = utcnow()
    address = client_address(request)
    username = auth.user.username
    if waits := current_lockouts(db, address, username, now):
        raise too_many_attempts(max(waits))
    if passwords.verify_password(password, auth.user.password_hash):
        return
    throttle.record_failure(db, Scope.ADDRESS, address, now)
    throttle.record_failure(db, Scope.ACCOUNT, username, now)
    detail: Detail = {"reason": "wrong_password", "while": purpose}
    record_audit(db, request, Action.LOGIN_FAILED, Outcome.FAILURE, user=auth.user, detail=detail)
    db.commit()
    # Not 401, which the web app takes to mean the sign-in itself has ended.
    raise HTTPException(status.HTTP_403_FORBIDDEN, "The password isn't right.")


@router.get("/passkeys")
def list_passkeys(auth: Annotated[SignedIn, Depends(signed_in)], db: Db) -> list[PasskeyInfo]:
    return [PasskeyInfo.of(passkey) for passkey in passkeys.for_user(db, auth.user.id)]


@router.post("/passkeys/options")
def start_adding_passkey(
    body: PasswordRequest,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
    settings: SettingsDep,
) -> Challenge:
    """What the browser asks a device to make a passkey from. It needs the password."""
    _require_password(db, request, auth, body.password, purpose="adding_passkey")
    try:
        challenge_id, options = passkeys.begin_registration(db, settings, auth.user, utcnow())
    except passkeys.TooMany as error:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"An account can have {passkeys.MOST_PER_ACCOUNT} passkeys. Remove one first.",
        ) from error
    db.commit()
    return Challenge(challenge_id=challenge_id, options=options)


@router.post("/passkeys", status_code=status.HTTP_201_CREATED)
def add_passkey(
    body: NewPasskey,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
    settings: SettingsDep,
) -> PasskeyInfo:
    """Keeps the passkey a device made from the options above."""
    name = audit.clean(body.name, 64)
    if name is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Give the passkey a name.")
    try:
        passkey = passkeys.finish_registration(
            db, settings, auth.user, body.challenge_id, body.credential, name, utcnow()
        )
    except passkeys.ChallengeGone as error:
        db.commit()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "That took too long. Start adding the passkey again."
        ) from error
    except passkeys.Rejected as error:
        detail: Detail = {"reason": error.reason}
        record_audit(
            db, request, Action.PASSKEY_ADDED, Outcome.FAILURE, user=auth.user, detail=detail
        )
        db.commit()
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "That passkey couldn't be added. It has to be one that this device unlocks itself.",
        ) from error
    except passkeys.AlreadyRegistered as error:
        db.commit()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "That passkey is already on an account."
        ) from error
    record_audit(
        db,
        request,
        Action.PASSKEY_ADDED,
        Outcome.SUCCESS,
        user=auth.user,
        detail={"name": passkey.name},
    )
    db.commit()
    return PasskeyInfo.of(passkey)


@router.post("/passkeys/{passkey_id}/remove", status_code=status.HTTP_204_NO_CONTENT)
def remove_passkey(
    passkey_id: UUID,
    body: PasswordRequest,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
) -> None:
    """Forgets a passkey. It needs the password, so a borrowed sign-in can't take away the
    passkeys the owner would use to get back in."""
    _require_password(db, request, auth, body.password, purpose="removing_passkey")
    removed = passkeys.remove(db, auth.user.id, passkey_id)
    if removed is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There is no such passkey.")
    record_audit(
        db,
        request,
        Action.PASSKEY_REMOVED,
        Outcome.SUCCESS,
        user=auth.user,
        detail={"name": removed.name},
    )
    db.commit()


@router.post("/login/passkey/options")
def start_passkey_sign_in(request: Request, db: Db, settings: SettingsDep) -> Challenge:
    """What the browser asks a device to sign. Nobody has said who they are yet."""
    now = utcnow()
    if wait := throttle.remaining_lockout(db, Scope.ADDRESS, client_address(request), now):
        raise too_many_attempts(wait)
    challenge_id, options = passkeys.begin_sign_in(db, settings, now)
    db.commit()
    return Challenge(challenge_id=challenge_id, options=options)


@router.post("/login/passkey")
def log_in_with_passkey(
    body: PasskeySignIn,
    request: Request,
    response: Response,
    db: Db,
    settings: SettingsDep,
) -> SessionInfo:
    """Signs in with the device's answer. A passkey is the password and the second step in one:
    the device unlocks it with a fingerprint, a face or a PIN. Failures count against the
    address only, since nobody has said whose account they are after."""
    now = utcnow()
    address = client_address(request)
    if wait := throttle.remaining_lockout(db, Scope.ADDRESS, address, now):
        raise too_many_attempts(wait)
    try:
        passkey = passkeys.finish_sign_in(db, settings, body.challenge_id, body.credential, now)
    except (passkeys.ChallengeGone, passkeys.Rejected) as error:
        reason = error.reason if isinstance(error, passkeys.Rejected) else "challenge_gone"
        user = (
            db.get(User, error.user_id)
            if isinstance(error, passkeys.Rejected) and error.user_id
            else None
        )
        throttle.record_failure(db, Scope.ADDRESS, address, now)
        record_audit(
            db,
            request,
            Action.LOGIN_FAILED,
            Outcome.FAILURE,
            user=user,
            detail=_sign_in_detail(reason=reason),
        )
        db.commit()
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Your sign-in timed out. Try again."
            if isinstance(error, passkeys.ChallengeGone)
            else "That passkey didn't work.",
        ) from error
    user = db.get_one(User, passkey.user_id)
    throttle.clear(db, Scope.ADDRESS, address)
    record_audit(
        db,
        request,
        Action.LOGIN_SUCCEEDED,
        Outcome.SUCCESS,
        user=user,
        detail=_sign_in_detail(passkey=passkey.name),
    )
    return open_session(db, response, user, settings, now)
