import base64
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

import pytest

from app.security import totp

# RFC 4226 appendix D: the key is the ASCII "12345678901234567890", and these are the six
# digits for counters 0 to 9.
RFC_KEY = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
RFC_CODES = [
    "755224",
    "287082",
    "359152",
    "969429",
    "338314",
    "254676",
    "287922",
    "162583",
    "399871",
    "520489",
]


def at(seconds: int) -> datetime:
    return datetime.fromtimestamp(seconds, UTC)


@pytest.mark.parametrize(("counter", "expected"), list(enumerate(RFC_CODES)))
def test_codes_match_the_rfc_4226_examples(counter: int, expected: str) -> None:
    assert totp.code_for(RFC_KEY, counter) == expected


def test_a_period_is_thirty_seconds() -> None:
    # RFC 6238 appendix B: at 59 seconds the period is 1, and SHA-1's code ends in 287082.
    assert totp.current_period(at(59)) == 1
    assert totp.current_period(at(60)) == 2
    assert totp.code_for(RFC_KEY, totp.current_period(at(59))) == "287082"


def test_new_secrets_are_160_bit_base32_and_different() -> None:
    first, second = totp.new_secret(), totp.new_secret()

    assert first != second
    assert len(first) == 32
    assert len(base64.b32decode(first)) == 20


def test_the_current_code_is_right() -> None:
    assert totp.verify(RFC_KEY, "287082", at(59)) == 1


def test_a_code_with_a_space_or_around_whitespace_is_right() -> None:
    assert totp.verify(RFC_KEY, " 287 082 ", at(59)) == 1


def test_the_period_before_and_after_are_allowed_for_a_clock_that_is_a_little_off() -> None:
    now = at(59 + 30 * 10)
    period = totp.current_period(now)

    assert totp.verify(RFC_KEY, totp.code_for(RFC_KEY, period - 1), now) == period - 1
    assert totp.verify(RFC_KEY, totp.code_for(RFC_KEY, period + 1), now) == period + 1
    assert totp.verify(RFC_KEY, totp.code_for(RFC_KEY, period - 2), now) is None
    assert totp.verify(RFC_KEY, totp.code_for(RFC_KEY, period + 2), now) is None


def test_a_period_can_only_be_used_once() -> None:
    now = at(59)

    assert totp.verify(RFC_KEY, "287082", now, after=1) is None
    assert totp.verify(RFC_KEY, "287082", now, after=0) == 1
    # A code for a later period is still good.
    later = totp.code_for(RFC_KEY, 2)
    assert totp.verify(RFC_KEY, later, now, after=1) == 2


@pytest.mark.parametrize(
    "wrong",
    [
        "",
        "12345",
        "1234567",
        "abcdef",
        "\u0661\u0662\u0663\u0664\u0665\u0666",
        "28708\uff12",
        "000000",
    ],
)
def test_what_is_not_the_code_is_refused(wrong: str) -> None:
    assert totp.verify(RFC_KEY, wrong, at(59)) is None


def test_looks_like_code() -> None:
    assert totp.looks_like_code("123456")
    assert totp.looks_like_code("123 456")
    assert not totp.looks_like_code("K7QD-3MWX-9HPA")
    assert not totp.looks_like_code("12345")


def test_the_address_for_an_app_names_the_issuer_and_account() -> None:
    uri = totp.provisioning_uri(RFC_KEY, "brian@example", "AresGate")

    parts = urlsplit(uri)
    assert (parts.scheme, parts.netloc, parts.path) == (
        "otpauth",
        "totp",
        "/AresGate:brian%40example",
    )
    assert parse_qs(parts.query) == {
        "secret": [RFC_KEY],
        "issuer": ["AresGate"],
        "algorithm": ["SHA1"],
        "digits": ["6"],
        "period": ["30"],
    }
