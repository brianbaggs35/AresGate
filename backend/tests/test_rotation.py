import pytest
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Base, RecoveryCode, TotpCredential, User, utcnow
from app.security import credential_store, rotation, totp, two_factor, vault
from app.security.credential_store import Kind
from tests.helpers import ACCOUNT_PASSWORD, TEST_DATABASE_URL, turn_on_two_factor

API_KEY = "a-firewall-api-key-for-tests"
AI_KEY = "an-ai-providers-key-for-tests"
NEW_KEY = "a brand new key, also long enough to be used"


def settings_with(key: str) -> Settings:
    return Settings(environment="test", database_url=TEST_DATABASE_URL, secret_key=SecretStr(key))


def fill(session: Session, settings: Settings, account: User) -> tuple[str, list[str]]:
    """Everything AresGate seals: two credentials and an account's authenticator app."""
    now = utcnow()
    credential_store.store(session, settings, Kind.INTEGRATION, "opnsense", "api_key", API_KEY, now)
    credential_store.store(session, settings, Kind.AI_PROVIDER, "anthropic", "api_key", AI_KEY, now)
    return turn_on_two_factor(session, settings, account)


def test_everything_sealed_opens_with_the_new_key_and_no_longer_with_the_old(
    session: Session, settings: Settings, account: User
) -> None:
    secret, _ = fill(session, settings, account)
    new = settings_with(NEW_KEY)

    result = rotation.rotate(session, settings, new)
    session.commit()

    assert result.credentials == 2
    assert result.authenticator_keys == 1
    session.expire_all()
    assert credential_store.reveal(session, new, Kind.INTEGRATION, "opnsense", "api_key") == API_KEY
    assert credential_store.reveal(session, new, Kind.AI_PROVIDER, "anthropic", "api_key") == AI_KEY
    with pytest.raises(vault.VaultError):
        credential_store.reveal(session, settings, Kind.INTEGRATION, "opnsense", "api_key")
    with pytest.raises(vault.VaultError):
        credential_store.reveal(session, settings, Kind.AI_PROVIDER, "anthropic", "api_key")
    credential = session.get(TotpCredential, account.id)
    assert credential is not None
    assert vault.unseal(new, "authenticator-key", credential.secret_sealed, str(account.id)) == (
        secret.encode()
    )


def test_the_authenticator_app_keeps_working_with_the_new_key(
    session: Session, settings: Settings, account: User
) -> None:
    secret, _ = fill(session, settings, account)
    new = settings_with(NEW_KEY)
    now = utcnow()
    last = totp.current_period(now)

    rotation.rotate(session, settings, new)
    session.commit()

    accepted = two_factor.accept_code(
        session, new, account.id, totp.code_for(secret, last + 1), now
    )
    assert accepted is not None
    assert accepted.method == two_factor.Method.AUTHENTICATOR


def test_recovery_codes_cannot_be_carried_over_and_are_removed(
    session: Session, settings: Settings, account: User
) -> None:
    _, codes = fill(session, settings, account)

    result = rotation.rotate(session, settings, settings_with(NEW_KEY))
    session.commit()

    assert result.recovery_codes_removed == len(codes)
    assert session.scalar(select(func.count()).select_from(RecoveryCode)) == 0
    # The account keeps its authenticator app, and can make new codes with it.
    assert two_factor.is_enabled(session, account.id)


def test_nothing_sealed_is_a_rotation_of_nothing(session: Session, settings: Settings) -> None:
    result = rotation.rotate(session, settings, settings_with(NEW_KEY))

    assert result == rotation.Rotated(credentials=0, authenticator_keys=0, recovery_codes_removed=0)


def test_a_credential_that_cannot_be_opened_is_named_and_nothing_changes(
    session: Session, settings: Settings, account: User
) -> None:
    fill(session, settings, account)
    elsewhere = settings_with("a key that sealed this somewhere else")
    credential_store.store(
        session, elsewhere, Kind.INTEGRATION, "zzz-broken", "api_key", "x", utcnow()
    )
    session.commit()

    new = settings_with(NEW_KEY)
    with pytest.raises(vault.VaultError, match=r"integration secret zzz-broken/api_key"):
        rotation.rotate(session, settings, new)
    session.rollback()

    for kind, name in ((Kind.INTEGRATION, "opnsense"), (Kind.AI_PROVIDER, "anthropic")):
        assert credential_store.reveal(session, settings, kind, name, "api_key")


def test_an_authenticator_key_that_cannot_be_opened_names_its_account(
    session: Session, settings: Settings, account: User
) -> None:
    elsewhere = settings_with("a key that sealed this somewhere else")
    turn_on_two_factor(session, elsewhere, account)

    new = settings_with(NEW_KEY)
    with pytest.raises(vault.VaultError, match=f"authenticator key of {account.username}"):
        rotation.rotate(session, settings, new)


def test_every_column_that_is_sealed_is_rotated() -> None:
    """A table that gains a sealed column has to be added to ``rotation.rotate``, or a new key
    would leave it unreadable. Then add it here."""
    sealed = {
        (table.name, column.name)
        for table in Base.metadata.sorted_tables
        for column in table.columns
        if column.name.endswith("_sealed")
    }

    assert sealed == {("credentials", "value_sealed"), ("totp_credentials", "secret_sealed")}


def test_a_dump_of_the_whole_database_reveals_none_of_what_is_sealed_or_hashed(
    session: Session, settings: Settings, account: User
) -> None:
    secret, codes = fill(session, settings, account)
    session.commit()

    dump = "\n".join(
        repr(tuple(row))
        for table in Base.metadata.sorted_tables
        for row in session.execute(select(table))
    )

    # The dump holds the rows, so it proves nothing unless it holds the sealed ones too.
    assert account.username in dump
    assert dump.count("'v1.") >= 3
    for plaintext in (API_KEY, AI_KEY, secret, ACCOUNT_PASSWORD):
        assert plaintext not in dump
    for code in codes:
        assert code not in dump
        assert code.replace("-", "") not in dump
    # Nor does it reveal anything after a new key.
    rotation.rotate(session, settings, settings_with(NEW_KEY))
    session.commit()
    rotated = "\n".join(
        repr(tuple(row))
        for table in Base.metadata.sorted_tables
        for row in session.execute(select(table))
    )
    for plaintext in (API_KEY, AI_KEY, secret):
        assert plaintext not in rotated


def test_without_the_key_the_dump_cannot_be_opened(
    session: Session, settings: Settings, account: User
) -> None:
    fill(session, settings, account)
    session.commit()
    sealed = list(session.scalars(select(Base.metadata.tables["credentials"].c.value_sealed)))
    stranger = settings_with("a stranger who only has the database")

    assert len(sealed) == 2
    for value in sealed:
        for purpose in ("integration-credential", "ai-provider-credential"):
            with pytest.raises(vault.VaultError):
                vault.unseal(stranger, purpose, value, "integration/opnsense/api_key")
