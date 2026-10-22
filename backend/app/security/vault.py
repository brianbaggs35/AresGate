"""Encryption and keyed hashes made from the app secret key.

What AresGate must read back, such as an authenticator app's key, is sealed with AES-256-GCM, so
a copy of the database on its own reveals none of it. What it only has to recognise, such as a
recovery code, is kept as a keyed hash, so a copy of the database can't be used to guess it
offline either.

Each purpose gets a key of its own, made from the secret key with HKDF, so a sealed value can't
be opened as another kind of thing. A sealed value also names what it belongs to (an account's
id, say), and can't be moved to another row. ``v1`` in front of it says how it was made, so
the scheme can change later without losing what is already stored.
"""

import base64
import hashlib
import hmac
import secrets
from functools import lru_cache

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import Settings
from app.secret_key import load_secret_key

VERSION = "v1"
_NONCE_BYTES = 12


class VaultError(ValueError):
    """A sealed value that can't be opened: it was made with another key, for another purpose or
    row, or it has been altered."""


@lru_cache(maxsize=32)
def _derive(secret: str, purpose: str) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=f"aresgate/{purpose}/{VERSION}".encode(),
    ).derive(secret.encode())


def _key(settings: Settings, purpose: str) -> bytes:
    return _derive(load_secret_key(settings).get_secret_value(), purpose)


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def seal(settings: Settings, purpose: str, plaintext: bytes, belongs_to: str) -> str:
    """Encrypts ``plaintext``, which only ``unseal`` with the same purpose and ``belongs_to``
    can open. A fresh random nonce each time means sealing the same thing twice gives different
    results."""
    nonce = secrets.token_bytes(_NONCE_BYTES)
    ciphertext = AESGCM(_key(settings, purpose)).encrypt(nonce, plaintext, belongs_to.encode())
    return f"{VERSION}.{_encode(nonce)}.{_encode(ciphertext)}"


def unseal(settings: Settings, purpose: str, sealed: str, belongs_to: str) -> bytes:
    """The plaintext of a sealed value, or ``VaultError`` if it can't be opened."""
    parts = sealed.split(".")
    if len(parts) != 3 or parts[0] != VERSION:
        raise VaultError("This wasn't sealed by a scheme AresGate knows.")
    try:
        return AESGCM(_key(settings, purpose)).decrypt(
            _decode(parts[1]), _decode(parts[2]), belongs_to.encode()
        )
    except (ValueError, InvalidTag) as error:
        raise VaultError("This can't be opened with the app secret key.") from error


def keyed_hash(settings: Settings, purpose: str, message: str) -> str:
    """A hash of ``message`` that can't be worked out without the secret key. The same message
    always gives the same result, which is what lets it be looked up."""
    return hmac.new(_key(settings, purpose), message.encode(), hashlib.sha256).hexdigest()
