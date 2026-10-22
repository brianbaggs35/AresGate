"""What the API's routes share: refusing changes that don't come from AresGate's own pages,
finding who is signed in, and the address a request came from."""

import secrets
from dataclasses import dataclass
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app import audit
from app.config import Settings, get_settings
from app.db import get_session
from app.models import User, UserSession, utcnow
from app.security import sessions

Db = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
# The web app's dev server and the end-to-end tests serve it over plain HTTP on this computer.
_DEV_HOSTS = frozenset({"localhost", "127.0.0.1"})


def _is_dev_server_origin(origin: str) -> bool:
    """Whether the origin is plain HTTP on this computer, with or without a port."""
    try:
        parts = urlsplit(origin)
        port = parts.port
    except ValueError:
        return False
    host = parts.hostname
    expected = host if port is None else f"{host}:{port}"
    return (
        parts.scheme == "http"
        and host in _DEV_HOSTS
        and parts.netloc == expected
        and origin == f"{parts.scheme}://{parts.netloc}"
    )


def require_same_origin(request: Request, settings: SettingsDep) -> None:
    """Refuses a change unless the browser says it came from AresGate's own address. Browsers
    always say so on a change, and a page on another website can't make them say otherwise."""
    if request.method in SAFE_METHODS:
        return
    origin = request.headers.get("origin", "")
    if origin == settings.public_origin:
        return
    if not settings.is_production and _is_dev_server_origin(origin):
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "The request didn't come from AresGate.")


def client_address(request: Request) -> str:
    """Where the request came from. Behind nginx, uvicorn has already swapped in the address
    nginx saw, as long as the request came from nginx."""
    return request.client.host if request.client else "unknown"


def record_audit(
    db: Session,
    request: Request,
    action: audit.Action,
    outcome: audit.Outcome,
    *,
    user: User | None = None,
    detail: audit.Detail | None = None,
) -> None:
    """Adds an audit event for the request: who it was about (if anyone), where it came from and
    what the client called itself. The caller commits."""
    audit.record(
        db,
        action,
        outcome,
        user_id=user.id if user else None,
        username=user.username if user else None,
        address=client_address(request),
        user_agent=request.headers.get("user-agent"),
        detail=detail,
    )


@dataclass(frozen=True)
class SignedIn:
    user: User
    session: UserSession


def signed_in(
    request: Request,
    db: Db,
    settings: SettingsDep,
    token: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> SignedIn:
    """Who is signed in. A change also has to carry the sign-in's security token, which only
    AresGate's own pages are given."""
    row = sessions.find(db, token, settings, utcnow()) if token else None
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "You're not signed in.")
    if request.method not in SAFE_METHODS and not (
        csrf_token and secrets.compare_digest(csrf_token.encode(), row.csrf_token.encode())
    ):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "The security token for this sign-in is missing."
        )
    return SignedIn(user=row.user, session=row)
