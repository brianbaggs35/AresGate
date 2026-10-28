import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.integrations import netguard, probes, registry, service
from app.integrations.client import Call, Target
from app.integrations.netguard import HOME_NETWORK, HOME_NETWORK_AND_LOOPBACK
from app.integrations.probes import Verdict
from app.integrations.registry import ModuleState, SettingsError
from app.integrations.service import Incomplete, Status, Submission
from app.models import IntegrationConnection, StoredCredential
from app.security import credential_store
from app.security.credential_store import Kind
from tests.stubs import Answer, Serve, make_certificate

NOW = datetime(2099, 1, 1, 12, 0, tzinfo=UTC)
LATER = NOW + timedelta(hours=1)
OPNSENSE = registry.OPNSENSE
NTOPNG = registry.NTOPNG
WAZUH = registry.WAZUH


def opnsense_api(**changes: object) -> Submission:
    fields: dict[str, object] = {
        "url": "https://192.168.1.1",
        "tls_mode": "system",
        "tls_ca_pem": None,
        "tls_fingerprint": None,
        "options": {},
        "secrets": {"api_key": "key-123456", "api_secret": "secret-123456"},
    }
    return Submission(**{**fields, **changes})  # type: ignore[arg-type]


def save(
    session: Session,
    settings: Settings,
    definition: registry.IntegrationDef,
    submitted: dict[str, Submission],
    now: datetime = NOW,
    policy: netguard.AddressPolicy = HOME_NETWORK,
) -> None:
    service.save(session, settings, policy, definition, submitted, now)
    session.commit()


def problems(
    session: Session,
    settings: Settings,
    definition: registry.IntegrationDef,
    submitted: dict[str, Submission],
) -> dict[str, str]:
    with pytest.raises(SettingsError) as raised:
        service.save(session, settings, HOME_NETWORK, definition, submitted, NOW)
    session.rollback()
    return raised.value.problems


def secret(session: Session, settings: Settings, name: str, field: str) -> str | None:
    return credential_store.reveal(session, settings, Kind.INTEGRATION, name, field)


def test_saving_keeps_the_settings_and_seals_the_secrets(
    session: Session, settings: Settings
) -> None:
    save(session, settings, OPNSENSE, {"api": opnsense_api(url=" https://192.168.1.1/ ")})

    row = service.rows_for(session, "opnsense")["api"]
    assert row.base_url == "https://192.168.1.1"
    assert (row.tls_mode, row.tls_ca_pem, row.tls_fingerprint) == ("system", None, None)
    assert row.options == {}
    assert row.module_states == {}
    assert row.disabled_modules == []
    assert (row.last_attempt_at, row.last_success_at, row.last_error) == (None, None, None)
    assert row.created_at == row.updated_at == NOW
    assert secret(session, settings, "opnsense-api", "api_key") == "key-123456"
    assert secret(session, settings, "opnsense-api", "api_secret") == "secret-123456"
    sealed = session.scalars(select(StoredCredential.value_sealed)).all()
    assert sealed
    assert all("key-123456" not in value for value in sealed)
    assert service.secrets_set(session, "opnsense", "api") == ["api_key", "api_secret"]


def test_saving_again_replaces_the_settings_and_keeps_the_secrets_left_blank(
    session: Session, settings: Settings
) -> None:
    save(session, settings, OPNSENSE, {"api": opnsense_api()})
    first = service.rows_for(session, "opnsense")["api"]
    service.record_attempt(first, Verdict(True, "ok", {"suricata": ModuleState.RUNNING}), NOW)
    session.commit()

    save(
        session,
        settings,
        OPNSENSE,
        {
            "api": opnsense_api(
                url="https://192.168.1.2:8443",
                secrets={"api_key": "new-key-123456", "api_secret": "  "},
                disabled_modules=["suricata", "suricata", "kea"],
            )
        },
        LATER,
    )

    [row] = session.scalars(select(IntegrationConnection)).all()
    assert row.id == first.id
    assert row.base_url == "https://192.168.1.2:8443"
    assert row.disabled_modules == ["kea", "suricata"]
    assert row.created_at == NOW
    assert row.updated_at == LATER
    # What the last test found was about the old settings.
    assert (row.module_states, row.last_attempt_at, row.last_error) == ({}, None, None)
    assert row.last_success_at == NOW
    assert secret(session, settings, "opnsense-api", "api_key") == "new-key-123456"
    assert secret(session, settings, "opnsense-api", "api_secret") == "secret-123456"


def test_a_secret_that_was_pasted_with_a_newline_is_cleaned(
    session: Session, settings: Settings
) -> None:
    submission = opnsense_api(secrets={"api_key": "key-123456\r\n", "api_secret": "\tsecret 123 "})

    save(session, settings, OPNSENSE, {"api": submission})

    assert secret(session, settings, "opnsense-api", "api_key") == "key-123456"
    assert secret(session, settings, "opnsense-api", "api_secret") == "secret 123 "


def test_changing_how_ntopng_is_signed_into_drops_the_secret_no_longer_used(
    session: Session, settings: Settings
) -> None:
    token = Submission(
        "http://192.168.1.2:3000", "system", None, None, {"auth": "token"}, {"token": "tok-123456"}
    )
    password = Submission(
        "http://192.168.1.2:3000",
        "system",
        None,
        None,
        {"auth": "basic", "username": "admin", "interface_id": "1"},
        {"password": "pw-123456"},
    )
    save(session, settings, NTOPNG, {"api": token})
    assert service.secrets_set(session, "ntopng", "api") == ["token"]

    save(session, settings, NTOPNG, {"api": password})

    assert service.secrets_set(session, "ntopng", "api") == ["password"]
    row = service.rows_for(session, "ntopng")["api"]
    assert row.options == {"auth": "basic", "username": "admin", "interface_id": 1}


def test_a_plain_http_address_has_no_certificate_settings(
    session: Session, settings: Settings
) -> None:
    submission = Submission(
        "http://192.168.1.2:3000",
        "pinned",
        "ignored",
        "also ignored",
        {},
        {"token": "tok-123456"},
    )

    save(session, settings, NTOPNG, {"api": submission})

    row = service.rows_for(session, "ntopng")["api"]
    assert (row.tls_mode, row.tls_ca_pem, row.tls_fingerprint) == ("system", None, None)


def test_a_pasted_authority_and_a_pinned_fingerprint_are_kept_in_their_normal_form(
    session: Session, settings: Settings
) -> None:
    certificate = make_certificate()
    wazuh = {
        "manager": Submission(
            "https://192.168.1.3:55000",
            "ca",
            f"  {certificate.pem}",
            None,
            {"username": "wazuh-wui"},
            {"password": "pw-123456"},
        ),
        "indexer": Submission(
            "https://192.168.1.3:9200",
            "pinned",
            None,
            certificate.fingerprint.replace(":", " ").lower(),
            {"username": "reader"},
            {"password": "pw-654321"},
        ),
    }

    save(session, settings, WAZUH, wazuh)

    rows = service.rows_for(session, "wazuh")
    assert rows["manager"].tls_ca_pem == certificate.pem
    assert rows["manager"].tls_fingerprint is None
    assert rows["indexer"].tls_fingerprint == certificate.fingerprint
    assert rows["indexer"].tls_ca_pem is None
    assert service.secrets_set(session, "wazuh", "indexer") == ["password"]


def test_optional_connections_are_left_out_or_removed(session: Session, settings: Settings) -> None:
    zenarmor = Submission(
        "https://192.168.1.1:8090", "system", None, None, {"user": "u"}, {"api_key": "zen-123456"}
    )
    save(session, settings, OPNSENSE, {"api": opnsense_api(), "zenarmor": zenarmor})
    assert set(service.rows_for(session, "opnsense")) == {"api", "zenarmor"}
    assert service.secrets_set(session, "opnsense", "zenarmor") == ["api_key"]

    save(session, settings, OPNSENSE, {"api": opnsense_api()})

    assert set(service.rows_for(session, "opnsense")) == {"api"}
    assert service.secrets_set(session, "opnsense", "zenarmor") == []
    save(session, settings, OPNSENSE, {"api": opnsense_api()})
    assert set(service.rows_for(session, "opnsense")) == {"api"}


def test_everything_wrong_is_reported_at_once_and_nothing_is_kept(
    session: Session, settings: Settings
) -> None:
    found = problems(
        session,
        settings,
        WAZUH,
        {
            "manager": Submission("ftp://x", "ca", "junk", None, {}, {}),
            "indexer": Submission(
                "https://192.168.1.3:9200",
                "pinned",
                None,
                "abc",
                {"username": "x" * 200},
                {"password": "pw-123456"},
            ),
            "other": opnsense_api(),
        },
    )

    assert found == {
        "other": "There is no such connection.",
        "manager.url": "Start the address with https:// and the host, such as https://192.168.1.1.",
        "manager.tls_ca_pem": found["manager.tls_ca_pem"],
        "manager.username": "Enter a value.",
        "indexer.tls_fingerprint": (
            "Enter a SHA-256 fingerprint: 64 hexadecimal digits, with or without colons."
        ),
        "indexer.username": "Use at most 128 characters, and no control characters.",
    }
    assert "isn't a certificate in PEM form" in found["manager.tls_ca_pem"]
    assert session.scalars(select(IntegrationConnection)).all() == []
    assert credential_store.entries(session) == []


def test_a_connection_that_is_required_has_to_be_filled_in(
    session: Session, settings: Settings
) -> None:
    assert problems(session, settings, OPNSENSE, {}) == {"api": "Fill in this connection."}


def test_a_certificate_choice_that_does_not_exist_is_refused(
    session: Session, settings: Settings
) -> None:
    found = problems(session, settings, OPNSENSE, {"api": opnsense_api(tls_mode="skip")})

    assert found == {"api.tls_mode": "Choose how to check the certificate."}


def test_a_missing_ca_is_refused(session: Session, settings: Settings) -> None:
    found = problems(session, settings, OPNSENSE, {"api": opnsense_api(tls_mode="ca")})

    assert "api.tls_ca_pem" in found


def test_a_service_that_the_connection_does_not_have_is_refused(
    session: Session, settings: Settings
) -> None:
    found = problems(
        session, settings, OPNSENSE, {"api": opnsense_api(disabled_modules=["suricata", "nope"])}
    )

    assert found == {"api.disabled_modules": "That isn't one of its services."}


def test_an_address_that_is_not_on_the_home_network_is_refused(
    session: Session, settings: Settings
) -> None:
    found = problems(
        session,
        settings,
        OPNSENSE,
        {"api": opnsense_api(url="https://169.254.169.254")},
    )

    assert "metadata services" in found["api.url"]
    assert (
        "isn't a private network address"
        in problems(session, settings, OPNSENSE, {"api": opnsense_api(url="https://8.8.8.8")})[
            "api.url"
        ]
    )
    assert set(found) == {"api.url"}


def test_the_other_secrets_are_not_asked_about_while_the_options_are_wrong(
    session: Session, settings: Settings
) -> None:
    submission = Submission("http://192.168.1.2:3000", "system", None, None, {"auth": "magic"}, {})

    assert problems(session, settings, NTOPNG, {"api": submission}) == {
        "api.auth": "Choose one of the options."
    }


def test_disconnecting_forgets_the_settings_and_the_secrets(
    session: Session, settings: Settings
) -> None:
    save(session, settings, OPNSENSE, {"api": opnsense_api()})
    save(
        session,
        settings,
        NTOPNG,
        {
            "api": Submission(
                "http://192.168.1.2:3000", "system", None, None, {}, {"token": "tok-123456"}
            )
        },
    )

    assert service.disconnect(session, OPNSENSE)
    session.commit()

    assert service.rows_for(session, "opnsense") == {}
    assert service.secrets_set(session, "opnsense", "api") == []
    assert set(service.rows_for(session, "ntopng")) == {"api"}
    assert service.secrets_set(session, "ntopng", "api") == ["token"]
    assert not service.disconnect(session, OPNSENSE)


def test_the_status_is_the_worst_of_the_connections(session: Session, settings: Settings) -> None:
    wazuh = {
        key: Submission(
            f"https://192.168.1.3:{port}",
            "system",
            None,
            None,
            {"username": "u"},
            {"password": "pw-123456"},
        )
        for key, port in (("manager", 55000), ("indexer", 9200))
    }
    assert service.integration_status({}) is Status.NOT_CONNECTED
    assert service.connection_status(None) is Status.NOT_CONNECTED
    save(session, settings, WAZUH, wazuh)
    rows = service.rows_for(session, "wazuh")
    assert service.integration_status(rows) is Status.UNTESTED

    service.record_attempt(rows["manager"], Verdict(True, "fine"), NOW)
    assert service.connection_status(rows["manager"]) is Status.CONNECTED
    assert service.integration_status(rows) is Status.UNTESTED

    service.record_attempt(rows["indexer"], Verdict(True, "fine"), LATER)
    assert service.integration_status(rows) is Status.CONNECTED
    assert service.last_success(rows) == LATER

    service.record_attempt(rows["indexer"], Verdict(False, "Broke\nbadly"), LATER + timedelta(1))
    assert service.connection_status(rows["indexer"]) is Status.PROBLEM
    assert service.integration_status(rows) is Status.PROBLEM
    assert rows["indexer"].last_error == "Broke badly"
    assert service.last_success(rows) == LATER
    assert service.last_success({}) is None


def test_an_attempt_keeps_what_was_found_of_the_modules(
    session: Session, settings: Settings
) -> None:
    save(session, settings, OPNSENSE, {"api": opnsense_api()})
    row = service.rows_for(session, "opnsense")["api"]

    service.record_attempt(row, Verdict(True, "fine", {"suricata": ModuleState.NOT_INSTALLED}), NOW)
    service.record_attempt(row, Verdict(False, "later failure"), LATER)

    assert row.module_states == {"suricata": "not_installed"}
    assert row.last_success_at == NOW
    assert row.last_attempt_at == LATER


def test_a_saved_connection_is_opened_for_use(session: Session, settings: Settings) -> None:
    save(session, settings, OPNSENSE, {"api": opnsense_api()})
    row = service.rows_for(session, "opnsense")["api"]

    target = service.load_target(session, settings, OPNSENSE, OPNSENSE.connections[0], row)

    assert (target.integration, target.connection) == ("opnsense", "api")
    assert target.origin == netguard.Origin("https", "192.168.1.1", 443)
    assert target.secrets == {"api_key": "key-123456", "api_secret": "secret-123456"}
    assert (target.tls_mode, target.tls_ca_pem, target.tls_fingerprint) == ("system", None, None)


def test_a_connection_whose_secret_is_gone_cannot_be_used(
    session: Session, settings: Settings
) -> None:
    save(session, settings, OPNSENSE, {"api": opnsense_api()})
    credential_store.remove(session, Kind.INTEGRATION, "opnsense-api", "api_secret")
    row = service.rows_for(session, "opnsense")["api"]

    with pytest.raises(Incomplete, match=r"OPNsense API: API secret is missing"):
        service.load_target(session, settings, OPNSENSE, OPNSENSE.connections[0], row)


def test_a_secret_that_cannot_be_opened_cannot_be_used(
    session: Session, settings: Settings
) -> None:
    save(session, settings, OPNSENSE, {"api": opnsense_api()})
    row = service.rows_for(session, "opnsense")["api"]

    wrong_key = _wrong_key(settings)
    connection = OPNSENSE.connections[0]

    with pytest.raises(Incomplete, match="missing or can't be opened"):
        service.load_target(session, wrong_key, OPNSENSE, connection, row)


def _wrong_key(settings: Settings) -> Settings:
    from pydantic import SecretStr

    return settings.model_copy(
        update={"secret_key": SecretStr("a different key altogether, 32+ bytes")}
    )


def test_checking_a_connection_runs_its_probe_and_logs_the_calls(
    serve: Serve, session: Session, settings: Settings
) -> None:
    server = serve(lambda seen: Answer(body='{"data": []}'))
    submission = Submission(server.url, "system", None, None, {}, {"api_key": "bouncer-key"})
    save(
        session, settings, registry.CROWDSEC, {"lapi": submission}, policy=HOME_NETWORK_AND_LOOPBACK
    )
    row = service.rows_for(session, "crowdsec")["lapi"]
    target = service.load_target(
        session, settings, registry.CROWDSEC, registry.CROWDSEC.connections[0], row
    )
    calls: list[Call] = []

    async def record(call: Call) -> None:
        calls.append(call)

    result = asyncio.run(service.check(target, record, HOME_NETWORK_AND_LOOPBACK))

    assert not result.ok
    assert "doesn't look like CrowdSec's" in result.message
    assert [call.path for call in calls] == ["/v1/decisions"]


def ntopng_draft(**changes: object) -> Submission:
    fields: dict[str, object] = {
        "url": "http://192.168.1.5:3000",
        "tls_mode": "system",
        "tls_ca_pem": None,
        "tls_fingerprint": None,
        "options": {"auth": "token", "interface_id": 1},
        "secrets": {"token": "typed-token-123"},
    }
    return Submission(**{**fields, **changes})  # type: ignore[arg-type]


def draft(
    session: Session,
    settings: Settings,
    submission: Submission,
    policy: netguard.AddressPolicy = HOME_NETWORK,
) -> Target:
    return service.draft_target(
        session, settings, policy, NTOPNG, NTOPNG.connections[0], submission
    )


def test_a_connection_not_yet_saved_is_opened_with_what_was_typed(
    session: Session, settings: Settings
) -> None:
    target = draft(session, settings, ntopng_draft())

    assert (target.integration, target.connection) == ("ntopng", "api")
    assert target.origin == netguard.Origin("http", "192.168.1.5", 3000)
    assert target.options == {"auth": "token", "interface_id": 1}
    assert target.secrets == {"token": "typed-token-123"}
    assert session.scalars(select(IntegrationConnection)).all() == []
    assert session.scalars(select(StoredCredential)).all() == []


def test_a_secret_left_blank_in_a_draft_is_the_one_kept(
    session: Session, settings: Settings
) -> None:
    save(session, settings, NTOPNG, {"api": ntopng_draft(secrets={"token": "kept-token-123"})})

    target = draft(session, settings, ntopng_draft(secrets={}, options={"auth": "token"}))

    assert target.secrets == {"token": "kept-token-123"}
    assert target.options == {"auth": "token", "interface_id": 0}


def test_a_draft_that_cannot_be_used_says_what_is_wrong_by_field(
    session: Session, settings: Settings
) -> None:
    with pytest.raises(SettingsError) as raised:
        draft(session, settings, ntopng_draft(url="http://8.8.8.8", secrets={}))

    assert set(raised.value.problems) == {"url", "token"}


def test_a_draft_without_a_secret_is_refused_when_none_is_kept(
    session: Session, settings: Settings
) -> None:
    save(session, settings, NTOPNG, {"api": ntopng_draft()})
    credential_store.remove(session, Kind.INTEGRATION, "ntopng-api", "token")
    session.commit()
    with pytest.raises(SettingsError):
        draft(session, settings, ntopng_draft(secrets={}))


def test_a_draft_whose_kept_secret_cannot_be_opened_is_incomplete(
    session: Session, settings: Settings
) -> None:
    save(session, settings, NTOPNG, {"api": ntopng_draft()})

    with pytest.raises(Incomplete, match="missing or can't be opened"):
        service.draft_target(
            session,
            _wrong_key(settings),
            HOME_NETWORK,
            NTOPNG,
            NTOPNG.connections[0],
            ntopng_draft(secrets={}),
        )


def test_a_lookup_asks_the_connection_what_it_lists_and_logs_the_calls(
    serve: Serve, session: Session, settings: Settings
) -> None:
    from e2e.stand_ins import ntopng

    server = serve(ntopng("typed-token-123"))
    target = draft(session, settings, ntopng_draft(url=server.url), HOME_NETWORK_AND_LOOPBACK)
    calls: list[Call] = []

    async def record(call: Call) -> None:
        calls.append(call)

    result = asyncio.run(
        service.look_up(
            probes.LOOKUPS[("ntopng", "api", "interface_id")],
            target,
            record,
            HOME_NETWORK_AND_LOOPBACK,
        )
    )

    assert result.ok
    assert [entry.value for entry in result.entries] == ["0", "1"]
    assert calls[0].path == "/lua/rest/v2/get/ntopng/interfaces.lua"
