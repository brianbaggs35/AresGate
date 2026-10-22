"""Password rules and Argon2id hashing.

The rules follow NIST SP 800-63B: length matters and composition rules don't, so there is no
demand for capitals or symbols. A password is refused when it is short, when it is one of the
passwords everyone tries first, or when it is made of something an attacker would guess first
(the username, the server's name, "aresgate", a run like ``abcdefghijkl``). Nothing is sent to
a website to check a password against known breaches: this server may have no internet.
"""

import unicodedata
from functools import cache
from itertools import pairwise

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

MIN_LENGTH = 12
MAX_LENGTH = 128

# Argon2id with argon2-cffi's defaults, which are RFC 9106's low-memory recommendation. Tests
# swap in a cheaper one so they don't each spend a tenth of a second hashing.
hasher = PasswordHasher()

# The most common passwords of 12 or more characters, in the shape _squash gives them.
_COMMON = frozenset(
    {
        "123456789012",
        "1234567890123",
        "12345678901234",
        "111111111111",
        "000000000000",
        "password1234",
        "password12345",
        "password123456",
        "passw0rd1234",
        "passwordpassword",
        "qwertyuiop12",
        "qwertyuiopasdf",
        "qwerty123456",
        "qwertyuiop123",
        "1q2w3e4r5t6y",
        "1qaz2wsx3edc",
        "zaq12wsxcde3",
        "iloveyou1234",
        "iloveyou12345",
        "letmein12345",
        "welcome12345",
        "administrator",
        "adminadmin123",
        "changeme1234",
        "changemenow",
        "trustno1trustno1",
        "abc123abc123",
        "abcd1234abcd",
        "football1234",
        "baseball1234",
        "monkey123456",
        "dragon123456",
        "master123456",
        "superman1234",
        "starwars1234",
        "princess1234",
        "sunshine1234",
        "mynameis12345",
        "defaultpassword",
        "samplepassword",
        "testpassword",
        "testtesttest",
    }
)
_KEYBOARD_ROWS = "qwertyuiopasdfghjklzxcvbnm"
# Words every attacker tries, whatever the install. The username and server name are added.
_ALWAYS_GUESSED = ("aresgate",)
# Shorter words (a server called "lan.home", a username "bob") would reject too much.
_MIN_GUESSABLE_WORD = 4
_MIN_KEYBOARD_RUN = 6


class PasswordPolicyError(ValueError):
    """The password breaks a rule. The message says which, and is meant to be shown."""


def normalize(password: str) -> str:
    """The form a password is hashed in, so the same characters typed on another device
    (a composed é or an e and an accent) are the same password."""
    return unicodedata.normalize("NFKC", password)


def _squash(password: str) -> str:
    return "".join(character for character in password.casefold() if character.isalnum())


def _is_a_run(password: str) -> bool:
    steps = {ord(b) - ord(a) for a, b in pairwise(password)}
    return steps <= {1} or steps <= {-1}


def _is_keyboard_run(squashed: str) -> bool:
    # Too little left after the symbols are dropped says nothing about the password.
    if len(squashed) < _MIN_KEYBOARD_RUN:
        return False
    return squashed in _KEYBOARD_ROWS or squashed[::-1] in _KEYBOARD_ROWS


def check_policy(password: str, *, username: str, server_name: str) -> None:
    """Raises PasswordPolicyError unless the password is acceptable for a new account."""
    password = normalize(password)
    if len(password) < MIN_LENGTH:
        raise PasswordPolicyError(f"Use at least {MIN_LENGTH} characters.")
    if len(password) > MAX_LENGTH:
        raise PasswordPolicyError(f"Use at most {MAX_LENGTH} characters.")

    squashed = _squash(password)
    if squashed in _COMMON or _is_a_run(password) or _is_keyboard_run(squashed):
        raise PasswordPolicyError("That password is too easy to guess. Try a longer phrase.")
    if len(set(password)) < 5:
        raise PasswordPolicyError("That password repeats too few characters. Try a longer phrase.")

    guessed = {username, *_ALWAYS_GUESSED, *server_name.split(".")}
    words = {_squash(word) for word in guessed}
    if any(len(word) >= _MIN_GUESSABLE_WORD and word in squashed for word in words):
        raise PasswordPolicyError(
            "Don't use your username, the server's name or AresGate in your password."
        )


def hash_password(password: str) -> str:
    return hasher.hash(normalize(password))


@cache
def _decoy_hash() -> str:
    return hasher.hash("a password nobody has")


def verify_password(password: str, stored_hash: str | None) -> bool:
    """Whether the password matches. With no hash to check against (the username isn't an
    account), it still does the same work, so the time taken doesn't reveal that."""
    try:
        matches = hasher.verify(stored_hash or _decoy_hash(), normalize(password))
    except VerificationError, InvalidHashError:
        return False
    return matches and stored_hash is not None


def needs_rehash(stored_hash: str) -> bool:
    """Whether the hash was made with weaker settings than the hasher now uses."""
    return hasher.check_needs_rehash(stored_hash)
