from decimal import Decimal
from urllib.parse import urlsplit

import pytest

from app.ai import catalog
from app.ai.catalog import Kind, Price, Wire


def test_every_provider_is_found_by_its_key() -> None:
    assert [item.key for item in catalog.PROVIDERS] == [
        "anthropic",
        "openai",
        "ollama",
        "ollama_cloud",
    ]
    assert catalog.provider("openai") is catalog.OPENAI
    assert catalog.provider("nothing") is None


def test_the_defaults_are_the_cheap_fast_models() -> None:
    assert catalog.ANTHROPIC.default_model == "claude-haiku-5-5"
    assert catalog.OPENAI.default_model == "gpt-6-luna"
    assert catalog.OLLAMA.default_model is None
    assert catalog.OLLAMA_CLOUD.default_model is None


@pytest.mark.parametrize("definition", [catalog.ANTHROPIC, catalog.OPENAI])
def test_a_hosted_provider_lists_models_with_prices_and_its_default_is_one_of_them(
    definition: catalog.ProviderDef,
) -> None:
    assert definition.kind is Kind.HOSTED
    assert definition.fixed_models
    assert definition.model(definition.default_model or "") is not None
    assert definition.model("nothing") is None
    for model in definition.models:
        assert model.price is not None
        assert model.note
        assert 0 < model.price.input < model.price.output
    ids = [model.id for model in definition.models]
    assert len(ids) == len(set(ids))


def test_an_ollama_has_the_models_it_has_and_no_price() -> None:
    for definition in (catalog.OLLAMA, catalog.OLLAMA_CLOUD):
        assert definition.wire is Wire.OLLAMA
        assert not definition.fixed_models
        assert definition.pricing_url is None
    assert (catalog.OLLAMA.kind, catalog.OLLAMA.needs_key) == (Kind.LOCAL, False)
    assert (catalog.OLLAMA_CLOUD.kind, catalog.OLLAMA_CLOUD.needs_key) == (Kind.CLOUD, True)
    assert catalog.OLLAMA.origin is None
    assert catalog.OLLAMA_CLOUD.origin == "https://ollama.com"


def test_prices_are_those_the_providers_publish() -> None:
    haiku = catalog.ANTHROPIC.model("claude-haiku-5-5")
    luna = catalog.OPENAI.model("gpt-6-luna")

    assert haiku and haiku.price == catalog.ANTHROPIC.models[0].price
    assert haiku.price and (haiku.price.input, haiku.price.output) == (
        Decimal("0.10"),
        Decimal("0.50"),
    )
    assert luna and luna.price
    assert (luna.price.input, luna.price.cached_input, luna.price.output) == (
        Decimal("0.10"),
        Decimal("0.01"),
        Decimal("0.50"),
    )


def test_prices_say_where_they_came_from_and_when() -> None:
    assert catalog.PRICES_AS_OF == "2026-10-27"
    assert urlsplit(catalog.ANTHROPIC.pricing_url or "").hostname == "platform.claude.com"
    assert urlsplit(catalog.OPENAI.pricing_url or "").hostname == "developers.openai.com"


def test_a_request_costs_its_tokens_at_the_models_rates() -> None:
    price = Price(Decimal(2), Decimal(10), Decimal("0.5"))

    assert price.cost(1_000_000, 0) == Decimal(2)
    assert price.cost(0, 1_000_000) == Decimal(10)
    assert price.cost(3000, 600) == Decimal("0.012")


def test_input_the_provider_had_cached_costs_the_cached_rate() -> None:
    price = Price(Decimal(2), Decimal(10), Decimal("0.5"))

    assert price.cost(1_000_000, 0, cached_tokens=400_000) == Decimal("1.4")
    # More cached than sent can't happen, but never costs less than nothing.
    assert price.cost(100, 0, cached_tokens=500) == Decimal("0.00025")


def test_without_a_cached_rate_cached_input_costs_the_full_rate() -> None:
    price = Price(Decimal(2), Decimal(10))

    assert price.cost(1_000_000, 0, cached_tokens=400_000) == Decimal(2)


def test_a_long_prompt_costs_the_long_rates() -> None:
    haiku = catalog.ANTHROPIC.models[0].price
    assert haiku is not None

    assert haiku.cost(100_000, 1000) == Decimal("0.0105")
    assert haiku.cost(100_001, 1000) == Decimal("0.0525005")
