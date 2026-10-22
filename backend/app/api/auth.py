"""Signing in and out."""

import math
from datetime import datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app.api.deps import Db, SettingsDep, SignedIn, client_address, record_audit, signed_in
from app.audit import Action, Detail, Outcome
from app.config import Settings
from app.models import User, utcnow
from app.security import passwords, sessions, throttle, two_factor
from app.security.accounts import find_user, normalize_username
from app.security.throttle import Scope

router = APIRouter(prefix="/auth", tags=["auth"])


class SessionInfo(BaseModel):
    username: str
    # Sent back in the X-CSRF-Token header with every change.
    csrf_token: str
    expires_at: datetime


class LoginRequest(BaseModel):
    username: str = Field(max_length=256)
    password: str = Field(max_length=1024)


class TwoFactorChallenge(BaseModel):
    """What a right password earns on an account that has an authenticator app: not a sign-in
    yet, but a challenge to send back with a code from the app or a recovery code."""

    two_factor_required: Literal[True] = True
    challenge: str


class TwoFactorLoginRequest(BaseModel):
    challenge: str = Field(max_length=512)
    code: str = Field(max_length=64)


def too_many_attempts(wait: timedelta) -> HTTPException:
    seconds = math.ceil(wait.total_seconds())
    minutes = math.ceil(seconds / 60)
    return HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS,
        f"Too many attempts. Try again in {minutes} minute{'' if minutes == 1 else 's'}.",
        headers={"Retry-After": str(seconds)},
    )


def current_lockouts(db: Db, address: str, username: str, now: datetime) -> list[timedelta]:
    """How long each of the address and the account is still locked, for those that are."""
    return [
        wait
        for scope, value in ((Scope.ADDRESS, address), (Scope.ACCOUNT, username))
        if (wait := throttle.remaining_lockout(db, scope, value, now))
    ]


def open_session(
    db: Db, response: Response, user: User, settings: Settings, now: datetime
) -> SessionInfo:
    """Signs the user in: records the session, commits, and sets its cookie."""
    sessions.purge_ended(db, settings, now)
    row, token = sessions.start(db, user, settings, now)
    db.commit()
    # No Max-Age, so the browser forgets it when it closes. The __Host- prefix makes browsers
    # accept it only from this exact host, over HTTPS, for the whole site.
    response.set_cookie(
        sessions.COOKIE_NAME,
        token,
        httponly=True,
        secure=True,
        samesite="strict",
        path="/",
    )
    return SessionInfo(
        username=user.username,
        csrf_token=row.csrf_token,
        expires_at=sessions.expires_at(row, settings),
    )


@router.post("/login")
def log_in(
    body: LoginRequest, request: Request, response: Response, db: Db, settings: SettingsDep
) -> SessionInfo | TwoFactorChallenge:
    now = utcnow()
    address = client_address(request)
    username = normalize_username(body.username)

    if waits := current_lockouts(db, address, username, now):
        raise too_many_attempts(max(waits))

    user = find_user(db, username)
    # The same work whether or not the username is an account.
    password_ok = passwords.verify_password(body.password, user.password_hash if user else None)
    if user is None or not password_ok:
        throttle.record_failure(db, Scope.ADDRESS, address, now)
        throttle.record_failure(db, Scope.ACCOUNT, username, now)
        # A wrong name isn't kept, since people sometimes type their password where it goes.
        detail: Detail = {"reason": "wrong_password" if user else "unknown_account"}
        if waits := current_lockouts(db, address, username, now):
            detail = {**detail, "locked_for_seconds": math.ceil(max(waits).total_seconds())}
        record_audit(db, request, Action.LOGIN_FAILED, Outcome.FAILURE, user=user, detail=detail)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect username or password.")

    if passwords.needs_rehash(user.password_hash):
        user.password_hash = passwords.hash_password(body.password)
    if two_factor.is_enabled(db, user.id):
        # The wrong guesses stay counted until the second step is right too, so a password that
        # has been found out can't be used to wipe them.
        db.commit()
        return TwoFactorChallenge(challenge=two_factor.make_challenge(settings, user.id, now))
    throttle.clear(db, Scope.ADDRESS, address)
    throttle.clear(db, Scope.ACCOUNT, username)
    record_audit(db, request, Action.LOGIN_SUCCEEDED, Outcome.SUCCESS, user=user)
    return open_session(db, response, user, settings, now)


@router.post("/login/two-factor")
def log_in_with_second_step(
    body: TwoFactorLoginRequest,
    request: Request,
    response: Response,
    db: Db,
    settings: SettingsDep,
) -> SessionInfo:
    """The second step of signing in to an account with an authenticator app."""
    now = utcnow()
    address = client_address(request)
    user_id = two_factor.read_challenge(settings, body.challenge, now)
    user = db.get(User, user_id) if user_id else None
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Your sign-in timed out. Enter your username and password again.",
        )

    if waits := current_lockouts(db, address, user.username, now):
        raise too_many_attempts(max(waits))

    accepted = two_factor.accept_code(db, settings, user.id, body.code, now)
    if accepted is None:
        throttle.record_failure(db, Scope.ADDRESS, address, now)
        throttle.record_failure(db, Scope.ACCOUNT, user.username, now)
        detail: Detail = {"reason": "wrong_code"}
        if waits := current_lockouts(db, address, user.username, now):
            detail = {**detail, "locked_for_seconds": math.ceil(max(waits).total_seconds())}
        record_audit(
            db, request, Action.TWO_FACTOR_FAILED, Outcome.FAILURE, user=user, detail=detail
        )
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "That code isn't right.")

    throttle.clear(db, Scope.ADDRESS, address)
    throttle.clear(db, Scope.ACCOUNT, user.username)
    detail = {"second_factor": accepted.method.value}
    if accepted.recovery_codes_left is not None:
        detail = {**detail, "recovery_codes_left": accepted.recovery_codes_left}
    record_audit(db, request, Action.LOGIN_SUCCEEDED, Outcome.SUCCESS, user=user, detail=detail)
    return open_session(db, response, user, settings, now)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def log_out(
    auth: Annotated[SignedIn, Depends(signed_in)], request: Request, response: Response, db: Db
) -> None:
    record_audit(db, request, Action.LOGOUT, Outcome.SUCCESS, user=auth.user)
    sessions.end(db, auth.session)
    response.delete_cookie(
        sessions.COOKIE_NAME, httponly=True, secure=True, samesite="strict", path="/"
    )


@router.get("/session")
def current_session(
    auth: Annotated[SignedIn, Depends(signed_in)], settings: SettingsDep
) -> SessionInfo:
    return SessionInfo(
        username=auth.user.username,
        csrf_token=auth.session.csrf_token,
        expires_at=sessions.expires_at(auth.session, settings),
    )
