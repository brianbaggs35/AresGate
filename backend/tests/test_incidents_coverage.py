"""What an incident would say if more of the programs were connected: every integration there is
has something to offer, so none is left out of the list the page shows."""

from app.incidents import coverage
from app.integrations import registry


def test_every_integration_that_can_be_connected_has_something_to_offer() -> None:
    assert set(registry.INTEGRATIONS) == set(coverage.OFFERS)


def test_what_each_offers_is_said_in_a_sentence() -> None:
    assert all(adds.endswith(".") for adds in coverage.OFFERS.values())
