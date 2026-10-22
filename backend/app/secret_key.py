"""The app secret key, which encrypts what AresGate stores, such as integration credentials and
authenticator-app keys, so a copy of the database on its own reveals none of it.

It comes from ``ARESGATE_SECRET_KEY`` when that is set. Otherwise it is read from the file named
by ``ARESGATE_SECRET_KEY_FILE``, which is where the container keeps the key it makes on its first
start and where a Docker secret is mounted. A key shorter than ``MIN_LENGTH`` is refused, and
the API won't start without one.
"""

import sys

from pydantic import SecretStr

from app.config import DEFAULT_SECRET_KEY_FILE, Settings, get_settings

MIN_LENGTH = 32


class SecretKeyError(RuntimeError):
    """The app secret key is missing or unusable."""


def check_length(key: str, source: str) -> SecretStr:
    """The key, or ``SecretKeyError`` if it is too short to use."""
    if len(key) < MIN_LENGTH:
        raise SecretKeyError(
            f"The app secret key from {source} has {len(key)} characters, "
            f"but it needs at least {MIN_LENGTH}."
        )
    return SecretStr(key)


def load_secret_key(settings: Settings) -> SecretStr:
    """The key to encrypt with, or ``SecretKeyError`` saying what to fix."""
    supplied = settings.secret_key.get_secret_value() if settings.secret_key else ""
    if supplied.strip():
        source, key = "ARESGATE_SECRET_KEY", supplied.strip()
    else:
        source = str(settings.secret_key_file)
        try:
            key = settings.secret_key_file.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError) as error:
            raise SecretKeyError(
                f"There is no app secret key. Set ARESGATE_SECRET_KEY, or put the key in {source} "
                f"(ARESGATE_SECRET_KEY_FILE changes where it is looked for): {error}"
            ) from error
    return check_length(key, source)


def is_container_made(settings: Settings) -> bool:
    """Whether the key is the one the container made in its data volume, rather than one that
    was supplied. Only that one can be replaced without touching how AresGate is started."""
    supplied = settings.secret_key is not None and settings.secret_key.get_secret_value().strip()
    return not supplied and settings.secret_key_file == DEFAULT_SECRET_KEY_FILE


def check_or_exit() -> None:
    """For ``docker/start-api.sh``: stop with a plain message, rather than a traceback from
    every worker, when there is no usable key."""
    try:
        load_secret_key(get_settings())
    except SecretKeyError as error:
        sys.exit(f"aresgate: {error}")
