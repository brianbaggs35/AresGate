"""Passkeys: signing in with the unlock a device already has, such as a fingerprint, a face or a
PIN, instead of a typed password.

The device keeps a private key for AresGate and signs a one-off challenge with it. AresGate keeps
only the matching public key, so a copy of the database lets nobody sign in. A passkey is tied
to the server name (the WebAuthn "relying party"), and a browser only offers it to a page served
from that name, which is why a look-alike site can't ask for it.

A passkey must be a discoverable credential that the device unlocks itself (user verification),
so signing in needs nothing typed, not even the username, and the passkey alone stands in for
both a password and an authenticator app. Attestation is not asked for: AresGate has no reason
to care which make of device holds the key.
"""

import struct
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any, Protocol, cast
from uuid import UUID

from fido2.server import Fido2Server
from fido2.webauthn import (
    AttestationConveyancePreference,
    AttestedCredentialData,
    AuthenticationResponse,
    AuthenticatorData,
    CredentialCreationOptions,
    CredentialRequestOptions,
    PublicKeyCredentialParameters,
    PublicKeyCredentialRpEntity,
    PublicKeyCredentialType,
    PublicKeyCredentialUserEntity,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Passkey, PasskeyChallenge, User
from app.security.origins import is_own_origin

CHALLENGE_LIFETIME = timedelta(minutes=5)
# Enough for every device someone owns, and a bound on what one account can pile up.
MOST_PER_ACCOUNT = 20

REGISTER = "register"
SIGN_IN = "sign_in"

# ES256 (the one nearly every device uses), EdDSA, and RS256 (which Windows Hello still uses).
_ALGORITHMS = (-7, -8, -257)
# What the library raises for an answer that is missing parts, is cut short or has the wrong
# kind of value. It asserts, rather than raises, that a new passkey's answer carries the key.
_MALFORMED = (
    ValueError,
    KeyError,
    TypeError,
    AttributeError,
    AssertionError,
    IndexError,
    OverflowError,
    struct.error,
)


class ChallengeGone(Exception):
    """The challenge has timed out, was never given or has already been used."""


class Rejected(Exception):
    """The device's answer doesn't prove anything. ``reason`` is a short code for the audit
    log, and ``user_id`` is the account the passkey belongs to, when it got as far as finding
    one. Whoever answered is told no more than that it didn't work."""

    def __init__(self, reason: str, user_id: UUID | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.user_id = user_id


class TooMany(Exception):
    """The account already has as many passkeys as it can."""


class AlreadyRegistered(Exception):
    """That passkey is already registered."""


class _Server(Protocol):
    """The parts of ``Fido2Server`` used here, with the types its ``state`` lacks."""

    def register_begin(
        self,
        user: PublicKeyCredentialUserEntity,
        credentials: Sequence[AttestedCredentialData],
        resident_key_requirement: ResidentKeyRequirement,
        user_verification: UserVerificationRequirement,
    ) -> tuple[CredentialCreationOptions, dict[str, Any]]: ...

    def register_complete(
        self, state: Mapping[str, Any], response: Mapping[str, Any]
    ) -> AuthenticatorData: ...

    def authenticate_begin(
        self, user_verification: UserVerificationRequirement
    ) -> tuple[CredentialRequestOptions, dict[str, Any]]: ...

    def authenticate_complete(
        self,
        state: Mapping[str, Any],
        credentials: Sequence[AttestedCredentialData],
        response: Mapping[str, Any],
    ) -> AttestedCredentialData: ...


def _server(settings: Settings) -> _Server:
    server = Fido2Server(
        PublicKeyCredentialRpEntity(id=settings.server_name, name="AresGate"),
        attestation=AttestationConveyancePreference.NONE,
        verify_origin=lambda origin: is_own_origin(settings, origin),
    )
    server.allowed_algorithms = [
        PublicKeyCredentialParameters(type=PublicKeyCredentialType.PUBLIC_KEY, alg=alg)
        for alg in _ALGORITHMS
    ]
    return cast("_Server", server)


def _keep(
    db: Session, purpose: str, user_id: UUID | None, state: Mapping[str, Any], now: datetime
) -> UUID:
    """Remembers a challenge until it is answered, and forgets the ones that ran out."""
    db.execute(delete(PasskeyChallenge).where(PasskeyChallenge.expires_at <= now))
    if user_id is not None:
        # Starting again replaces the attempt before it.
        db.execute(
            delete(PasskeyChallenge).where(
                PasskeyChallenge.user_id == user_id, PasskeyChallenge.purpose == purpose
            )
        )
    row = PasskeyChallenge(
        purpose=purpose,
        user_id=user_id,
        challenge=state["challenge"],
        expires_at=now + CHALLENGE_LIFETIME,
    )
    db.add(row)
    db.flush()
    return row.id


def _take(
    db: Session, challenge_id: UUID, purpose: str, user_id: UUID | None, now: datetime
) -> str:
    """The challenge, used up: an answer gets one try, right or wrong, so a recorded answer
    can't be sent again. The caller commits, which has to happen even when this raises."""
    row = db.execute(
        select(PasskeyChallenge).where(PasskeyChallenge.id == challenge_id).with_for_update()
    ).scalar_one_or_none()
    if row is None:
        raise ChallengeGone
    db.delete(row)
    if row.expires_at <= now or row.purpose != purpose or row.user_id != user_id:
        raise ChallengeGone
    return row.challenge


def _state(challenge: str) -> dict[str, Any]:
    return {"challenge": challenge, "user_verification": UserVerificationRequirement.REQUIRED}


def _for_browser(options: Mapping[str, Any]) -> dict[str, Any]:
    """The options as the browser's ``parseCreationOptionsFromJSON`` and
    ``parseRequestOptionsFromJSON`` take them."""
    return dict(options["publicKey"])


def count(db: Session, user_id: UUID) -> int:
    return (
        db.scalar(select(func.count()).select_from(Passkey).where(Passkey.user_id == user_id)) or 0
    )


def for_user(db: Session, user_id: UUID) -> list[Passkey]:
    """The account's passkeys, oldest first."""
    return list(
        db.scalars(select(Passkey).where(Passkey.user_id == user_id).order_by(Passkey.created_at))
    )


def remove(db: Session, user_id: UUID, passkey_id: UUID) -> Passkey | None:
    """Forgets a passkey, and returns it, or None if the account has no such passkey. The
    device keeps its copy, which no longer opens anything. The caller commits."""
    row = db.scalar(select(Passkey).where(Passkey.id == passkey_id, Passkey.user_id == user_id))
    if row is not None:
        db.delete(row)
    return row


def begin_registration(
    db: Session, settings: Settings, user: User, now: datetime
) -> tuple[UUID, dict[str, Any]]:
    """What a device is asked to make a passkey from, and the id to answer it by. Passkeys the
    account already has are named, so a device doesn't make a second one. The caller commits."""
    if count(db, user.id) >= MOST_PER_ACCOUNT:
        raise TooMany
    options, state = _server(settings).register_begin(
        PublicKeyCredentialUserEntity(
            id=user.id.bytes, name=user.username, display_name=user.username
        ),
        [AttestedCredentialData(passkey.credential_data) for passkey in for_user(db, user.id)],
        resident_key_requirement=ResidentKeyRequirement.REQUIRED,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    return _keep(db, REGISTER, user.id, state, now), _for_browser(options)


def finish_registration(
    db: Session,
    settings: Settings,
    user: User,
    challenge_id: UUID,
    credential: Mapping[str, Any],
    name: str,
    now: datetime,
) -> Passkey:
    """Keeps the passkey a device made, if it answers the challenge. The caller commits, which
    it has to do when this raises ``ChallengeGone`` or ``Rejected`` too."""
    challenge = _take(db, challenge_id, REGISTER, user.id, now)
    try:
        made = _server(settings).register_complete(_state(challenge), credential).credential_data
    except _MALFORMED as error:
        raise Rejected("bad_response") from error
    if made is None or type(made.public_key).ALGORITHM not in _ALGORITHMS:
        raise Rejected("unsupported_key")
    if db.scalar(select(Passkey.id).where(Passkey.credential_id == made.credential_id)):
        raise AlreadyRegistered
    passkey = Passkey(
        user_id=user.id,
        name=name,
        credential_id=made.credential_id,
        credential_data=bytes(made),
        sign_count=0,
        created_at=now,
    )
    db.add(passkey)
    return passkey


def begin_sign_in(db: Session, settings: Settings, now: datetime) -> tuple[UUID, dict[str, Any]]:
    """What a device is asked to sign, and the id to answer it by. No account is named: the
    device offers its passkeys for AresGate and the answer says which. The caller commits."""
    options, state = _server(settings).authenticate_begin(
        user_verification=UserVerificationRequirement.REQUIRED
    )
    return _keep(db, SIGN_IN, None, state, now), _for_browser(options)


def finish_sign_in(
    db: Session,
    settings: Settings,
    challenge_id: UUID,
    credential: Mapping[str, Any],
    now: datetime,
) -> Passkey:
    """The passkey a device proved it holds, which says whose it is. The caller commits, which
    it has to do when this raises ``ChallengeGone`` or ``Rejected`` too."""
    challenge = _take(db, challenge_id, SIGN_IN, None, now)
    passkey = None
    try:
        answer = AuthenticationResponse.from_dict(credential)
        passkey = db.scalar(
            select(Passkey).where(Passkey.credential_id == answer.raw_id).with_for_update()
        )
        if passkey is None:
            raise Rejected("unknown_passkey")
        # A device that says whose passkey it is must say the account this one belongs to.
        handle = answer.response.user_handle
        if handle and handle != passkey.user_id.bytes:
            raise Rejected("wrong_account", passkey.user_id)
        _server(settings).authenticate_complete(
            _state(challenge), [AttestedCredentialData(passkey.credential_data)], credential
        )
        counter = answer.response.authenticator_data.counter
    except _MALFORMED as error:
        raise Rejected("bad_response", passkey.user_id if passkey else None) from error
    # A device's count only goes up. One that hasn't moved on, other than devices that don't
    # count at all, is a copy of the passkey being used alongside the original.
    if (counter or passkey.sign_count) and counter <= passkey.sign_count:
        raise Rejected("counter_went_back", passkey.user_id)
    passkey.sign_count = counter
    passkey.last_used_at = now
    return passkey
