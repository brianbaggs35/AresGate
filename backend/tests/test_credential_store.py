from datetime import timedelta

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import StoredCredential, utcnow
from app.security import credential_store, vault
from app.security.credential_store import InvalidName, Kind
from tests.helpers import TEST_DATABASE_URL

API_KEY = "a-firewall-api-key-for-tests"


def keep(
    session: Session,
    settings: Settings,
    value: str = API_KEY,
    *,
    kind: Kind = Kind.INTEGRATION,
    name: str = "opnsense",
    field: str = "api_key",
) -> StoredCredential:
    row = credential_store.store(session, settings, kind, name, field, value, utcnow())
    session.commit()
    return row


def test_a_secret_can_be_read_back_by_the_code_that_needs_it(
    session: Session, settings: Settings
) -> None:
    keep(session, settings)

    revealed = credential_store.reveal(session, settings, Kind.INTEGRATION, "opnsense", "api_key")
    assert revealed == API_KEY


def test_asking_for_a_secret_that_is_not_kept_gives_none(
    session: Session, settings: Settings
) -> None:
    assert credential_store.reveal(session, settings, Kind.INTEGRATION, "wazuh", "token") is None


def test_the_secret_is_not_in_what_the_database_holds(session: Session, settings: Settings) -> None:
    row = keep(session, settings)

    assert API_KEY not in row.value_sealed
    assert row.value_sealed.startswith("v1.")


def test_keeping_a_secret_again_replaces_it(session: Session, settings: Settings) -> None:
    first = keep(session, settings, "the first")
    created = first.created_at
    later = utcnow() + timedelta(minutes=5)

    credential_store.store(
        session, settings, Kind.INTEGRATION, "opnsense", "api_key", "the second", later
    )
    session.commit()

    assert session.scalar(select(func.count()).select_from(StoredCredential)) == 1
    revealed = credential_store.reveal(session, settings, Kind.INTEGRATION, "opnsense", "api_key")
    assert revealed == "the second"
    session.expire_all()
    [row] = credential_store.entries(session)
    assert (row.created_at, row.updated_at) == (created, later)


def test_each_kind_name_and_field_is_kept_apart(session: Session, settings: Settings) -> None:
    keep(session, settings, "a", kind=Kind.INTEGRATION, name="same", field="key")
    keep(session, settings, "b", kind=Kind.AI_PROVIDER, name="same", field="key")
    keep(session, settings, "c", kind=Kind.INTEGRATION, name="other", field="key")
    keep(session, settings, "d", kind=Kind.INTEGRATION, name="same", field="secret")

    def revealed(kind: Kind, name: str, field: str) -> str | None:
        return credential_store.reveal(session, settings, kind, name, field)

    assert revealed(Kind.INTEGRATION, "same", "key") == "a"
    assert revealed(Kind.AI_PROVIDER, "same", "key") == "b"
    assert revealed(Kind.INTEGRATION, "other", "key") == "c"
    assert revealed(Kind.INTEGRATION, "same", "secret") == "d"


def test_the_list_says_what_is_kept_in_order_without_the_secrets(
    session: Session, settings: Settings
) -> None:
    keep(session, settings, kind=Kind.INTEGRATION, name="wazuh", field="password")
    keep(session, settings, kind=Kind.AI_PROVIDER, name="anthropic", field="api_key")
    keep(session, settings, kind=Kind.INTEGRATION, name="opnsense", field="api_secret")
    keep(session, settings, kind=Kind.INTEGRATION, name="opnsense", field="api_key")

    listed = [(row.kind, row.name, row.field) for row in credential_store.entries(session)]

    assert listed == [
        ("ai_provider", "anthropic", "api_key"),
        ("integration", "opnsense", "api_key"),
        ("integration", "opnsense", "api_secret"),
        ("integration", "wazuh", "password"),
    ]


def test_a_secret_can_be_forgotten(session: Session, settings: Settings) -> None:
    keep(session, settings)

    assert credential_store.remove(session, Kind.INTEGRATION, "opnsense", "api_key")
    session.commit()

    assert credential_store.entries(session) == []
    assert not credential_store.remove(session, Kind.INTEGRATION, "opnsense", "api_key")


@pytest.mark.parametrize(
    ("name", "field"),
    [
        ("Upper", "api_key"),
        ("opnsense", "api key"),
        ("a/b", "api_key"),
        ("opnsense", "../x"),
        ("", "api_key"),
        ("opnsense", "-leading"),
        ("x" * 64, "api_key"),
    ],
)
def test_names_that_are_not_short_lowercase_words_are_refused(
    session: Session, settings: Settings, name: str, field: str
) -> None:
    with pytest.raises(InvalidName):
        credential_store.store(session, settings, Kind.INTEGRATION, name, field, "x", utcnow())
    with pytest.raises(InvalidName):
        credential_store.reveal(session, settings, Kind.INTEGRATION, name, field)
    with pytest.raises(InvalidName):
        credential_store.remove(session, Kind.INTEGRATION, name, field)


def test_the_longest_name_is_accepted(session: Session, settings: Settings) -> None:
    keep(session, settings, name="x" * 63, field="y" * 63)

    assert credential_store.reveal(session, settings, Kind.INTEGRATION, "x" * 63, "y" * 63)


def test_a_secret_copied_onto_another_row_cannot_be_opened(
    session: Session, settings: Settings
) -> None:
    source = keep(session, settings, "firewall secret", name="opnsense", field="api_key")
    target = keep(session, settings, "other", name="ntopng", field="api_key")
    target.value_sealed = source.value_sealed
    session.commit()

    with pytest.raises(vault.VaultError):
        credential_store.reveal(session, settings, Kind.INTEGRATION, "ntopng", "api_key")


def test_a_secret_of_one_kind_cannot_be_opened_as_another(
    session: Session, settings: Settings
) -> None:
    row = keep(session, settings, "secret", kind=Kind.INTEGRATION, name="x", field="key")
    row.kind = Kind.AI_PROVIDER.value
    session.commit()

    with pytest.raises(vault.VaultError):
        credential_store.reveal(session, settings, Kind.AI_PROVIDER, "x", "key")


def test_another_key_cannot_open_a_secret(session: Session, settings: Settings) -> None:
    keep(session, settings)
    other = Settings(
        environment="test",
        database_url=TEST_DATABASE_URL,
        secret_key=SecretStr("another key, also long enough to be used"),
    )

    with pytest.raises(vault.VaultError):
        credential_store.reveal(session, other, Kind.INTEGRATION, "opnsense", "api_key")


def test_a_secret_can_contain_anything(session: Session, settings: Settings) -> None:
    value = "  päss wörd\n-----BEGIN KEY-----\tend 🔑 "
    keep(session, settings, value)

    revealed = credential_store.reveal(session, settings, Kind.INTEGRATION, "opnsense", "api_key")
    assert revealed == value
