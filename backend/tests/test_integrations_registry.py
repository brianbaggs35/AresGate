import re
from urllib.parse import urlsplit

import pytest

from app.integrations import probes, registry
from app.integrations.registry import (
    INTEGRATIONS,
    ConnectionDef,
    FieldDef,
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


def test_the_integrations_are_listed_in_order() -> None:
    assert list(INTEGRATIONS) == ["opnsense", "ntopng", "wazuh", "crowdsec", "virustotal"]


def test_virustotal_is_threat_intelligence_on_the_internet_with_a_warned_tier() -> None:
    definition = INTEGRATIONS["virustotal"]
    connection = definition.connection("api")

    assert definition.category == "Threat intelligence"
    assert connection is not None
    assert connection.internet
    assert connection.address == "https://www.virustotal.com"
    assert urlsplit(connection.address).scheme == "https"
    tier = next(item for item in connection.fields if item.key == "tier")
    assert tier.kind is FieldKind.CHOICE
    assert tier.default == "free"
    assert tier.caution.startswith("Free and premium differ.")


def test_a_connection_with_a_fixed_address_takes_no_other_address() -> None:
    for integration in INTEGRATIONS.values():
        for connection in integration.connections:
            if connection.address:
                assert connection.address == connection.url_example


def test_a_guide_has_steps_for_each_connection_it_names_and_cites_its_sources() -> None:
    for integration in INTEGRATIONS.values():
        guide = integration.guide
        connections = {connection.key: connection for connection in integration.connections}
        named = [part.connection for part in guide.parts]

        assert set(named) <= set(connections)
        assert len(named) == len(set(named))
        assert guide.sources
        for source in guide.sources:
            assert source.title
            assert urlsplit(source.url).scheme == "https"
        for part in guide.parts:
            # A part is left out only where the connection can be.
            assert part.optional == connections[part.connection].optional
            assert part.title
            assert part.intro
            assert part.steps
            for step in part.steps:
                assert step.title
                assert step.detail


def test_every_connection_is_covered_by_a_part_of_its_guide() -> None:
    for integration in INTEGRATIONS.values():
        covered = {part.connection for part in integration.guide.parts}

        assert covered == {connection.key for connection in integration.connections}


def test_a_step_never_asks_for_a_secret_to_be_typed_into_the_guide() -> None:
    # The guide is plain text on a page: what it shows must be an example that is safe to read.
    for integration in INTEGRATIONS.values():
        for part in integration.guide.parts:
            for step in part.steps:
                assert "BEGIN" not in step.command
                assert "token=" not in step.command.lower()


def test_names_fit_where_they_are_kept() -> None:
    for integration in INTEGRATIONS.values():
        assert re.fullmatch(NAME_PATTERN, integration.key)
        assert integration.docs_url.startswith("https://")
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
    assert clean_options(NTOPNG, {}) == {"auth": "token", "interface_id": ""}


def test_no_ntopng_interface_is_assumed_because_ntopng_numbers_them_itself() -> None:
    field = next(item for item in NTOPNG.fields if item.key == "interface_id")

    assert field.default == ""
    for blank in ("", "  ", " , ", None):
        assert clean_options(NTOPNG, {"interface_id": blank})["interface_id"] == ""


def test_only_the_fields_that_apply_are_kept() -> None:
    options = clean_options(
        NTOPNG, {"auth": "basic", "username": " admin ", "interface_id": "2", "token": "ignored"}
    )

    assert options == {"auth": "basic", "username": "admin", "interface_id": "2"}
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

    assert "whole numbers from 0 to 999" in raised.value.problems["interface_id"]


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


def test_a_lookup_field_that_allows_several_keeps_them_lowest_first_without_repeats() -> None:
    field = next(item for item in NTOPNG.fields if item.key == "interface_id")

    assert field.kind is FieldKind.LOOKUP
    assert field.action == "Fetch interfaces"
    assert field.multiple is True
    assert clean_options(NTOPNG, {"interface_id": " 12 "})["interface_id"] == "12"
    assert clean_options(NTOPNG, {"interface_id": "3, 1,,3 ,2"})["interface_id"] == "1,2,3"
    assert clean_options(NTOPNG, {"interface_id": 5})["interface_id"] == "5"


@pytest.mark.parametrize("value", ["eth1", "1,x", "1,-2", "1,1000", "0;1"])
def test_a_lookup_field_that_allows_several_refuses_what_is_not_numbers_in_range(
    value: str,
) -> None:
    with pytest.raises(SettingsError) as raised:
        clean_options(NTOPNG, {"interface_id": value})

    assert (
        "whole numbers from 0 to 999 separated by commas" in raised.value.problems["interface_id"]
    )


def test_a_lookup_field_that_allows_several_has_a_limit() -> None:
    many = ",".join(str(number) for number in range(registry.MAX_CHOSEN + 1))

    with pytest.raises(SettingsError) as raised:
        clean_options(NTOPNG, {"interface_id": many})

    assert raised.value.problems == {"interface_id": "Choose at most 16."}
    assert (
        len(clean_options(NTOPNG, {"interface_id": many[: -len(f",{registry.MAX_CHOSEN}")]})) == 2
    )


@pytest.mark.parametrize(
    ("saved", "numbers"),
    [("0,1", [0, 1]), (" 3 , 1 ", [1, 3]), (2, [2]), ("x,4,,٣", [4]), ("", [])],
)
def test_what_was_chosen_is_read_back_whatever_it_was_saved_as(
    saved: str | int, numbers: list[int]
) -> None:
    assert registry.chosen_numbers(saved) == numbers


def test_a_lookup_field_that_allows_one_is_kept_as_a_whole_number_like_a_number() -> None:
    single = ConnectionDef(
        key="api",
        label="API",
        summary="",
        url_example="",
        allow_http=False,
        fields=(
            FieldDef(
                key="slot",
                label="Slot",
                kind=FieldKind.LOOKUP,
                default=0,
                maximum=9,
                action="Fetch",
            ),
        ),
    )

    assert clean_options(single, {"slot": " 4 "}) == {"slot": 4}
    with pytest.raises(SettingsError) as raised:
        clean_options(single, {"slot": "10"})
    assert "whole number from 0 to 9" in raised.value.problems["slot"]
