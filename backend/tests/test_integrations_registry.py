import re

import pytest

from app.integrations import probes, registry
from app.integrations.registry import (
    INTEGRATIONS,
    ConnectionDef,
    FieldKind,
    ModuleState,
    SettingsError,
    active_fields,
    clean_options,
    credential_name,
)
from app.security.credential_store import NAME_PATTERN

NTOPNG = registry.NTOPNG.connections[0]


def test_every_connection_has_a_probe_and_every_probe_a_connection() -> None:
    defined = {
        (integration.key, connection.key)
        for integration in INTEGRATIONS.values()
        for connection in integration.connections
    }

    assert defined == set(probes.PROBES)


def test_the_four_integrations_are_listed_in_order() -> None:
    assert list(INTEGRATIONS) == ["opnsense", "ntopng", "wazuh", "crowdsec"]


def test_names_fit_where_they_are_kept() -> None:
    for integration in INTEGRATIONS.values():
        assert re.fullmatch(NAME_PATTERN, integration.key)
        assert integration.docs_url.startswith("https://")
        assert integration.setup
        for connection in integration.connections:
            assert re.fullmatch(NAME_PATTERN, connection.key)
            assert len(credential_name(integration.key, connection.key)) <= 63
            assert re.fullmatch(NAME_PATTERN, credential_name(integration.key, connection.key))
            for item in connection.fields:
                assert re.fullmatch(NAME_PATTERN, item.key)


def test_a_connection_has_one_of_each_field() -> None:
    for integration in INTEGRATIONS.values():
        for connection in integration.connections:
            keys = [item.key for item in connection.fields]
            assert len(keys) == len(set(keys))
            reserved = {"url", "tls_mode", "tls_ca_pem", "tls_fingerprint", "disabled_modules"}
            assert not reserved & set(keys)


def test_a_field_that_depends_on_another_comes_after_it() -> None:
    for integration in INTEGRATIONS.values():
        for connection in integration.connections:
            earlier: dict[str, registry.FieldDef] = {}
            for item in connection.fields:
                if item.only_if:
                    assert item.only_if.field in earlier
                    controlling = earlier[item.only_if.field]
                    assert controlling.kind is FieldKind.CHOICE
                    assert item.only_if.value in {choice.value for choice in controlling.choices}
                earlier[item.key] = item


def test_choices_have_valid_defaults() -> None:
    for integration in INTEGRATIONS.values():
        for connection in integration.connections:
            for item in connection.fields:
                if item.kind is FieldKind.CHOICE:
                    assert item.default in {choice.value for choice in item.choices}


def test_modules_are_read_with_get_requests_under_api() -> None:
    modules = registry.OPNSENSE_MODULES

    assert modules[0].key == "firewall"
    assert len({module.key for module in modules}) == len(modules)
    assert all(module.path.startswith("/api/") for module in modules[1:])
    assert not modules[0].path


def test_a_modules_request_path_is_not_sent_to_the_web_app() -> None:
    assert "path" not in registry.OPNSENSE_MODULES[1].model_dump()


def test_only_zenarmor_is_optional() -> None:
    optional = [
        (integration.key, connection.key)
        for integration in INTEGRATIONS.values()
        for connection in integration.connections
        if connection.optional
    ]

    assert optional == [("opnsense", "zenarmor")]


def test_the_connection_of_an_integration_is_found_by_key() -> None:
    assert registry.WAZUH.connection("indexer") is registry.WAZUH.connections[1]
    assert registry.WAZUH.connection("nothing") is None


@pytest.mark.parametrize(
    ("state", "present"),
    [
        (ModuleState.RUNNING, True),
        (ModuleState.STOPPED, True),
        (ModuleState.INSTALLED, True),
        (ModuleState.NOT_INSTALLED, False),
        (ModuleState.NO_ACCESS, False),
        (ModuleState.UNKNOWN, False),
    ],
)
def test_a_module_is_present_if_it_was_found(state: ModuleState, present: bool) -> None:
    assert state.present is present


def test_defaults_fill_in_what_is_missing() -> None:
    assert clean_options(NTOPNG, {}) == {"auth": "token", "interface_id": 0}


def test_only_the_fields_that_apply_are_kept() -> None:
    options = clean_options(
        NTOPNG, {"auth": "basic", "username": " admin ", "interface_id": "2", "token": "ignored"}
    )

    assert options == {"auth": "basic", "username": "admin", "interface_id": 2}
    assert [item.key for item in active_fields(NTOPNG, options)] == [
        "auth",
        "username",
        "password",
        "interface_id",
    ]


def test_a_value_may_be_blank_or_missing_only_if_there_is_a_default() -> None:
    with pytest.raises(SettingsError) as raised:
        clean_options(NTOPNG, {"auth": "basic", "username": "  "})

    assert raised.value.problems == {"username": "Enter a value."}


@pytest.mark.parametrize("value", ["abc", "-1", "1000", "1.5", "١٢"])
def test_a_number_is_a_whole_number_in_range(value: str) -> None:
    with pytest.raises(SettingsError) as raised:
        clean_options(NTOPNG, {"interface_id": value})

    assert "whole number from 0 to 999" in raised.value.problems["interface_id"]


def test_a_choice_must_be_one_of_the_options() -> None:
    with pytest.raises(SettingsError) as raised:
        clean_options(NTOPNG, {"auth": "magic"})

    assert raised.value.problems == {"auth": "Choose one of the options."}


@pytest.mark.parametrize("value", ["x" * 129, "line\nbreak", "tab\there"])
def test_text_is_short_and_printable(value: str) -> None:
    connection: ConnectionDef = registry.WAZUH.connections[0]

    with pytest.raises(SettingsError) as raised:
        clean_options(connection, {"username": value})

    assert "at most 128 characters" in raised.value.problems["username"]


def test_every_problem_is_reported_at_once() -> None:
    with pytest.raises(SettingsError) as raised:
        clean_options(NTOPNG, {"auth": "basic", "interface_id": "x"})

    assert set(raised.value.problems) == {"username", "interface_id"}
    assert "username: Enter a value." in str(raised.value)
