"""A passkey made of software, for tests: it answers a challenge the way a real device does, so
the server's checks can be tried without a browser. Each keyword says one thing to get wrong."""

# The library's constructors for these messages take untyped extras.
# pyright: reportUnknownMemberType=false

import hashlib
import secrets
from collections.abc import Callable
from typing import Any, Literal

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, padding, rsa
from fido2 import cose
from fido2.utils import websafe_decode, websafe_encode
from fido2.webauthn import (
    AttestationObject,
    AttestedCredentialData,
    AuthenticatorData,
    CollectedClientData,
)

from tests.helpers import ORIGIN, SERVER_NAME

Algorithm = Literal["es256", "es384", "eddsa", "rs256"]

_UP = AuthenticatorData.FLAG.UP
_UV = AuthenticatorData.FLAG.UV
_AT = AuthenticatorData.FLAG.AT


class SoftAuthenticator:
    def __init__(self, algorithm: Algorithm = "es256") -> None:
        self.credential_id = secrets.token_bytes(32)
        self.counter = 0
        # Learned from the account the passkey was made for.
        self.user_handle: bytes | None = None
        self._sign: Callable[[bytes], bytes]
        match algorithm:
            case "es256":
                ec_key = ec.generate_private_key(ec.SECP256R1())
                self._cose = cose.ES256.from_cryptography_key(ec_key.public_key())
                self._sign = lambda message: ec_key.sign(message, ec.ECDSA(hashes.SHA256()))
            case "es384":
                ec_key = ec.generate_private_key(ec.SECP384R1())
                self._cose = cose.ES384.from_cryptography_key(ec_key.public_key())
                self._sign = lambda message: ec_key.sign(message, ec.ECDSA(hashes.SHA384()))
            case "eddsa":
                ed_key = ed25519.Ed25519PrivateKey.generate()
                self._cose = cose.EdDSA.from_cryptography_key(ed_key.public_key())
                self._sign = ed_key.sign
            case "rs256":
                rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
                self._cose = cose.RS256.from_cryptography_key(rsa_key.public_key())
                self._sign = lambda message: rsa_key.sign(
                    message, padding.PKCS1v15(), hashes.SHA256()
                )

    @property
    def id(self) -> str:
        return websafe_encode(self.credential_id)

    def register(
        self,
        options: dict[str, Any],
        *,
        origin: str = ORIGIN,
        rp_id: str = SERVER_NAME,
        type: str = "webauthn.create",
        challenge: str | None = None,
        user_present: bool = True,
        user_verified: bool = True,
        attested: bool = True,
    ) -> dict[str, Any]:
        """The answer to the options ``/api/auth/passkeys/options`` gave."""
        self.user_handle = websafe_decode(options["user"]["id"])
        client_data = CollectedClientData.create(type, challenge or options["challenge"], origin)
        credential_data = AttestedCredentialData.create(bytes(16), self.credential_id, self._cose)
        flags = (_UP if user_present else 0) | (_UV if user_verified else 0)
        auth_data = AuthenticatorData.create(
            hashlib.sha256(rp_id.encode()).digest(),
            AuthenticatorData.FLAG(flags | (_AT if attested else 0)),
            self.counter,
            bytes(credential_data) if attested else b"",
        )
        return {
            "id": self.id,
            "rawId": self.id,
            "type": "public-key",
            # Browsers add more than the server needs, which it has to put up with.
            "authenticatorAttachment": "platform",
            "response": {
                "clientDataJSON": websafe_encode(client_data),
                "attestationObject": websafe_encode(
                    bytes(AttestationObject.create("none", auth_data, {}))
                ),
                "authenticatorData": websafe_encode(bytes(auth_data)),
                "transports": ["internal"],
                "publicKeyAlgorithm": self._cose.ALGORITHM,
            },
            "clientExtensionResults": {"credProps": {"rk": True}},
        }

    def sign_in(
        self,
        options: dict[str, Any],
        *,
        origin: str = ORIGIN,
        rp_id: str = SERVER_NAME,
        type: str = "webauthn.get",
        challenge: str | None = None,
        user_present: bool = True,
        user_verified: bool = True,
        counter: int | None = None,
        user_handle: bytes | None = None,
        credential_id: bytes | None = None,
        sign_with: SoftAuthenticator | None = None,
    ) -> dict[str, Any]:
        """The answer to the options ``/api/auth/login/passkey/options`` gave. Unless told
        otherwise the count goes up by one, as a device's does."""
        self.counter = self.counter + 1 if counter is None else counter
        client_data = CollectedClientData.create(type, challenge or options["challenge"], origin)
        flags = (_UP if user_present else 0) | (_UV if user_verified else 0)
        auth_data = bytes(
            AuthenticatorData.create(
                hashlib.sha256(rp_id.encode()).digest(),
                AuthenticatorData.FLAG(flags),
                self.counter,
            )
        )
        signature = (sign_with or self)._sign(auth_data + client_data.hash)
        raw_id = websafe_encode(credential_id or self.credential_id)
        handle = user_handle if user_handle is not None else self.user_handle
        return {
            "id": raw_id,
            "rawId": raw_id,
            "type": "public-key",
            "authenticatorAttachment": "platform",
            "response": {
                "clientDataJSON": websafe_encode(client_data),
                "authenticatorData": websafe_encode(auth_data),
                "signature": websafe_encode(signature),
                **({"userHandle": websafe_encode(handle)} if handle is not None else {}),
            },
            "clientExtensionResults": {},
        }
