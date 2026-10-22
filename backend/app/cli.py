"""Commands for whoever runs AresGate, for when the web app can't help.

Run them inside the container as the ``aresgate`` user, which is the one the database lets in.
``make two-factor-off ACCOUNT=USERNAME`` does this one:

    docker compose exec -u aresgate -w /app/backend aresgate \\
        python -m app.cli disable-two-factor USERNAME

and ``make rotate-secret-key`` does the same for ``rotate-secret-key``.
"""

import argparse
import os
import secrets
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import SecretStr
from sqlalchemy import delete

from app import audit
from app.audit import Action, Outcome
from app.config import get_settings
from app.db import get_sessionmaker
from app.models import UserSession
from app.secret_key import SecretKeyError, check_length, is_container_made, load_secret_key
from app.security import rotation, two_factor
from app.security.accounts import find_user, normalize_username
from app.security.vault import VaultError


def disable_two_factor(username: str) -> int:
    """Takes the authenticator app and recovery codes off an account, for someone who has lost
    both. It also ends the account's sign-ins, and leaves an event in the audit log."""
    with get_sessionmaker()() as db:
        user = find_user(db, normalize_username(username))
        if user is None:
            print(f"There is no account called {username!r}.", file=sys.stderr)
            return 1
        if not two_factor.is_enabled(db, user.id):
            print(f"{user.username} hasn't turned on an authenticator app.", file=sys.stderr)
            return 1
        two_factor.disable(db, user.id)
        db.execute(delete(UserSession).where(UserSession.user_id == user.id))
        audit.record(
            db,
            Action.TWO_FACTOR_DISABLED,
            Outcome.SUCCESS,
            user_id=user.id,
            username=user.username,
            user_agent="command line",
            detail={"by": "command_line"},
        )
        db.commit()
    print(f"Turned off the authenticator app for {user.username}, and ended their sign-ins.")
    print("They can sign in with their password alone, and add an authenticator app again.")
    return 0


# What --new-key-file is given to read the key from standard input.
STDIN = Path("-")


def _new_key(new_key_file: Path | None, container_made: bool) -> str:
    """The key to change to: the one in the file, or a new random one when the container made
    the current key and so can keep the new one the same way."""
    if new_key_file is not None:
        source = "standard input" if new_key_file == STDIN else str(new_key_file)
        try:
            text = sys.stdin.read() if new_key_file == STDIN else new_key_file.read_text("utf-8")
        except (OSError, UnicodeError) as error:
            raise SecretKeyError(f"Can't read the new key from {source}: {error}") from error
        return check_length(text.strip(), source).get_secret_value()
    if not container_made:
        raise SecretKeyError(
            "The current key was supplied (ARESGATE_SECRET_KEY, or a file named by "
            "ARESGATE_SECRET_KEY_FILE), so this command can't keep a new one for you. Save a "
            "new key of at least 32 characters in a file and run it again with "
            "--new-key-file PATH (or - to read the key from standard input)."
        )
    return secrets.token_urlsafe(32)


def _stage(key_file: Path, key: str) -> Path:
    """Writes the new key next to the key file, ready to replace it, and fails rather than
    overwrite what an earlier rotation left behind."""
    staged = key_file.with_name(f"{key_file.name}.new")
    descriptor = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(f"{key}\n")
    return staged


def rotate_secret_key(new_key_file: Path | None) -> int:
    """Changes the app secret key, sealing everything stored with the old one again with the new.
    It is all done in one transaction, so a value that can't be opened changes nothing."""
    settings = get_settings()
    container_made = is_container_made(settings)
    try:
        old_key = load_secret_key(settings).get_secret_value()
        new_key = _new_key(new_key_file, container_made)
    except SecretKeyError as error:
        print(error, file=sys.stderr)
        return 1
    if new_key == old_key:
        print("That is the key AresGate already uses.", file=sys.stderr)
        return 1

    staged: Path | None = None
    if container_made:
        try:
            staged = _stage(settings.secret_key_file, new_key)
        except OSError as error:
            print(
                f"Can't save the new key next to {settings.secret_key_file}: {error}\n"
                f"If an earlier rotation was cut short, see 'Changing the app secret key' in "
                f"DOCS/operations.md.",
                file=sys.stderr,
            )
            return 1

    committed = False
    try:
        with get_sessionmaker()() as db:
            rotated = rotation.rotate(
                db, settings, settings.model_copy(update={"secret_key": SecretStr(new_key)})
            )
            audit.record(
                db,
                Action.KEY_ROTATED,
                Outcome.SUCCESS,
                user_agent="command line",
                detail={
                    "by": "command_line",
                    "credentials": rotated.credentials,
                    "authenticator_keys": rotated.authenticator_keys,
                    "recovery_codes_removed": rotated.recovery_codes_removed,
                },
            )
            db.commit()
            committed = True
    except VaultError as error:
        print(f"Nothing was changed. {error}", file=sys.stderr)
        return 1
    finally:
        if staged and not committed:
            staged.unlink(missing_ok=True)

    if staged:
        try:
            os.replace(staged, settings.secret_key_file)
        except OSError as error:
            print(
                f"What AresGate stores is sealed with the new key now, but it couldn't replace "
                f"{settings.secret_key_file}: {error}\nThe new key is in {staged}. Move it over "
                f"{settings.secret_key_file} before anything else.",
                file=sys.stderr,
            )
            return 1

    print(
        f"Sealed {rotated.credentials} credentials and {rotated.authenticator_keys} "
        "authenticator keys again with the new app secret key."
    )
    if rotated.recovery_codes_removed:
        print(
            f"{rotated.recovery_codes_removed} recovery codes can't be carried over to a new "
            "key, so they were removed. Make new ones on the Security page."
        )
    if staged:
        print(
            f"The new key is in {settings.secret_key_file}. Keep a copy somewhere safe, apart "
            "from the backups (make secret-key shows it)."
        )
    else:
        print(
            "Now make the new key the app secret key (ARESGATE_SECRET_KEY, or the file "
            "ARESGATE_SECRET_KEY_FILE names) and restart AresGate. Until then it can't open "
            "what it stores."
        )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli", description="Commands for whoever runs AresGate."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    disable = commands.add_parser(
        "disable-two-factor",
        help="turn off an account's authenticator app, if the phone and recovery codes are lost",
    )
    disable.add_argument("username")
    rotate = commands.add_parser(
        "rotate-secret-key",
        help="change the app secret key, and seal everything stored again with the new one",
    )
    rotate.add_argument(
        "--new-key-file",
        type=Path,
        help="a file holding the new key (- for standard input), instead of a random one",
    )
    arguments = parser.parse_args(argv)
    if arguments.command == "rotate-secret-key":
        return rotate_secret_key(arguments.new_key_file)
    return disable_two_factor(arguments.username)


if __name__ == "__main__":
    sys.exit(main())
