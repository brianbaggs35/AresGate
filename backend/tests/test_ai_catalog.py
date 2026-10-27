from decimal import Decimal
from urllib.parse import urlsplit

import pytest

from app.ai import catalog
from app.ai.catalog import Caching, Kind, Price, Wire


def test_every_provider_is_found_by_its_key() -> None:
    assert [item.key for item in catalog.PROVIDERS] == [
        "ollama",
        "ollama_cloud",
        "anthropic",
        "openai",
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

    assert haiku is not None
    assert haiku.price == catalog.ANTHROPIC.models[0].price
    assert (haiku.price.input, haiku.price.output) == (Decimal("0.10"), Decimal("0.50"))
    assert luna is not None
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


def test_input_that_is_being_cached_costs_the_write_rate() -> None:
    price = Price(Decimal(2), Decimal(10), Decimal("0.5"), Decimal("2.5"))

    assert price.cost(1_000_000, 0, cached_tokens=400_000, written_tokens=100_000) == (
        Decimal("0.5") * Decimal("0.4")
        + Decimal("2.5") * Decimal("0.1")
        + Decimal("2") * Decimal("0.5")
    )
    assert price.cost(1_000_000, 0, written_tokens=1_000_000) == Decimal("2.5")


def test_without_a_write_rate_input_that_is_being_cached_costs_the_full_rate() -> None:
    price = Price(Decimal(2), Decimal(10), Decimal("0.5"))

    assert price.cost(1_000_000, 0, written_tokens=1_000_000) == Decimal(2)


def test_a_long_prompt_costs_the_long_rates_for_cached_and_written_input_too() -> None:
    haiku = catalog.ANTHROPIC.models[0].price

    # The prompt's length counts what was read from the cache and what was written to it.
    assert haiku.cost(120_000, 0, cached_tokens=100_000, written_tokens=10_000) == (
        Decimal("0.05") * Decimal("0.1")
        + Decimal("0.625") * Decimal("0.01")
        + Decimal("0.5") * Decimal("0.01")
    )


PUBLISHED = [
    # model, input, output, cached input, cache write, then the same for a long prompt
    (
        "anthropic",
        "claude-haiku-5-5",
        "0.10",
        "0.50",
        "0.01",
        "0.125",
        ("0.50", "2.50", "0.05", "0.625", 100_000),
    ),
    ("anthropic", "claude-sonnet-5-5", "2", "10", "0.10", "2.50", None),
    ("anthropic", "claude-opus-5-5", "4", "20", "0.20", "5", None),
    ("anthropic", "claude-fable-5-1", "10", "50", "0.25", "12.50", None),
    (
        "openai",
        "gpt-6-luna",
        "0.10",
        "0.50",
        "0.01",
        "0.125",
        ("0.20", "0.75", "0.02", "0.25", 272_000),
    ),
    ("openai", "gpt-6.1-terra", "1", "5", "0.05", "1.25", ("2", "7.50", "0.10", "2.50", 272_000)),
    ("openai", "gpt-6.1-sol", "2", "10", "0.10", "2.50", ("4", "15", "0.20", "5", 272_000)),
    ("openai", "gpt-6-astra", "10", "50", "1.00", "12.50", ("20", "75", "2", "25", 272_000)),
    ("openai", "gpt-5.4-mini", "0.75", "4.50", "0.075", None, None),
    ("openai", "gpt-5.4-nano", "0.20", "1.25", "0.02", None, None),
]


@pytest.mark.parametrize(
    ("provider", "model", "sent", "received", "cached", "written", "long"), PUBLISHED
)
def test_every_model_costs_what_its_providers_pricing_page_says(
    provider: str,
    model: str,
    sent: str,
    received: str,
    cached: str,
    written: str | None,
    long: tuple[str, str, str, str, int] | None,
) -> None:
    definition = catalog.provider(provider)
    assert definition is not None
    found = definition.model(model)
    assert found is not None
    price = found.price

    assert (price.input, price.output, price.cached_input) == (
        Decimal(sent),
        Decimal(received),
        Decimal(cached),
    )
    assert price.cache_write == (Decimal(written) if written is not None else None)
    if long is None:
        assert price.long is None
    else:
        assert price.long is not None
        assert (
            price.long.input,
            price.long.output,
            price.long.cached_input,
            price.long.cache_write,
            price.long_over,
        ) == (Decimal(long[0]), Decimal(long[1]), Decimal(long[2]), Decimal(long[3]), long[4])


def test_the_models_offered_are_the_ones_asked_for_and_their_defaults_come_first_among_equals() -> (
    None
):
    assert [model.id for model in catalog.ANTHROPIC.models] == [
        "claude-haiku-5-5",
        "claude-sonnet-5-5",
        "claude-opus-5-5",
        "claude-fable-5-1",
    ]
    assert [model.id for model in catalog.OPENAI.models] == [
        "gpt-6-luna",
        "gpt-5.4-nano",
        "gpt-5.4-mini",
        "gpt-6.1-terra",
        "gpt-6.1-sol",
        "gpt-6-astra",
    ]


def test_a_claude_is_cached_by_marking_the_end_of_the_fixed_start_for_five_minutes() -> None:
    for model in catalog.ANTHROPIC.models:
        assert (model.caching, model.cache_min_tokens, model.cache_minutes) == (
            Caching.MARKED,
            512,
            5,
        )
        assert (model.effort, model.thinking_allowance, model.deprecated) == (None, 0, False)


def test_a_gpt_6_is_cached_for_30_minutes_and_asked_to_think_a_little() -> None:
    for model in catalog.OPENAI.models:
        if not model.id.startswith("gpt-6"):
            continue
        assert (model.caching, model.cache_min_tokens, model.cache_minutes) == (
            Caching.MARKED,
            1024,
            30,
        )
        # Astra and Sol can't be asked not to think, so none of them is.
        assert model.effort == "low"
        assert model.thinking_allowance > 0


def test_an_older_gpt_caches_by_itself_does_not_think_and_nano_is_being_retired() -> None:
    for model_id in ("gpt-5.4-mini", "gpt-5.4-nano"):
        model = catalog.OPENAI.model(model_id)
        assert model is not None
        assert (model.caching, model.effort, model.thinking_allowance) == (
            Caching.AUTOMATIC,
            None,
            0,
        )
    assert [model.id for model in catalog.OPENAI.models if model.deprecated] == ["gpt-5.4-nano"]
