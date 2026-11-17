"""What to try when a request got no answer: said for the kind of failure and, where it is
known, for the system."""

import pytest

from app.integrations.advice import GENERIC, NTOPNG_ALERTS, SPECIFIC, Failure, advise

ALERTS = "/lua/rest/v2/get/alert/severity/counters.lua"


@pytest.mark.parametrize("kind", [Failure.TIMEOUT, Failure.UNREACHABLE, Failure.DROPPED])
def test_a_failure_of_the_connection_has_advice_for_any_system(kind: Failure) -> None:
    assert advise("opnsense", kind, "/api/x") == GENERIC[kind]


@pytest.mark.parametrize("kind", [Failure.SECURE, Failure.REFUSED, Failure.OTHER])
def test_a_failure_whose_message_says_it_all_has_none(kind: Failure) -> None:
    assert advise("ntopng", kind, ALERTS) is None


def test_a_fault_inside_aresgate_says_so_for_every_system_and_never_blames_the_settings() -> None:
    for integration in ("ntopng", "wazuh"):
        found = advise(integration, Failure.INTERNAL, ALERTS)
        assert found == GENERIC[Failure.INTERNAL]
        assert "AresGate's log" in GENERIC[Failure.INTERNAL]


def test_ntopng_that_drops_a_request_is_not_a_missing_permission() -> None:
    found = advise("ntopng", Failure.DROPPED, "/lua/rest/v2/get/ntopng/interfaces.lua")

    assert found == f"{GENERIC[Failure.DROPPED]} {SPECIFIC['ntopng'][Failure.DROPPED]}"
    assert "isn't a permission" in SPECIFIC["ntopng"][Failure.DROPPED]


@pytest.mark.parametrize("kind", [Failure.DROPPED, Failure.TIMEOUT])
def test_an_ntopng_page_about_alerts_points_at_its_alert_database(kind: Failure) -> None:
    assert NTOPNG_ALERTS in str(advise("ntopng", kind, ALERTS))


def test_it_is_for_ntopng_only() -> None:
    assert NTOPNG_ALERTS not in str(advise("wazuh", Failure.DROPPED, ALERTS))
    assert NTOPNG_ALERTS not in str(advise("ntopng", Failure.UNREACHABLE, ALERTS))
