"""The second step of signing in: a code from an authenticator app, or a recovery code.

An account turns it on in two steps, so a typing mistake can't lock it out: AresGate makes a key
and shows it, and the account only counts as protected once a code from the app proves the app
has it. The key is sealed with the app secret key (see ``vault``). Turning it on also makes ten
recovery codes, for when the phone is lost.

When it is on, the password alone no longer signs in. It earns a challenge, good for a few
minutes, which the second step trades for the session once it has a right code.
"""

import hmac
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import RecoveryCode, TotpCredential, User
from app.security import recovery_codes, totp, vault

ISSUER = "AresGate"
CHALLENGE_VALID = timedelta(minutes=5)
_KEY_PURPOSE = "authenticator-key"
_CHALLENGE_PURPOSE = "sign-in-challenge"


class Method(StrEnum):
    AUTHENTICATOR = "authenticator"
    RECOVERY_CODE = "recovery_code"


@dataclass(frozen=True)
class Accepted:
    method: Method
    # How many recovery codes are left, when one was just used.
    recovery_codes_left: int | None = None


class AlreadyEnabled(Exception):
    """The account already has an authenticator app."""


class NotEnrolling(Exception):
    """There is no authenticator app being added."""


def is_enabled(db: Session, user_id: UUID) -> bool:
    return (
        db.scalar(
            select(TotpCredential.user_id).where(
                TotpCredential.user_id == user_id, TotpCredential.confirmed_at.is_not(None)
            )
        )
        is not None
    )


def recovery_codes_left(db: Session, user_id: UUID) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(RecoveryCode)
            .where(RecoveryCode.user_id == user_id, RecoveryCode.used_at.is_(None))
        )
        or 0
    )


def _secret(settings: Settings, credential: TotpCredential) -> str:
    return vault.unseal(
        settings, _KEY_PURPOSE, credential.secret_sealed, str(credential.user_id)
    ).decode()


def start_enrollment(db: Session, settings: Settings, user: User, now: datetime) -> tuple[str, str]:
    """Makes a key for an authenticator app, and returns it with the address a QR code carries.
    Starting again before a code has been confirmed replaces the key. The caller commits."""
    credential = db.get(TotpCredential, user.id)
    if credential is not None and credential.confirmed_at is not None:
        raise AlreadyEnabled
    secret = totp.new_secret()
    sealed = vault.seal(settings, _KEY_PURPOSE, secret.encode(), str(user.id))
    if credential is None:
        db.add(TotpCredential(user_id=user.id, secret_sealed=sealed, created_at=now))
    else:
        credential.secret_sealed = sealed
        credential.created_at = now
    return secret, totp.provisioning_uri(secret, user.username, ISSUER)


def confirm_enrollment(
    db: Session, settings: Settings, user: User, code: str, now: datetime
) -> list[str] | None:
    """Turns the app on if the code from it is right, and returns the recovery codes, which
    are shown once. None if the code is wrong. The caller commits."""
    credential = db.execute(
        select(TotpCredential)
        .where(TotpCredential.user_id == user.id, TotpCredential.confirmed_at.is_(None))
        .with_for_update()
    ).scalar_one_or_none()
    if credential is None:
        raise NotEnrolling
    period = totp.verify(_secret(settings, credential), code, now)
    if period is None:
        return None
    credential.confirmed_at = now
    credential.last_used_period = period
    return replace_recovery_codes(db, settings, user.id, now)


def replace_recovery_codes(
    db: Session, settings: Settings, user_id: UUID, now: datetime
) -> list[str]:
    """Makes a new set of recovery codes, which end the old ones. The caller commits."""
    db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user_id))
    codes = [recovery_codes.generate() for _ in range(recovery_codes.COUNT)]
    db.add_all(
        RecoveryCode(
            user_id=user_id,
            code_hash=recovery_codes.hash_code(settings, user_id, code),
            created_at=now,
        )
        for code in codes
    )
    return codes


def accept_code(
    db: Session, settings: Settings, user_id: UUID, code: str, now: datetime
) -> Accepted | None:
    """Checks a code from the authenticator app or a recovery code, and uses it up so it can't
    be used again. None if it isn't right. The caller commits."""
    if totp.looks_like_code(code):
        credential = db.execute(
            select(TotpCredential)
            .where(TotpCredential.user_id == user_id, TotpCredential.confirmed_at.is_not(None))
            .with_for_update()
        ).scalar_one_or_none()
        if credential is None:
            return None
        period = totp.verify(
            _secret(settings, credential), code, now, after=credential.last_used_period
        )
        if period is None:
            return None
        credential.last_used_period = period
        return Accepted(Method.AUTHENTICATOR)
    if recovery_codes.looks_like_code(code):
        recovery = db.execute(
            select(RecoveryCode)
            .where(
                RecoveryCode.user_id == user_id,
                RecoveryCode.code_hash == recovery_codes.hash_code(settings, user_id, code),
                RecoveryCode.used_at.is_(None),
            )
            .with_for_update()
        ).scalar_one_or_none()
        if recovery is None:
            return None
        recovery.used_at = now
        db.flush()
        return Accepted(Method.RECOVERY_CODE, recovery_codes_left(db, user_id))
    return None


def disable(db: Session, user_id: UUID) -> None:
    """Takes the authenticator app and the recovery codes off the account. The caller commits."""
    db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user_id))
    db.execute(delete(TotpCredential).where(TotpCredential.user_id == user_id))


def reseal_keys(db: Session, old: Settings, new: Settings) -> int:
    """Seals every account's authenticator key again with a new app secret key, and returns how
    many there were. Raises ``VaultError`` naming the account whose key can't be opened with the
    old one. The caller commits."""
    rows = db.execute(
        select(TotpCredential, User.username).join(User, User.id == TotpCredential.user_id)
    ).all()
    for credential, username in rows:
        belongs_to = str(credential.user_id)
        try:
            key = vault.unseal(old, _KEY_PURPOSE, credential.secret_sealed, belongs_to)
        except vault.VaultError as error:
            raise vault.VaultError(f"The authenticator key of {username}: {error}") from error
        credential.secret_sealed = vault.seal(new, _KEY_PURPOSE, key, belongs_to)
    return len(rows)


def discard_recovery_codes(db: Session) -> int:
    """Removes every account's recovery codes, and returns how many were left. They are kept as
    hashes made with the app secret key, which can't be made again under a new key without the
    codes themselves, so a new key ends them. The caller commits."""
    return db.connection().execute(delete(RecoveryCode)).rowcount


def make_challenge(settings: Settings, user_id: UUID, now: datetime) -> str:
    """What a right password earns on an account with an authenticator app: proof it was
    given, which only this install can have made, and which stops working after a few minutes."""
    body = f"{user_id}.{int((now + CHALLENGE_VALID).timestamp())}"
    return f"{body}.{vault.keyed_hash(settings, _CHALLENGE_PURPOSE, body)}"


def read_challenge(settings: Settings, challenge: str, now: datetime) -> UUID | None:
    """The account a challenge was made for, or None if it is forged, damaged or too old."""
    parts = challenge.split(".")
    if len(parts) != 3:
        return None
    account, expires, signature = parts
    expected = vault.keyed_hash(settings, _CHALLENGE_PURPOSE, f"{account}.{expires}")
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        user_id = UUID(account)
        expiry = int(expires)
    except ValueError:
        return None
    return user_id if now.timestamp() < expiry else None
