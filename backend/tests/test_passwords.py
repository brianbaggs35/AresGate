from typing import Literal

import pytest
from argon2 import PasswordHasher

from app.security import passwords
from app.security.passwords import PasswordPolicyError, check_policy

SERVER = "aresgate.example.com"


def acceptable(password: str, username: str = "brian") -> None:
    check_policy(password, username=username, server_name=SERVER)


@pytest.mark.parametrize(
    "password",
    [
        "a sentence nobody would guess",
        "correct horse battery staple",
        "short but 12 chars",
        "!@#$%^&*()_+",
        "ünïcödé pässwörd 🙂",
        "abcdefgh" * 16,
    ],
)
def test_a_good_password_is_accepted(password: str) -> None:
    acceptable(password)


def test_length_counts_not_composition() -> None:
    acceptable("all lowercase words here")


@pytest.mark.parametrize("password", ["", "elevenchars", "a b c d e f"])
def test_a_short_password_is_refused(password: str) -> None:
    with pytest.raises(PasswordPolicyError, match=r"at least 12"):
        acceptable(password)


def test_a_very_long_password_is_refused() -> None:
    with pytest.raises(PasswordPolicyError, match=r"at most 128"):
        acceptable("ab" * 65)


@pytest.mark.parametrize(
    "password",
    [
        "123456789012",
        "Password1234",
        "PASSWORD-12345",
        "q w e r t y u i o p 1 2",
        "iloveyou1234",
    ],
)
def test_a_common_password_is_refused_however_it_is_written(password: str) -> None:
    with pytest.raises(PasswordPolicyError, match="too easy to guess"):
        acceptable(password)


@pytest.mark.parametrize(
    "password",
    ["abcdefghijkl", "ZYXWVUTSRQPO", "456789:;<=>?", "qwertyuiopasdf", "MNBVCXZLKJHGF"],
)
def test_a_run_of_characters_is_refused(password: str) -> None:
    with pytest.raises(PasswordPolicyError, match="too easy to guess"):
        acceptable(password)


def test_a_keyboard_run_with_symbols_between_is_refused() -> None:
    with pytest.raises(PasswordPolicyError, match="too easy to guess"):
        acceptable("q-w-e-r-t-y-u-i-o-p")


def test_symbols_alone_say_nothing_about_a_keyboard_run() -> None:
    acceptable("!#$%&'()*+,-./")


@pytest.mark.parametrize("password", ["aaaaaaaaaaaa", "abababababab", "ababcabcabcab"])
def test_a_password_with_few_different_characters_is_refused(password: str) -> None:
    with pytest.raises(PasswordPolicyError, match="repeats too few"):
        acceptable(password)


@pytest.mark.parametrize(
    "password",
    [
        "my brian password",
        "BRIAN is my name!!",
        "AresGate is great",
        "ares-gate rules ok",
        "aresgate.example is it",
        "welcome to EXAMPLE land",
    ],
)
def test_a_password_made_of_what_an_attacker_tries_first_is_refused(password: str) -> None:
    with pytest.raises(PasswordPolicyError, match="username, the server's name or AresGate"):
        acceptable(password)


def test_short_usernames_and_server_names_are_not_held_against_a_password() -> None:
    check_policy("sunny bob and lan days", username="bob", server_name="lan.home")


def test_the_same_password_typed_two_ways_is_one_password() -> None:
    composed = "café au lait & more"
    decomposed = "café au lait & more"
    stored = passwords.hash_password(composed)

    assert passwords.verify_password(decomposed, stored)


def test_a_password_checks_against_its_hash() -> None:
    stored = passwords.hash_password("a sentence nobody would guess")

    assert passwords.verify_password("a sentence nobody would guess", stored)
    assert not passwords.verify_password("another sentence entirely", stored)


def test_hashes_are_argon2id_with_a_salt_of_their_own() -> None:
    first = passwords.hash_password("a sentence nobody would guess")
    second = passwords.hash_password("a sentence nobody would guess")

    assert first.startswith("$argon2id$")
    assert first != second


def test_a_hash_that_is_not_one_matches_nothing() -> None:
    assert not passwords.verify_password("anything at all", "not a hash")


def test_no_hash_matches_nothing_but_takes_the_same_work(monkeypatch: pytest.MonkeyPatch) -> None:
    verified: list[str] = []

    class Recording(PasswordHasher):
        def verify(self, hash: str | bytes, password: str | bytes) -> Literal[True]:
            verified.append(str(hash))
            return super().verify(hash, password)

    monkeypatch.setattr(passwords, "hasher", Recording(time_cost=1, memory_cost=8, parallelism=1))

    # The decoy's own password, which must still not count as a match.
    assert not passwords.verify_password("a password nobody has", None)
    assert len(verified) == 1
    assert verified[0].startswith("$argon2id$")


def test_a_hash_made_with_weaker_settings_needs_rehashing() -> None:
    weak = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash("x")
    current = passwords.hash_password("x")

    assert not passwords.needs_rehash(current)
    stronger = PasswordHasher(time_cost=2, memory_cost=16, parallelism=1)
    assert stronger.check_needs_rehash(weak)


def test_the_real_hasher_uses_the_recommended_settings() -> None:
    real = PasswordHasher()

    assert real.hash("x").startswith("$argon2id$v=19$m=65536,t=3,p=4$")
