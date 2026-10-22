import pytest
from pydantic import SecretStr

from app.config import Settings
from app.security import vault
from tests.helpers import TEST_DATABASE_URL, TEST_SECRET_KEY


def settings_with(key: str) -> Settings:
    return Settings(environment="test", database_url=TEST_DATABASE_URL, secret_key=SecretStr(key))


def test_what_is_sealed_can_be_opened(settings: Settings) -> None:
    sealed = vault.seal(settings, "authenticator-key", b"JBSWY3DPEHPK3PXP", "account-1")

    assert vault.unseal(settings, "authenticator-key", sealed, "account-1") == b"JBSWY3DPEHPK3PXP"


def test_the_plaintext_is_not_in_what_is_stored(settings: Settings) -> None:
    sealed = vault.seal(settings, "authenticator-key", b"JBSWY3DPEHPK3PXP", "account-1")

    assert "JBSWY3DPEHPK3PXP" not in sealed
    assert sealed.startswith("v1.")


def test_sealing_the_same_thing_twice_gives_different_results(settings: Settings) -> None:
    first = vault.seal(settings, "authenticator-key", b"same", "account-1")
    second = vault.seal(settings, "authenticator-key", b"same", "account-1")

    assert first != second


def test_another_key_cannot_open_it(settings: Settings) -> None:
    sealed = vault.seal(settings, "authenticator-key", b"secret", "account-1")

    with pytest.raises(vault.VaultError):
        vault.unseal(
            settings_with("another key, also long enough to be used"),
            "authenticator-key",
            sealed,
            "account-1",
        )


def test_it_opens_only_for_the_purpose_it_was_sealed_for(settings: Settings) -> None:
    sealed = vault.seal(settings, "authenticator-key", b"secret", "account-1")

    with pytest.raises(vault.VaultError):
        vault.unseal(settings, "integration-credential", sealed, "account-1")


def test_it_cannot_be_moved_to_another_row(settings: Settings) -> None:
    sealed = vault.seal(settings, "authenticator-key", b"secret", "account-1")

    with pytest.raises(vault.VaultError):
        vault.unseal(settings, "authenticator-key", sealed, "account-2")


def damage(sealed: str, how: str) -> str:
    version, nonce, ciphertext = sealed.split(".")
    swapped = "BB" if ciphertext.endswith("AA") else "AA"
    return {
        "altered": f"{version}.{nonce}.{ciphertext[:-2]}{swapped}",
        "unknown version": f"v2.{nonce}.{ciphertext}",
        "missing part": f"{version}.{nonce}",
        "empty": "",
        "not base64": "v1.!!!.???",
        "short nonce": f"{version}.AAAA.{ciphertext}",
    }[how]


@pytest.mark.parametrize(
    "how", ["altered", "unknown version", "missing part", "empty", "not base64", "short nonce"]
)
def test_damaged_values_are_refused(settings: Settings, how: str) -> None:
    sealed = vault.seal(settings, "authenticator-key", b"secret", "account-1")

    with pytest.raises(vault.VaultError):
        vault.unseal(settings, "authenticator-key", damage(sealed, how), "account-1")


def test_a_keyed_hash_is_repeatable_and_depends_on_everything(settings: Settings) -> None:
    first = vault.keyed_hash(settings, "recovery-code", "message")

    assert first == vault.keyed_hash(settings, "recovery-code", "message")
    assert len(first) == 64
    assert first != vault.keyed_hash(settings, "recovery-code", "another message")
    assert first != vault.keyed_hash(settings, "sign-in-challenge", "message")
    assert first != vault.keyed_hash(settings_with("x" * 40), "recovery-code", "message")


def test_the_test_key_is_the_one_in_use(settings: Settings) -> None:
    assert settings.secret_key is not None
    assert settings.secret_key.get_secret_value() == TEST_SECRET_KEY
