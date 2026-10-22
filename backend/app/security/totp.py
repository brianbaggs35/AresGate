"""Time-based one-time codes (RFC 6238), the six digits an authenticator app shows.

The apps all agree on one recipe: HMAC-SHA1 of the 30-second period the time falls in, cut down
to six digits (RFC 4226). Stronger hashes are in the standard, but several of the most used apps
ignore the setting and show SHA-1 codes anyway, so only SHA-1 works everywhere. What protects
the account is that a code is good for one use and that wrong guesses lock it (see
``throttle``), not the hash.
"""

import base64
import hashlib
import hmac
import secrets
import struct
from datetime import datetime
from urllib.parse import quote, urlencode

DIGITS = 6
PERIOD_SECONDS = 30
SECRET_BYTES = 20  # 160 bits, as RFC 4226 recommends.
# A phone's clock is rarely exact, so the period before and the one after count too.
DRIFT_PERIODS = 1


def new_secret() -> str:
    """A new key, in the base32 that authenticator apps take (``JBSWY3DP…``)."""
    return base64.b32encode(secrets.token_bytes(SECRET_BYTES)).decode()


def _key(secret: str) -> bytes:
    return base64.b32decode(secret)


def current_period(now: datetime) -> int:
    """Which 30-second period of time since 1970 ``now`` is in."""
    return int(now.timestamp()) // PERIOD_SECONDS


def code_for(secret: str, period: int) -> str:
    """The six digits for a period."""
    digest = hmac.new(_key(secret), struct.pack(">Q", period), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(number % 10**DIGITS).zfill(DIGITS)


def normalize(code: str) -> str:
    """The digits of what was typed, ignoring the space many apps show in the middle."""
    return "".join(code.split())


def looks_like_code(code: str) -> bool:
    normalized = normalize(code)
    return len(normalized) == DIGITS and normalized.isascii() and normalized.isdigit()


def verify(secret: str, code: str, now: datetime, *, after: int | None = None) -> int | None:
    """The period a code belongs to, or None if it is wrong.

    A period is good once: pass the last one that was accepted as ``after``, and that period and
    earlier ones are refused, so a code someone watched being typed is of no use to them. Every
    period is compared, whichever matches, so the time taken doesn't say how close a guess was.
    """
    normalized = normalize(code)
    if not looks_like_code(normalized):
        return None
    current = current_period(now)
    matched: int | None = None
    for period in range(current - DRIFT_PERIODS, current + DRIFT_PERIODS + 1):
        if hmac.compare_digest(code_for(secret, period), normalized) and (
            after is None or period > after
        ):
            matched = period
    return matched


def provisioning_uri(secret: str, account: str, issuer: str) -> str:
    """The ``otpauth://`` address that a QR code carries, which an authenticator app reads to
    add the account."""
    label = f"{quote(issuer, safe='')}:{quote(account, safe='')}"
    query = urlencode(
        {
            "secret": secret,
            "issuer": issuer,
            "algorithm": "SHA1",
            "digits": DIGITS,
            "period": PERIOD_SECONDS,
        },
        quote_via=quote,
    )
    return f"otpauth://totp/{label}?{query}"
