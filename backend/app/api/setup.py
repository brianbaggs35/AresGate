"""Creating the account, once, when AresGate is first opened."""

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app.api.auth import SessionInfo, open_session, too_many_attempts
from app.api.deps import Db, SettingsDep, client_address
from app.models import User, utcnow
from app.security import passwords, setup_code, throttle
from app.security.accounts import (
    UsernameError,
    any_user_exists,
    check_username,
    normalize_username,
)
from app.security.throttle import Scope

router = APIRouter(prefix="/setup", tags=["setup"])


class SetupStatus(BaseModel):
    setup_required: bool


class SetupRequest(BaseModel):
    code: str = Field(max_length=64)
    username: str = Field(max_length=256)
    password: str = Field(max_length=1024)


@router.get("/status")
def setup_status(db: Db) -> SetupStatus:
    """Whether the web app should show the setup page or the sign-in page."""
    return SetupStatus(setup_required=not any_user_exists(db))


@router.post("", status_code=status.HTTP_201_CREATED)
def set_up(
    body: SetupRequest, request: Request, response: Response, db: Db, settings: SettingsDep
) -> SessionInfo:
    """Creates the account and signs in, if the setup code from the log is right."""
    now = utcnow()
    address = client_address(request)
    wait = throttle.remaining_lockout(db, Scope.SETUP, address, now)
    if wait is not None:
        raise too_many_attempts(wait)

    stored_hash = setup_code.lock(db)
    if any_user_exists(db):
        raise HTTPException(status.HTTP_409_CONFLICT, "AresGate is already set up.")
    if stored_hash is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "There is no setup code. Restart AresGate and look in its log for a new one.",
        )
    if not setup_code.matches(stored_hash, body.code):
        throttle.record_failure(db, Scope.SETUP, address, now)
        db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "That setup code isn't right.")

    username = normalize_username(body.username)
    try:
        check_username(username)
        passwords.check_policy(body.password, username=username, server_name=settings.server_name)
    except (UsernameError, passwords.PasswordPolicyError) as error:
        # The code stays good, so they can try again.
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error

    user = User(username=username, password_hash=passwords.hash_password(body.password))
    db.add(user)
    setup_code.consume(db)
    throttle.clear(db, Scope.SETUP, address)
    return open_session(db, response, user, settings, now)
