"""Adding an authenticator app to the account, and taking it off again."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth import current_lockouts, too_many_attempts
from app.api.deps import Db, SettingsDep, SignedIn, client_address, record_audit, signed_in
from app.audit import Action, Detail, Outcome
from app.config import Settings
from app.models import utcnow
from app.security import passwords, throttle, two_factor
from app.security.throttle import Scope

router = APIRouter(prefix="/auth/two-factor", tags=["auth"])


class TwoFactorStatus(BaseModel):
    enabled: bool
    recovery_codes_left: int


class Enrollment(BaseModel):
    # The key to type into an app, and the address a QR code for it carries.
    secret: str
    otpauth_uri: str


class CodeRequest(BaseModel):
    code: str = Field(max_length=64)


class DisableRequest(BaseModel):
    password: str = Field(max_length=1024)
    code: str = Field(max_length=64)


class RecoveryCodes(BaseModel):
    recovery_codes: list[str]


@router.get("")
def two_factor_status(auth: Annotated[SignedIn, Depends(signed_in)], db: Db) -> TwoFactorStatus:
    return TwoFactorStatus(
        enabled=two_factor.is_enabled(db, auth.user.id),
        recovery_codes_left=two_factor.recovery_codes_left(db, auth.user.id),
    )


@router.post("/enroll", status_code=status.HTTP_201_CREATED)
def start_enrollment(
    auth: Annotated[SignedIn, Depends(signed_in)], db: Db, settings: SettingsDep
) -> Enrollment:
    """Makes a key for an authenticator app. It only counts once ``/confirm`` has a code from
    the app."""
    try:
        secret, uri = two_factor.start_enrollment(db, settings, auth.user, utcnow())
    except two_factor.AlreadyEnabled as error:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "An authenticator app is already set up. Turn it off before adding another.",
        ) from error
    db.commit()
    return Enrollment(secret=secret, otpauth_uri=uri)


@router.post("/confirm")
def confirm_enrollment(
    body: CodeRequest,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
    settings: SettingsDep,
) -> RecoveryCodes:
    """Turns the authenticator app on, if the code from it is right. The recovery codes in the
    answer are the only time they are shown."""
    try:
        codes = two_factor.confirm_enrollment(db, settings, auth.user, body.code, utcnow())
    except two_factor.NotEnrolling as error:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Start adding an authenticator app first."
        ) from error
    if codes is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "That code isn't right. Check that the clock on your phone is correct, and try the "
            "next code.",
        )
    record_audit(db, request, Action.TWO_FACTOR_ENABLED, Outcome.SUCCESS, user=auth.user)
    db.commit()
    return RecoveryCodes(recovery_codes=codes)


def _require_code(
    db: Session,
    settings: Settings,
    request: Request,
    auth: SignedIn,
    code: str,
    *,
    password: str | None = None,
    purpose: str,
) -> None:
    """Refuses unless the code (and the password, where asked for) is right. Guesses at them
    count towards the same lockout as at the sign-in page, since a stolen sign-in is the case
    these checks are for."""
    now = utcnow()
    address = client_address(request)
    username = auth.user.username
    if waits := current_lockouts(db, address, username, now):
        raise too_many_attempts(max(waits))

    # The code is only used up if the password was right, so a typing mistake in the password
    # doesn't cost the person the code they have.
    if (
        password is None or passwords.verify_password(password, auth.user.password_hash)
    ) and two_factor.accept_code(db, settings, auth.user.id, code, now) is not None:
        return
    throttle.record_failure(db, Scope.ADDRESS, address, now)
    throttle.record_failure(db, Scope.ACCOUNT, username, now)
    detail: Detail = {"reason": "wrong_password_or_code", "while": purpose}
    record_audit(
        db, request, Action.TWO_FACTOR_FAILED, Outcome.FAILURE, user=auth.user, detail=detail
    )
    db.commit()
    # Not 401, which the web app takes to mean the sign-in itself has ended.
    raise HTTPException(
        status.HTTP_403_FORBIDDEN,
        "That isn't right." if password is None else "The password or the code isn't right.",
    )


@router.post("/recovery-codes")
def make_recovery_codes(
    body: CodeRequest,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
    settings: SettingsDep,
) -> RecoveryCodes:
    """Makes a new set of recovery codes, which end the old ones. It needs a current code, so
    a sign-in left open on a borrowed computer can't make them."""
    if not two_factor.is_enabled(db, auth.user.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "There is no authenticator app set up.")
    _require_code(db, settings, request, auth, body.code, purpose="new_recovery_codes")
    codes = two_factor.replace_recovery_codes(db, settings, auth.user.id, utcnow())
    record_audit(db, request, Action.RECOVERY_CODES_CREATED, Outcome.SUCCESS, user=auth.user)
    db.commit()
    return RecoveryCodes(recovery_codes=codes)


@router.post("/disable", status_code=status.HTTP_204_NO_CONTENT)
def disable(
    body: DisableRequest,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
    settings: SettingsDep,
) -> None:
    """Turns the authenticator app off. It needs the password and a current code."""
    if not two_factor.is_enabled(db, auth.user.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "There is no authenticator app set up.")
    _require_code(
        db, settings, request, auth, body.code, password=body.password, purpose="turning_off"
    )
    two_factor.disable(db, auth.user.id)
    record_audit(db, request, Action.TWO_FACTOR_DISABLED, Outcome.SUCCESS, user=auth.user)
    db.commit()
