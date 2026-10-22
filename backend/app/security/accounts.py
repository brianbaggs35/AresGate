"""Usernames, and finding the account."""

import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User

_VALID_USERNAME = re.compile(r"[a-z0-9._@-]{3,64}")


class UsernameError(ValueError):
    """The username breaks a rule. The message says which, and is meant to be shown."""


def normalize_username(username: str) -> str:
    """The form usernames are stored and compared in, so "Brian" and "brian" are one account."""
    return unicodedata.normalize("NFKC", username).strip().lower()


def check_username(username: str) -> None:
    """Raises UsernameError unless an already normalized username is acceptable."""
    if not _VALID_USERNAME.fullmatch(username):
        raise UsernameError(
            "Use 3 to 64 letters, numbers, dots, dashes, underscores or @ signs for the username."
        )


def find_user(db: Session, username: str) -> User | None:
    return db.scalar(select(User).where(User.username == username))


def any_user_exists(db: Session) -> bool:
    return db.scalar(select(User.id).limit(1)) is not None
