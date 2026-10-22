"""Commands for whoever runs AresGate, for when the web app can't help.

Run them inside the container as the ``aresgate`` user, which is the one the database lets in.
``make two-factor-off ACCOUNT=USERNAME`` does this one:

    docker compose exec -u aresgate -w /app/backend aresgate \\
        python -m app.cli disable-two-factor USERNAME
"""

import argparse
import sys
from collections.abc import Sequence

from sqlalchemy import delete

from app import audit
from app.audit import Action, Outcome
from app.db import get_sessionmaker
from app.models import UserSession
from app.security import two_factor
from app.security.accounts import find_user, normalize_username


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
    arguments = parser.parse_args(argv)
    return disable_two_factor(arguments.username)


if __name__ == "__main__":
    sys.exit(main())
